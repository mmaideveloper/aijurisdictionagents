from __future__ import annotations

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm import load_embedding_runtime_summary_from_env

from .service import DocumentProcessor, ProcessedDocumentResult


def run_document_processor(*, limit: int = 20) -> list[ProcessedDocumentResult]:
    embedding_runtime = load_embedding_runtime_summary_from_env()
    print(
        "[document-processor] startup "
        f"embedding_option={embedding_runtime.option} "
        f"embedding_model={embedding_runtime.model}"
    )
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return DocumentProcessor(store).run_once(limit=limit)
