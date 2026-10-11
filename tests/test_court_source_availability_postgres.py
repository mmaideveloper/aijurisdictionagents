"""Synthetic queue integration only; never connect to non-loopback PostgreSQL."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import uuid

import httpx
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg import sql
import pytest

from services.court_decision_collector.fixtures import sample_court_decision_records
from services.court_decision_collector.postgres_store import PostgresCourtDecisionStore
from services.court_decision_collector.service import CourtDecisionCollectorService

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 10, 11)
DIGEST = sha256(b"synthetic-review-evidence").hexdigest()
REVIEWER = sha256(b"synthetic-operator").hexdigest()


@pytest.fixture
def store():
    # Existing configuration key; without it use the documented synthetic local
    # PostgreSQL credentials. A unique database isolates tables and pgvector.
    target = os.getenv("COURT_DECISIONS_DB_CLOUD") or make_conninfo(
        host="127.0.0.1", port=5432, dbname="postgres", user="postgres", password="postgres",
    )
    try:
        settings = conninfo_to_dict(target)
    except Exception:
        pytest.skip("invalid local court PostgreSQL test configuration")
    if settings.get("host") not in {"127.0.0.1", "localhost", "::1"} or settings.get("hostaddr"):
        pytest.skip("court PostgreSQL integration requires an explicit loopback host")
    database = "court_889_" + uuid.uuid4().hex
    try:
        conn = psycopg.connect(target, connect_timeout=3, autocommit=True)
    except psycopg.Error:
        pytest.skip("local PostgreSQL unavailable; integration validation pending")
    try:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        scoped_target = make_conninfo(target, dbname=database, options="")
        candidate = PostgresCourtDecisionStore(connection_uri=scoped_target)
        candidate.initialize()
        # Exercise tracked migration, including repeated application.
        migration = (ROOT / "databases/court-decision-collector/migrations/0006_source_availability_review.sql").read_text()
        with candidate._connect() as scoped:
            scoped.execute(migration)
            scoped.execute(migration)
        candidate.ensure_scheduler_state(
            source_system="infosud", source_total=3, source_updated_at="synthetic",
            page_size=25, daily_new_limit=10, utc_day=DAY, overlap_pages=1,
        )
        yield candidate
    finally:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
        conn.close()


def enqueue(store, guid="missing", ordinal=0):
    store.enqueue_work_page(source_system="infosud", work_class="new", source_page=0,
                            entries=[(guid, ordinal, True)])
    return store.next_work_item(source_system="infosud", work_class="new")


def review(store, unavailable=True, **overrides):
    params = dict(source_system="infosud", source_guid="missing", unavailable=unavailable,
                  evidence_category="operator_verified_unavailable" if unavailable else "operator_requeue",
                  evidence_sha256=DIGEST, reviewer_sha256=REVIEWER)
    params.update(overrides)
    return store.review_work_availability(**params)


@pytest.mark.parametrize("status", [404, 410])
def test_review_survives_restart_rediscovery_and_stale_worker_then_requeues(store, status):
    missing = enqueue(store)
    store.mark_work_retry(missing, error_type="source_missing", http_status=status,
                          next_attempt_at=datetime.now(timezone.utc) + timedelta(days=7))
    assert review(store)
    assert not review(store)  # Idempotent repeated approval adds no audit event.
    restarted = PostgresCourtDecisionStore(connection_uri=store.connection_uri)
    restarted.initialize()
    for _ in range(3):
        restarted.enqueue_work_page(source_system="infosud", work_class="backfill", source_page=1,
                                    entries=[("missing", 0, False)])
        restarted.enqueue_work_page(source_system="infosud", work_class="new", source_page=0,
                                    entries=[("missing", 0, True)])
        assert restarted.next_work_item(source_system="infosud", work_class="new") is None
        assert restarted.pending_work_count(source_system="infosud", work_class="new") == 0
    restarted.mark_work_retry(missing, error_type="source_transient", http_status=503)
    assert not restarted.complete_work_item(missing, utc_day=DAY, count_quota=True)
    assert restarted.get_scheduler_state(source_system="infosud").quota_used == 0
    assert review(restarted, unavailable=False)
    assert not review(restarted, unavailable=False)
    restored = restarted.next_work_item(source_system="infosud", work_class="new")
    assert restored.source_guid == "missing"
    assert restored.attempt_count == 0
    assert restarted.complete_work_item(restored, utc_day=DAY, count_quota=True)
    assert not restarted.complete_work_item(restored, utc_day=DAY, count_quota=True)
    assert restarted.get_scheduler_state(source_system="infosud").quota_used == 1
    with restarted._connect() as conn:
        events = conn.execute("SELECT * FROM court_decision_availability_reviews ORDER BY review_id").fetchall()
        row = conn.execute("SELECT * FROM court_decision_import_queue").fetchone()
    assert len(events) == 2
    assert events[0]["last_http_status"] == status
    assert events[0]["attempt_count"] == 1
    assert events[0]["reference_hash"] == sha256(b"missing").hexdigest()
    assert events[1]["source_unavailable"] is False
    assert row["last_http_status"] is None
    assert row["last_error_type"] == ""


@pytest.mark.parametrize("error,status", [("", None), ("source_transient", 503), ("source_missing", None)])
def test_unverified_or_transient_items_cannot_be_quarantined(store, error, status):
    item = enqueue(store)
    if error:
        store.mark_work_retry(item, error_type=error, http_status=status)
    with pytest.raises(ValueError, match="recorded missing-source"):
        review(store)
    assert store.next_work_item(source_system="infosud", work_class="new") is not None


@pytest.mark.parametrize("override", [
    {"evidence_category": "raw-personal-data"}, {"evidence_sha256": "private-url"},
    {"reviewer_sha256": "real-person"},
])
def test_invalid_review_metadata_never_mutates_queue(store, override):
    item = enqueue(store)
    store.mark_work_retry(item, error_type="source_missing", http_status=404)
    with pytest.raises(ValueError):
        review(store, **override)
    assert store.next_work_item(source_system="infosud", work_class="new") is not None


def test_deferred_missing_and_quarantined_work_do_not_request_or_block_valid_work(store):
    item = enqueue(store)
    store.mark_work_retry(item, error_type="source_missing", http_status=404)
    review(store)
    store.enqueue_work_page(source_system="infosud", work_class="new", source_page=0,
                            entries=[("deferred", 1, True), ("valid", 2, True)])
    deferred = store.next_work_item(source_system="infosud", work_class="new")
    store.mark_work_retry(deferred, error_type="source_missing", http_status=404,
                          next_attempt_at=datetime.now(timezone.utc) + timedelta(days=7))
    calls = []

    class Source:
        source_system = "infosud"

        def get_decision(self, guid):
            calls.append(guid)
            assert guid == "valid"
            return replace(sample_court_decision_records()[0], source_system="infosud", source_guid=guid)

    for _ in range(3):
        restarted = PostgresCourtDecisionStore(connection_uri=store.connection_uri)
        summary = CourtDecisionCollectorService(store=restarted, source=Source())._drain_work(
            work_class="new", utc_day=DAY, daily_new_limit=10, max_items=0,
        )
        assert summary.processed in {0, 1}
    assert calls == ["valid"]
    assert store.get_scheduler_state(source_system="infosud").quota_used == 1
    assert store.pending_work_count(source_system="infosud", work_class="new") == 1
    assert store.pending_work_count(source_system="infosud", work_class="new", eligible_only=True) == 0


def test_first_404_stays_deferred_with_numeric_status_and_no_review(store):
    enqueue(store)

    class Source:
        source_system = "infosud"

        def get_decision(self, guid):
            response = httpx.Response(404, request=httpx.Request("GET", "https://synthetic.invalid"))
            response.raise_for_status()

    CourtDecisionCollectorService(store=store, source=Source())._drain_work(
        work_class="new", utc_day=DAY, daily_new_limit=10, max_items=0,
    )
    with store._connect() as conn:
        row = conn.execute("SELECT * FROM court_decision_import_queue").fetchone()
        count = conn.execute("SELECT COUNT(*) AS count FROM court_decision_availability_reviews").fetchone()
    assert not row["source_unavailable"]
    assert row["last_http_status"] == 404
    assert row["next_attempt_at"] > datetime.now(timezone.utc)
    assert count["count"] == 0


def test_migration_upgrades_legacy_queue_without_discarding_deferred_state(store):
    item = enqueue(store)
    future = datetime.now(timezone.utc) + timedelta(days=7)
    store.mark_work_retry(item, error_type="source_missing", http_status=404, next_attempt_at=future)
    with store._connect() as conn:
        conn.execute("DROP TABLE court_decision_availability_reviews")
        conn.execute("ALTER TABLE court_decision_import_queue DROP COLUMN source_unavailable")
        conn.execute("ALTER TABLE court_decision_import_queue DROP COLUMN last_http_status")
        conn.execute((ROOT / "databases/court-decision-collector/migrations/0006_source_availability_review.sql").read_text())
    store.initialize()
    with store._connect() as conn:
        row = conn.execute("SELECT * FROM court_decision_import_queue").fetchone()
    assert row["status"] == "retryable"
    assert row["attempt_count"] == 1
    assert row["next_attempt_at"] == future
    assert row["last_http_status"] is None
    assert row["source_unavailable"] is False
