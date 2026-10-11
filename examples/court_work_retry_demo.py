"""Synthetic retry/review demo; add --postgres for an isolated local database."""
import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import uuid

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from services.court_decision_collector.retry import schedule_retry
from services.court_decision_collector.config import CourtDecisionCollectorConfig
from services.court_decision_collector.postgres_store import PostgresCourtDecisionStore
from services.court_decision_collector.source_review import inspect_reference


def postgres_demo() -> None:
    config = CourtDecisionCollectorConfig.from_env()
    config.validate()
    settings = conninfo_to_dict(config.db_cloud)
    if settings.get("host") not in {"127.0.0.1", "localhost", "::1"} or settings.get("hostaddr"):
        raise ValueError("demo requires loopback PostgreSQL")
    database = "court_889_demo_" + uuid.uuid4().hex
    with psycopg.connect(config.db_cloud, autocommit=True, connect_timeout=3) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            store = PostgresCourtDecisionStore(connection_uri=make_conninfo(
                config.db_cloud, dbname=database, options="",
            ))
            store.initialize()
            store.ensure_scheduler_state(
                source_system="infosud", source_total=1, source_updated_at="synthetic",
                page_size=25, daily_new_limit=10, utc_day=date.today(), overlap_pages=1,
            )
            store.enqueue_work_page(source_system="infosud", work_class="new", source_page=0,
                                    entries=[("synthetic-missing", 0, True)])
            item = store.next_work_item(source_system="infosud", work_class="new")
            assert item is not None
            store.mark_work_retry(item, error_type="source_missing", http_status=404)
            evidence = sha256(b"synthetic-human-review").hexdigest()
            reviewer = sha256(b"synthetic-reviewer").hexdigest()
            for unavailable in (True, False):
                store.review_work_availability(
                    source_system="infosud", source_guid=item.source_guid, unavailable=unavailable,
                    evidence_category="operator_verified_unavailable" if unavailable else "operator_requeue",
                    evidence_sha256=evidence, reviewer_sha256=reviewer,
                )
                eligible = store.next_work_item(source_system="infosud", work_class="new") is not None
                assert eligible != unavailable
                print(json.dumps({"source_unavailable": unavailable, "eligible": eligible}))
        finally:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    retry = schedule_retry(httpx.ConnectError("synthetic"), attempt=1,
                           reference="synthetic", now=datetime.now(timezone.utc))
    print(retry)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client:
        print(json.dumps(inspect_reference(client, source_guid="synthetic", page=0, size=25)))
    if args.postgres:
        postgres_demo()
