from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import os
from pathlib import Path
import uuid

import psycopg
import pytest

from aijurisdictionagents.llm.embeddings import EmbeddingBatchResult
from services.court_decision_collector.config import CourtDecisionCollectorConfig
from services.court_decision_collector.domain import CourtDecisionRecord
from services.court_decision_collector.enrichment import OnDemandCourtDecisionEnricher
from services.court_decision_collector.enrichment_queue import BackgroundCourtDecisionEnricher
from services.court_decision_collector.postgres_store import PostgresCourtDecisionStore


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOCAL_POSTGRES_COURT_ENRICHMENT_TEST", "").strip() != "1",
    reason="Set RUN_LOCAL_POSTGRES_COURT_ENRICHMENT_TEST=1 for local PostgreSQL integration.",
)


class FakeEmbeddingClient:
    def embed_texts(self, texts):
        return EmbeddingBatchResult(
            model_name="synthetic-local-embedding",
            vectors=[[float(index + 1), 1.0] for index, _text in enumerate(texts)],
        )


class SyntheticSource:
    source_system = "infosud"
    base_url = "https://obcan.justice.sk/pilot/api/ress-isu-service/v1"
    timeout_seconds = 5
    tls_verify = True

    def __init__(self, record: CourtDecisionRecord) -> None:
        self.record = record

    def get_decision(self, guid: str) -> CourtDecisionRecord:
        assert guid == self.record.source_guid
        return self.record


def _pdf() -> bytes:
    from reportlab.pdfgen import canvas

    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 760, "Kupna zmluva a prevod vlastnickeho prava k nehnutelnosti.")
    document.drawString(72, 740, "Sud rozhodol o platnosti zmluvy a povinnosti zaplatit cenu.")
    document.save()
    return output.getvalue()


def _record(run_id: str, payload_size: int) -> CourtDecisionRecord:
    guid = f"{uuid.uuid4()}:{uuid.uuid4()}"
    return CourtDecisionRecord(
        source_system=f"synthetic-issue-652-{run_id}",
        source_guid=guid,
        court_name="Synthetic District Court",
        court_type="synthetic",
        decision_form="rozsudok",
        nature="synthetic",
        file_number="Synthetic/652",
        case_number="synthetic-652",
        ecli="ECLI:SK:SYNTH:652.1",
        issue_date="2026-08-25",
        indexed_at="2026-08-25",
        update_date="2026-08-25",
        source_url=(
            "https://obcan.justice.sk/pilot/api/ress-isu-service/v1/rozhodnutie/" + guid
        ),
        raw_text="synthetic metadata",
        pseudonymized_text="synthetic metadata",
        metadata={
            "synthetic": True,
            "dokument": {
                "name": "synthetic-652.pdf",
                "size": payload_size,
                "url": f"https://obcan.justice.sk/content/public/item/{uuid.uuid4()}",
            },
        },
    )


def test_postgres_queue_reaches_ready_and_reclaims_expired_lease(
    monkeypatch, tmp_path: Path
) -> None:
    connection_uri = os.getenv(
        "COURT_DECISIONS_TEST_DB_CLOUD",
        "postgresql://postgres:postgres@127.0.0.1:5432/court_decisions_sk",
    )
    run_id = uuid.uuid4().hex[:12]
    payload = _pdf()
    record = _record(run_id, len(payload))
    store = PostgresCourtDecisionStore(connection_uri=connection_uri)
    store.initialize()
    stored = store.upsert_decision(record, work_class="new")
    try:
        store.enqueue_enrichment(
            decision_id=stored.decision_id,
            version_id=stored.version_id,
            priority_class="recent",
            max_attempts=3,
        )
        monkeypatch.setenv("COURT_DECISIONS_DB_CLOUD", connection_uri)
        monkeypatch.setenv("COURT_DECISIONS_STORAGE_LOCAL", str(tmp_path))
        monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_ENABLED", "true")
        monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_CYCLE_LIMIT", "1")
        monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_CANDIDATE_LIMIT", "1")
        monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_RATE_DELAY_SECONDS", "0")
        monkeypatch.setenv("COURT_DECISIONS_ENRICHMENT_MIN_FREE_DISK_BYTES", "0")
        config = CourtDecisionCollectorConfig.from_env()
        source = SyntheticSource(record)
        enricher = OnDemandCourtDecisionEnricher(
            store=store,
            source=source,
            storage_root=tmp_path,
            embedding_client=FakeEmbeddingClient(),
            downloader=lambda _url: payload,
        )
        summary = BackgroundCourtDecisionEnricher(
            store=store,
            enricher=enricher,
            config=config,
            sleep_fn=lambda _seconds: None,
            free_disk_fn=lambda _path: 10_000,
        ).run_cycle()
        assert summary.ready == 1
        enrichment = store.get_enrichment(version_id=stored.version_id)
        assert enrichment is not None
        assert enrichment["status"] == "ready"
        assert int(enrichment["chunk_count"]) >= 1

        second = store.upsert_decision(
            replace(record, source_guid=f"{uuid.uuid4()}:{uuid.uuid4()}", ecli="ECLI:SK:SYNTH:652.2")
        )
        store.enqueue_enrichment(
            decision_id=second.decision_id,
            version_id=second.version_id,
            priority_class="user_requested",
            max_attempts=3,
        )
        first_claim = store.claim_next_enrichment(lease_seconds=30)
        assert first_claim is not None and first_claim.version_id == second.version_id
        with psycopg.connect(connection_uri) as conn:
            conn.execute(
                "UPDATE court_decision_enrichment_queue SET lease_expires_at='2000-01-01T00:00:00Z' "
                "WHERE version_id=%s",
                (second.version_id,),
            )
            conn.commit()
        reclaimed = PostgresCourtDecisionStore(connection_uri=connection_uri).claim_next_enrichment(
            lease_seconds=30
        )
        assert reclaimed is not None and reclaimed.version_id == second.version_id
        assert reclaimed.attempt_count == 2
    finally:
        with psycopg.connect(connection_uri) as conn:
            conn.execute(
                "DELETE FROM court_decision_documents WHERE source_system LIKE %s",
                (f"synthetic-issue-652-{run_id}%",),
            )
            conn.commit()
