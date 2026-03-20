from __future__ import annotations

from aijurisdictionagents.api_db import ApiDatabaseStore

from .service import DocumentProcessor, ProcessedDocumentResult


def run_document_processor(*, limit: int = 20) -> list[ProcessedDocumentResult]:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return DocumentProcessor(store).run_once(limit=limit)
