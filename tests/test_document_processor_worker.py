from __future__ import annotations

import logging
import uuid

from services.document_processor import worker
from services.document_processor import service as document_processor_service
from services.document_processor.service import DocumentProcessor


class _FakeCaseDocument:
    def __init__(self) -> None:
        self.doc_id = str(uuid.uuid4())
        self.case_id = str(uuid.uuid4())
        self.original_filename = "bad.pdf"
        self.storage_uri = "memory://bad.pdf"


def test_document_processor_logs_embedding_runtime_on_startup(monkeypatch, caplog) -> None:
    class FakeStore:
        def initialize(self) -> None:
            return None

    class FakeProcessor:
        def __init__(self, store: FakeStore) -> None:
            self._store = store

        def run_once(self, *, limit: int, max_running_seconds: float = 0) -> list[object]:
            assert limit == 3
            assert max_running_seconds == 0
            return []

    fake_store = FakeStore()
    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL_OPTION", "local")
    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    caplog.set_level(logging.INFO, logger="document-processor")
    monkeypatch.setattr(worker.ApiDatabaseStore, "from_env", lambda: fake_store)
    monkeypatch.setattr(worker, "DocumentProcessor", FakeProcessor)

    worker.run_document_processor(limit=3)

    output = caplog.text

    assert "[document-processor] startup" in output
    assert "embedding_option=local" in output
    assert "embedding_model=all-MiniLM-L6-v2" in output
    assert "embedding_device=" in output


def test_document_processor_reads_azure_max_running_time(monkeypatch) -> None:
    class FakeStore:
        def initialize(self) -> None:
            return None

    observed_max_running_seconds: list[float] = []

    class FakeProcessor:
        def __init__(self, store: FakeStore) -> None:
            self._store = store

        def run_once(self, *, limit: int, max_running_seconds: float = 0) -> list[object]:
            observed_max_running_seconds.append(max_running_seconds)
            assert limit == 2
            return []

    fake_store = FakeStore()
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("DB_OPTION", "azure")
    monkeypatch.setenv("DOCUMENT_PROCESSOR_MAX_RUNNING_TIME", "60")
    monkeypatch.setattr(worker.ApiDatabaseStore, "from_env", lambda: fake_store)
    monkeypatch.setattr(worker, "DocumentProcessor", FakeProcessor)

    worker.run_document_processor(limit=2)

    assert observed_max_running_seconds == [3600]


def test_document_processor_default_max_running_time_is_15(monkeypatch) -> None:
    monkeypatch.delenv("DOCUMENT_PROCESSOR_MAX_RUNNING_TIME", raising=False)

    assert worker._load_max_running_minutes() == 15


def test_document_processor_logs_failure_reason(monkeypatch, caplog) -> None:
    class FakeStore:
        def __init__(self, document: _FakeCaseDocument) -> None:
            self.document = document
            self.status_updates: list[tuple[str, str, str | None]] = []

        def mark_document_processing(self, *, doc_id: str, status: str, error: str | None = None) -> None:
            self.status_updates.append((doc_id, status, error))

        def read_storage_bytes(self, *, storage_uri: str) -> bytes:
            assert storage_uri == "memory://bad.pdf"
            return b"%PDF-1.7"

    class FakeEmbeddingClient:
        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("embedding client should not be called")

    document = _FakeCaseDocument()
    store = FakeStore(document)
    caplog.set_level(logging.INFO, logger="document-processor")
    def _raise_extraction_failure(*, filename: str, payload: bytes) -> object:
        raise ValueError("OCR engine unavailable")

    monkeypatch.setattr(document_processor_service, "extract_document_text", _raise_extraction_failure)

    processor = DocumentProcessor(store=store, embedding_client=FakeEmbeddingClient())
    results = processor.process_documents([document])

    assert results[0].status == "failed"
    assert "document failed" in caplog.text
    assert "OCR engine unavailable" in caplog.text
