from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256

import httpx

from services.court_decision_collector.config import CourtDecisionCollectorConfig
from services.court_decision_collector.fixtures import FixtureCourtDecisionSource, sample_court_decision_records
from services.court_decision_collector.infosud_source import (
    InfoSudDecisionPage,
    InfoSudSourceClient,
    record_from_infosud_payload,
)
from services.court_decision_collector.postgres_store import (
    CourtDecisionCollectorStatus,
    CourtDecisionSchedulerState,
    CourtDecisionWorkItem,
    _parse_issue_date,
    normalize_court_name,
)
from services.court_decision_collector.pseudonymization import pseudonymize_court_decision_text
from services.court_decision_collector.query import parse_court_decision_query
from services.court_decision_collector.service import CourtDecisionCollectorService


class FakeStore:
    def __init__(self) -> None:
        self.saved = []
        self.documents = {}
        self.import_states = {}
        self.scheduler = None
        self.queue = {}
        self.checkpoint_failures = 0
        self.enrichment_queue = []

    def upsert_decision(self, record, *, work_class="manual"):
        previous = self.documents.get(record.source_guid)
        self.saved.append(record)
        self.documents[record.source_guid] = record.version_checksum()
        state = "created" if previous is None else ("unchanged" if previous == record.version_checksum() else "updated")
        return type("Stored", (), {"decision_id": "decision-1", "version_id": "version-1", "state": state})()

    def enqueue_enrichment(self, **kwargs):
        self.enrichment_queue.append(kwargs)
        return True

    def ensure_scheduler_state(
        self, *, source_system, source_total, source_updated_at, page_size,
        daily_new_limit, utc_day, overlap_pages,
    ):
        if self.scheduler is None:
            self.scheduler = CourtDecisionSchedulerState(
                source_system=source_system,
                discovered_source_total=source_total,
                source_updated_at=source_updated_at,
                backfill_next_page=max(0, len(self.documents) // page_size - overlap_pages),
                backfill_generation=0,
                quota_day=utc_day,
                quota_used=0,
                daily_new_limit=daily_new_limit,
                status="initialized",
            )
        elif self.scheduler.quota_day != utc_day:
            self.scheduler = replace(
                self.scheduler,
                quota_day=utc_day,
                quota_used=0,
                daily_new_limit=daily_new_limit,
            )
        else:
            self.scheduler = replace(self.scheduler, daily_new_limit=daily_new_limit)
        return self.scheduler

    def get_scheduler_state(self, *, source_system):
        assert self.scheduler is not None
        return self.scheduler

    def enqueue_work_page(self, *, source_system, work_class, source_page, entries):
        for guid, ordinal, counts_toward_quota in entries:
            previous = self.queue.get(guid)
            if previous and previous["item"].work_class == "new" and work_class == "backfill":
                continue
            self.queue[guid] = {
                "item": CourtDecisionWorkItem(
                    source_system=source_system,
                    source_guid=guid,
                    work_class=work_class,
                    source_page=source_page,
                    source_ordinal=ordinal,
                    counts_toward_quota=counts_toward_quota,
                ),
                "status": "pending",
            }
        return len(entries)

    def next_work_item(self, *, source_system, work_class):
        items = [
            entry["item"] for entry in self.queue.values()
            if entry["item"].work_class == work_class and entry["status"] in {"pending", "retryable"}
        ]
        return min(items, key=lambda item: (item.source_ordinal, item.source_guid)) if items else None

    def complete_work_item(self, item, *, utc_day, count_quota):
        entry = self.queue[item.source_guid]
        if entry["status"] == "completed":
            return False
        entry["status"] = "completed"
        increment = int(item.work_class == "new" and item.counts_toward_quota and count_quota)
        self.scheduler = replace(
            self.scheduler,
            quota_day=utc_day,
            quota_used=self.scheduler.quota_used + increment,
            status="processing_new" if item.work_class == "new" else "processing_backfill",
        )
        return True

    def mark_work_retry(self, item, *, error_type):
        self.queue[item.source_guid]["status"] = "retryable"
        self.scheduler = replace(self.scheduler, status="retryable_error")

    def pending_work_count(self, *, source_system, work_class):
        return sum(
            entry["item"].work_class == work_class and entry["status"] in {"pending", "retryable"}
            for entry in self.queue.values()
        )

    def save_discovery_checkpoint(self, *, source_system, source_total, source_updated_at):
        self.scheduler = replace(
            self.scheduler,
            discovered_source_total=source_total,
            source_updated_at=source_updated_at,
            status="discovered",
        )

    def advance_backfill_checkpoint(
        self, *, source_system, source_total, page_size, page, wrote_data,
    ):
        page_count = max(1, (source_total + page_size - 1) // page_size)
        wrapped = page + 1 >= page_count
        self.scheduler = replace(
            self.scheduler,
            backfill_next_page=0 if wrapped else page + 1,
            backfill_generation=self.scheduler.backfill_generation + int(wrapped),
            status="backfill_cycle_complete" if wrapped else "processing_backfill",
        )

    def record_checkpoint_failure(self, *, source_system, status):
        self.checkpoint_failures += 1
        self.scheduler = replace(self.scheduler, status=status)

    def save_import_state(
        self,
        *,
        source_system: str,
        cursor_kind: str,
        last_source_guid: str,
        status: str,
        conn=None,
    ) -> None:
        self.import_states[(source_system, cursor_kind)] = CourtDecisionCollectorStatus(
            last_processed_at="2026-06-30T00:00:00+00:00",
            last_source_guid=last_source_guid,
            status=status,
        )

    def get_import_state(self, *, source_system: str, cursor_kind: str) -> CourtDecisionCollectorStatus:
        return self.import_states.get(
            (source_system, cursor_kind),
            CourtDecisionCollectorStatus(last_processed_at="", last_source_guid="", status="not_started"),
        )


def test_issue_date_parser_supports_source_and_iso_dates_without_fabrication() -> None:
    assert str(_parse_issue_date("31.12.2012")) == "2012-12-31"
    assert str(_parse_issue_date("2026-06-29")) == "2026-06-29"
    assert _parse_issue_date("31.02.2012") is None
    assert _parse_issue_date("") is None


def test_new_import_is_enqueued_as_recent_only_when_background_enabled() -> None:
    store = FakeStore()
    service = CourtDecisionCollectorService(
        store=store,
        enrichment_auto_queue=True,
        enrichment_max_attempts=4,
    )
    service.sync_records([sample_court_decision_records()[0]], work_class="new")
    assert store.enrichment_queue == [
        {
            "decision_id": "decision-1",
            "version_id": "version-1",
            "priority_class": "recent",
            "max_attempts": 4,
        }
    ]


def test_court_name_normalization_is_diacritic_insensitive_and_exact() -> None:
    assert normalize_court_name("Okresny sud Poprad") == "okresny sud poprad"
    assert normalize_court_name("Okresný súd Poprad") == "okresny sud poprad"
    assert normalize_court_name("Okresný súd Kežmarok") != "okresny sud poprad"

def test_conversational_purchase_contract_query_extracts_topic_count_and_latest() -> None:
    profile = parse_court_decision_query(
        "Ukáž mi posledných 5 súdnych rozhodnutí o kupón predajnej zmluve"
    )

    assert profile.topic_query == "kupna predajna zmluva"
    assert profile.requested_limit == 5
    assert profile.latest_requested is True
    assert profile.concepts == ("purchase_contract",)
    assert "predaj:* & zmluv:*" in profile.tsquery


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_config_reads_infosud_timeout_retry_settings(monkeypatch) -> None:
    monkeypatch.setenv("COURT_DECISIONS_DB_CLOUD", "postgresql://postgres:postgres@db/court_decisions_sk")
    monkeypatch.setenv("COURT_DECISIONS_SOURCE_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("COURT_DECISIONS_SOURCE_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("COURT_DECISIONS_SOURCE_RETRY_BACKOFF_SECONDS", "1.5")
    monkeypatch.setenv("COURT_DECISIONS_DAILY_NEW_LIMIT", "10000")
    monkeypatch.setenv("COURT_DECISIONS_DISCOVERY_OVERLAP_PAGES", "3")
    monkeypatch.setenv("COURT_DECISIONS_BACKFILL_PAGES_PER_CYCLE", "12")

    config = CourtDecisionCollectorConfig.from_env()

    assert config.source_timeout_seconds == 120
    assert config.source_retry_attempts == 4
    assert config.source_retry_backoff_seconds == 1.5
    assert config.daily_new_limit == 10000
    assert config.discovery_overlap_pages == 3
    assert config.backfill_pages_per_cycle == 12
    config.validate()


def test_infosud_list_decisions_retries_connect_timeout_with_safe_context(monkeypatch) -> None:
    messages = []
    sleeps = []
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            raise httpx.ConnectTimeout("timed out")
        return FakeResponse(
            {
                "rozhodnutieList": [
                    {"guid": "decision-guid-1", "spisovaZnacka": "12C/34/2026"},
                ],
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = InfoSudSourceClient(
        base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
        timeout_seconds=90,
        retry_attempts=2,
        retry_backoff_seconds=0.25,
        progress_logger=messages.append,
        sleep_fn=sleeps.append,
    )

    refs = client.list_decisions(page=5362, size=25)

    assert [ref.guid for ref in refs] == ["decision-guid-1"]
    assert len(calls) == 2
    assert calls[0][1]["params"] == {"page": 5363, "size": 25}
    assert calls[0][1]["timeout"] == 90
    assert sleeps == [0.25]
    assert any(
        (
            "infosud_source_request_retry stage=list_decision_page page=5362 size=25 "
            "attempt=1 max_attempts=2 timeout_seconds=90 error_type=ConnectTimeout"
        )
        in message
        for message in messages
    )


def test_infosud_scheduler_page_translates_zero_based_page_and_returns_total(monkeypatch) -> None:
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            {
                "numFound": 123,
                "updateDate": "22.08.2026",
                "rozhodnutieList": [{"guid": "decision-guid-1"}],
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    client = InfoSudSourceClient(base_url="https://obcan.justice.sk", retry_backoff_seconds=0)

    page = client.list_decision_page(page=0, size=25)

    assert page.total == 123
    assert page.source_updated_at == "22.08.2026"
    assert [ref.guid for ref in page.refs] == ["decision-guid-1"]
    assert calls[0][1]["params"] == {"page": 1, "size": 25}


def test_infosud_detail_failure_logs_hashed_guid_without_raw_identifier(monkeypatch) -> None:
    messages = []
    guid = "raw-guid-value"
    expected_hash = sha256(guid.encode("utf-8")).hexdigest()[:12]

    def fake_get(url, **kwargs):
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    client = InfoSudSourceClient(
        base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
        timeout_seconds=45,
        retry_attempts=1,
        retry_backoff_seconds=0,
        progress_logger=messages.append,
    )

    try:
        client.get_decision(guid)
    except httpx.ReadTimeout:
        pass

    assert any(
        (
            "infosud_source_request_failed stage=get_decision "
            f"guid_hash={expected_hash} attempt=1 max_attempts=1"
        )
        in message
        for message in messages
    )
    assert not any(guid in message for message in messages)


def test_pseudonymization_removes_common_person_names() -> None:
    text = "Jan Novak byva na ulici Hlavna 12 a narodil sa 01.01.1980."

    sanitized = pseudonymize_court_decision_text(text)

    assert "Jan Novak" not in sanitized
    assert "01.01.1980" not in sanitized


def test_infosud_payload_maps_to_record_with_public_text() -> None:
    payload = {
        "guid": "abc",
        "sud": {"nazov": "Okresny sud Zilina", "typSudu": "Okresny sud"},
        "spisovaZnacka": "1C/2/2024",
        "ecli": "ECLI:SK:OSZA:2024:1",
        "text": "Sud rozhodol vo veci Jan Novak proti Eva Kovacova.",
    }

    record = record_from_infosud_payload(
        payload,
        source_base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
    )

    assert record.source_guid == "abc"
    assert record.court_name == "Okresny sud Zilina"
    assert "Jan Novak" not in record.public_text


def test_infosud_payload_prefers_original_issuing_court_after_court_reorganization() -> None:
    payload = {
        "guid": "kezmarok-origin",
        "sud": {"nazov": "Okresný súd Poprad", "registreGuid": "sud_160"},
        "povodnySud": {"nazov": "Okresný súd Kežmarok", "registreGuid": "sud_159"},
        "ecli": "ECLI:SK:OSKK:2013:8413010378.1",
        "datumVydania": "14.11.2013",
    }

    record = record_from_infosud_payload(
        payload,
        source_base_url="https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
    )

    assert record.court_name == "Okresný súd Kežmarok"


def test_service_logs_current_processing_decision() -> None:
    messages = []
    store = FakeStore()
    service = CourtDecisionCollectorService(store=store, progress_logger=messages.append)

    summary = service.sync_records(sample_court_decision_records())

    assert summary.processed == 1
    assert store.saved[0].source_guid == "fixture-sk-decision-1"
    expected_hash = sha256(b"fixture-sk-decision-1").hexdigest()[:16]
    assert any(f"reference_hash={expected_hash} year=2024" in item for item in messages)
    assert any(f"reference_hash={expected_hash} work_class=manual status=created" in item for item in messages)
    assert not any("fixture-sk-decision-1" in item for item in messages)
    assert not any("12C/34/2024" in item for item in messages)


def test_priority_backfill_resumes_from_persisted_page_after_restart() -> None:
    messages = []
    store = FakeStore()
    source = FixtureCourtDecisionSource()
    service = CourtDecisionCollectorService(store=store, source=source, progress_logger=messages.append)

    first = service.run_priority_cycle(page_size=1, backfill_pages_per_cycle=1)

    assert first.processed == 1
    assert store.scheduler.backfill_next_page == 1

    restarted = CourtDecisionCollectorService(store=store, source=source, progress_logger=messages.append)
    second = restarted.run_priority_cycle(page_size=1, backfill_pages_per_cycle=2)

    assert second.processed == 2
    assert [record.source_guid for record in store.saved] == [
        "fixture-sk-decision-1",
        "fixture-sk-decision-2",
        "fixture-sk-decision-3",
    ]
    assert store.scheduler.backfill_next_page == 0
    assert store.scheduler.backfill_generation == 1


def test_new_overflow_stays_priority_until_next_utc_day_before_backfill() -> None:
    store = FakeStore()
    original = sample_court_decision_records()
    initial_source = FixtureCourtDecisionSource(records=original)
    clock = [datetime(2026, 8, 22, 1, tzinfo=timezone.utc)]
    service = CourtDecisionCollectorService(store=store, source=initial_source, utc_now=lambda: clock[0])
    service.run_priority_cycle(page_size=2, backfill_pages_per_cycle=1)

    expanded_records = FixtureCourtDecisionSource().records + [
        replace(
            original[0],
            source_guid=f"fixture-sk-new-{index}",
            ecli=f"ECLI:SK:NEW:2026:{index}",
            file_number=f"NEW/{index}/2026",
        )
        for index in range(1, 3)
    ]
    expanded_source = FixtureCourtDecisionSource(records=expanded_records)
    service = CourtDecisionCollectorService(store=store, source=expanded_source, utc_now=lambda: clock[0])

    first_day = service.run_priority_cycle(
        page_size=2,
        daily_new_limit=2,
        discovery_overlap_pages=1,
        backfill_pages_per_cycle=10,
    )

    assert first_day.created == 2
    assert store.scheduler.quota_used == 2
    assert store.pending_work_count(source_system="infosud", work_class="new") == 2
    assert store.scheduler.backfill_generation == 1

    same_day = service.run_priority_cycle(page_size=2, daily_new_limit=2, backfill_pages_per_cycle=10)
    assert same_day.processed == 0
    assert store.pending_work_count(source_system="infosud", work_class="new") == 2

    clock[0] = datetime(2026, 8, 23, 0, 1, tzinfo=timezone.utc)
    next_day = service.run_priority_cycle(page_size=2, daily_new_limit=2, backfill_pages_per_cycle=1)
    assert next_day.created == 2
    assert store.pending_work_count(source_system="infosud", work_class="new") == 0
    assert store.scheduler.quota_day == date(2026, 8, 23)
    assert store.scheduler.quota_used == 2


def test_source_metadata_change_rechecks_overlap_and_only_real_update_uses_quota() -> None:
    class UpdatedMetadataSource(FixtureCourtDecisionSource):
        def list_decision_page(self, *, page=0, size=25):
            result = super().list_decision_page(page=page, size=size)
            return replace(result, source_updated_at="fixture-v2")

    original = sample_court_decision_records()[0]
    store = FakeStore()
    service = CourtDecisionCollectorService(
        store=store,
        source=FixtureCourtDecisionSource(records=[original]),
    )
    service.run_priority_cycle(page_size=1, backfill_pages_per_cycle=1)

    unchanged = CourtDecisionCollectorService(
        store=store,
        source=UpdatedMetadataSource(records=[original]),
    ).run_priority_cycle(page_size=1, daily_new_limit=1, backfill_pages_per_cycle=0)

    assert unchanged.unchanged == 1
    assert store.scheduler.quota_used == 0

    updated_record = replace(original, update_date="2026-08-22", raw_text=original.raw_text + " update")

    class LaterMetadataSource(FixtureCourtDecisionSource):
        def list_decision_page(self, *, page=0, size=25):
            result = super().list_decision_page(page=page, size=size)
            return replace(result, source_updated_at="fixture-v3")

    updated = CourtDecisionCollectorService(
        store=store,
        source=LaterMetadataSource(records=[updated_record]),
    ).run_priority_cycle(page_size=1, daily_new_limit=1, backfill_pages_per_cycle=0)

    assert updated.updated == 1
    assert store.scheduler.quota_used == 1


def test_source_total_regression_is_degraded_not_up_to_date() -> None:
    store = FakeStore()
    full_source = FixtureCourtDecisionSource()
    service = CourtDecisionCollectorService(store=store, source=full_source)
    service.run_priority_cycle(page_size=1, backfill_pages_per_cycle=1)

    regressed_source = FixtureCourtDecisionSource(records=full_source.records[:2])
    regressed = CourtDecisionCollectorService(store=store, source=regressed_source)
    summary = regressed.run_priority_cycle(page_size=1, backfill_pages_per_cycle=1)

    assert summary.processed == 0
    assert store.scheduler.status == "degraded_source_total_regressed"
    assert store.checkpoint_failures == 1


def test_missing_expected_backfill_page_is_degraded() -> None:
    class MissingPageSource(FixtureCourtDecisionSource):
        def list_decision_page(self, *, page=0, size=25):
            result = super().list_decision_page(page=page, size=size)
            if page == 1:
                return InfoSudDecisionPage(refs=(), page=page, size=size, total=len(self.records))
            return result

    store = FakeStore()
    source = MissingPageSource()
    service = CourtDecisionCollectorService(store=store, source=source)
    first_page = source.list_decision_page(page=0, size=1)
    store.ensure_scheduler_state(
        source_system="infosud",
        source_total=first_page.total,
        source_updated_at="fixture",
        page_size=1,
        daily_new_limit=10000,
        utc_day=date(2026, 8, 22),
        overlap_pages=1,
    )
    store.scheduler = replace(store.scheduler, backfill_next_page=1)

    summary = service.run_priority_cycle(page_size=1, backfill_pages_per_cycle=1)

    assert summary.processed == 0
    assert store.scheduler.status == "degraded_backfill_page_missing"
    assert store.checkpoint_failures == 1


def test_worker_loop_waits_after_priority_cycle_is_idle() -> None:
    messages = []
    sleeps = []
    store = FakeStore()
    source = FixtureCourtDecisionSource(records=[])
    service = CourtDecisionCollectorService(store=store, source=source, progress_logger=messages.append)

    summary = service.run_worker_loop(
        page_size=1,
        poll_seconds=30,
        backfill_pages_per_cycle=1,
        max_idle_cycles=1,
        sleep_fn=sleeps.append,
    )

    assert summary.processed == 0
    assert sleeps == []
    assert store.scheduler.status == "backfill_cycle_complete"
    assert any("waiting_for_new_judicial_decisions status=backfill_cycle_complete" in item for item in messages)
