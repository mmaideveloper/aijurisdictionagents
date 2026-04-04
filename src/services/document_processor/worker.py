from __future__ import annotations

import logging
import os

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
    max_running_minutes = _load_max_running_minutes()
    max_running_seconds = max_running_minutes * 60 if _is_azure_runtime() and max_running_minutes > 0 else 0
    if max_running_seconds > 0:
        logger.info(
            "[document-processor] max running time enabled "
            "max_running_minutes=%s",
            max_running_minutes,
        )
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return DocumentProcessor(store).run_once(
        limit=limit,
        max_running_seconds=max_running_seconds,
    )


def _load_max_running_minutes() -> int:
    value = int(os.getenv("DOCUMENT_PROCESSOR_MAX_RUNNING_TIME", "15"))
    if value < 0:
        raise ValueError("DOCUMENT_PROCESSOR_MAX_RUNNING_TIME must be >= 0")
    return value


def _is_azure_runtime() -> bool:
    return os.getenv("DB_OPTION", "").strip().lower() == "azure"
