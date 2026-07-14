from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from aijurisdictionagents.llm.embeddings import EmbeddingBatchResult
from services.court_decision_collector.domain import CourtDecisionRecord, StoredCourtDecision
from services.court_decision_collector.enrichment import OnDemandCourtDecisionEnricher, build_local_extract_summary


class FakeEmbeddingClient:
    model_name = "local-test-model"

    def embed_texts(self, texts):
        return EmbeddingBatchResult(model_name=self.model_name, vectors=[[float(i), 1.0] for i, _ in enumerate(texts)])


class FakeSource:
    base_url = "https://obcan.justice.sk/pilot/api/ress-isu-service/v1"
    timeout_seconds = 5
    tls_verify = True

    def __init__(self, record):
        self.record = record
        self.calls = 0

    def get_decision(self, guid):
        self.calls += 1
        assert guid == self.record.source_guid
        return self.record


class FakeStore:
    def __init__(self):
        self.cached = None
        self.saved = None

    def upsert_decision(self, record):
        return StoredCourtDecision("decision-1", "version-1", "created")

    def get_enrichment(self, *, version_id):
        return self.cached

    def mark_enrichment_processing(self, **kwargs):
        self.processing = kwargs

    def save_enrichment(self, **kwargs):
        self.saved = kwargs

    def mark_enrichment_failed(self, **kwargs):
        self.failed = kwargs


def _pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


def _record(pdf_size: int) -> CourtDecisionRecord:
    guid = "24beca89-d93b-4cfc-b664-bb28148db9da:34712443-63f4-4a0e-96fe-60bec5bc06f0"
    return CourtDecisionRecord(
        source_system="infosud", source_guid=guid, court_name="Okresný súd Komárno",
        court_type="okresný", decision_form="Platobný rozkaz", nature="",
        file_number="7C/418/2013", case_number="4213203390",
        ecli="ECLI:SK:OSKN:2013:4213203390.1", issue_date="04.03.2013",
        indexed_at="", update_date="26.09.2023",
        source_url=f"https://obcan.justice.sk/pilot/api/ress-isu-service/v1/rozhodnutie/{guid}",
        raw_text="Platobný rozkaz 7C/418/2013", pseudonymized_text="Platobný rozkaz 7C/418/2013",
        metadata={"guid": guid, "sud": {"nazov": "Okresný súd Komárno"},
                  "dokument": {"name": "Platobný_rozkaz_7C-418-2013.pdf", "size": pdf_size,
                  "url": "https://obcan.justice.sk/content/public/item/34712443-63f4-4a0e-96fe-60bec5bc06f0"}},
    )


def test_cache_miss_downloads_validates_and_persists_enrichment(tmp_path: Path) -> None:
    payload = _pdf()
    store = FakeStore()
    record = _record(len(payload))
    result = OnDemandCourtDecisionEnricher(
        store=store, source=FakeSource(record), storage_root=tmp_path,
        embedding_client=FakeEmbeddingClient(), downloader=lambda _url: payload,
    ).enrich_source_url(record.source_url)
    assert result.status == "ready"
    assert result.cache_hit is False
    assert Path(result.pdf_path).read_bytes().startswith(b"%PDF-")
    assert store.processing["metadata"]["guid"] == record.source_guid
    assert store.saved["embedding_model"] == "local-test-model"
    assert store.saved["pseudonymized_text"]


def test_rejects_non_infosud_source_url_before_fetch(tmp_path: Path) -> None:
    payload = _pdf()
    with pytest.raises(ValueError, match="allowlisted"):
        OnDemandCourtDecisionEnricher(
            store=FakeStore(), source=FakeSource(_record(len(payload))), storage_root=tmp_path,
            embedding_client=FakeEmbeddingClient(), downloader=lambda _url: payload,
        ).enrich_source_url("https://attacker.example/decision/123")


def test_rejects_invalid_pdf_signature(tmp_path: Path) -> None:
    record = _record(8)
    store = FakeStore()
    with pytest.raises(ValueError, match="PDF signature"):
        OnDemandCourtDecisionEnricher(
            store=store, source=FakeSource(record), storage_root=tmp_path,
            embedding_client=FakeEmbeddingClient(), downloader=lambda _url: b"not-pdf!",
        ).enrich_source_url(record.source_url)
    assert store.failed["error_type"] == "ValueError"


def test_summary_prefers_outcome_and_omits_party_preamble() -> None:
    summary = build_local_extract_summary(
        "Navrhovateľ Example s.r.o., IČO: 00 170 984, adresa 940 53 Nové Zámky. "
        "Súd rozhodol: Odporca je povinný zaplatiť 783,77 eur do 15 dní."
    )
    assert summary.startswith("Výrok rozhodnutia:")
    assert "Navrhovateľ" not in summary
    assert "IČO" not in summary
