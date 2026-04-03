from __future__ import annotations

import logging

from services.document_processor import worker


def test_document_processor_logs_embedding_runtime_on_startup(monkeypatch, caplog) -> None:
    class FakeStore:
        def initialize(self) -> None:
            return None

    class FakeProcessor:
        def __init__(self, store: FakeStore) -> None:
            self._store = store

        def run_once(self, *, limit: int) -> list[object]:
            assert limit == 3
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
