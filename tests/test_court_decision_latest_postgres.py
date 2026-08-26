from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from services.court_decision_collector.domain import CourtDecisionRecord
from services.court_decision_collector.postgres_store import PostgresCourtDecisionStore


def _connection_uri() -> str:
    return os.getenv(
        "COURT_DECISIONS_DB_CLOUD",
        "postgresql://postgres:postgres@127.0.0.1:5432/court_decisions_sk",
    )


@pytest.mark.skipif(
    os.getenv("RUN_LOCAL_POSTGRES_COURT_LATEST_TEST") != "1",
    reason="Set RUN_LOCAL_POSTGRES_COURT_LATEST_TEST=1 for the synthetic PostgreSQL check.",
)
def test_topic_free_latest_returns_newest_metadata_without_body_match() -> None:
    run_id = uuid.uuid4().hex
    source_system = f"synthetic-issue-651-{run_id}"
    court_name = f"Synthetic Court {run_id}"
    store = PostgresCourtDecisionStore(connection_uri=_connection_uri())
    expected_dates = [
        "2026-08-20",
        "2026-08-19",
        "2026-08-18",
        "2026-08-17",
        "2026-08-16",
    ]
    dates = [*expected_dates, "2026-08-15"]

    try:
        for index, issue_date in enumerate(dates, start=1):
            decision_form = "uznesenie" if index == 1 else "rozsudok"
            metadata_text = f"{decision_form} {index}Synthetic/2026 ECLI:SK:SYNTH:2026:{index}.1"
            store.upsert_decision(
                CourtDecisionRecord(
                    source_system=source_system,
                    source_guid=f"{run_id}-{index}",
                    court_name=court_name,
                    court_type="synthetic",
                    decision_form=decision_form,
                    nature="synthetic",
                    file_number=f"{index}Synthetic/2026",
                    case_number=f"synthetic-{index}",
                    ecli=f"ECLI:SK:SYNTH:2026:{index}.1",
                    issue_date=issue_date,
                    indexed_at=issue_date,
                    update_date=issue_date,
                    source_url=f"https://example.test/{run_id}/{index}",
                    raw_text=metadata_text,
                    pseudonymized_text=metadata_text,
                    metadata={"synthetic": True, "run_id": run_id},
                )
            )

        results = store.search(
            query="Zobraz 5 posledn\u00fdch s\u00fadnych rozhodnut\u00ed.",
            court_name=court_name,
            limit=5,
            sort="latest",
        )

        assert [result.issue_date for result in results] == expected_dates
        assert results[0].file_number == "1Synthetic/2026"
        assert all(result.content_source == "metadata_only" for result in results)
        assert all(result.snippet == "" and result.summary == "" for result in results)
    finally:
        with psycopg.connect(_connection_uri()) as conn:
            conn.execute(
                "DELETE FROM court_decision_documents WHERE source_system = %s",
                (source_system,),
            )
            conn.commit()
