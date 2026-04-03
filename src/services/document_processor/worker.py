from __future__ import annotations

import logging

from aijurisdictionagents import __version__
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm import load_embedding_runtime_summary_from_env
from aijurisdictionagents.telemetry import configure_worker_telemetry

from .service import DocumentProcessor, ProcessedDocumentResult

logger = logging.getLogger("document-processor")


def run_document_processor(*, limit: int = 20) -> list[ProcessedDocumentResult]:
    telemetry_mode = configure_worker_telemetry(
        service_name="document-processor",
        service_version=__version__,
        logger_name="document-processor",
    )
    embedding_runtime = load_embedding_runtime_summary_from_env()
    logger.info(
        "[document-processor] startup "
        f"telemetry_mode={telemetry_mode} "
        f"embedding_option={embedding_runtime.option} "
        f"embedding_model={embedding_runtime.model}"
    )
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return DocumentProcessor(store).run_once(limit=limit)
