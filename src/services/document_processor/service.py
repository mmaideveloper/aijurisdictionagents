from __future__ import annotations

from dataclasses import dataclass
import logging
import time
import uuid

from aijurisdictionagents.api_db import ApiDatabaseStore, CaseDocument, CaseDocumentChunk
from aijurisdictionagents.llm import EmbeddingClient, get_embedding_client

from .runtime import (
    chunk_document_text,
    extract_document_text,
    serialize_embedding_vector,
)

logger = logging.getLogger("document-processor")


@dataclass(frozen=True)
class ProcessedDocumentResult:
    doc_id: str
    case_id: str
    original_filename: str
    status: str
    extracted_characters: int
    extraction_method: str | None = None


class DocumentProcessor:
    """Best-effort document extraction + model-backed embeddings for full docs and chunks."""

    def __init__(self, store: ApiDatabaseStore, embedding_client: EmbeddingClient | None = None) -> None:
        self.store = store
        self.embedding_client = embedding_client or get_embedding_client()

    def run_once(self, *, limit: int = 20, max_running_seconds: float = 0) -> list[ProcessedDocumentResult]:
        documents = self.store.list_unprocessed_case_documents(limit=limit)
        return self.process_documents(documents, max_running_seconds=max_running_seconds)

    def process_documents(
        self,
        documents: list[CaseDocument],
        *,
        max_running_seconds: float = 0,
    ) -> list[ProcessedDocumentResult]:
        results: list[ProcessedDocumentResult] = []
        started_at = time.monotonic()
        for document in documents:
            if max_running_seconds > 0 and (time.monotonic() - started_at) >= max_running_seconds:
                logger.info(
                    "[document-processor] worker stopped after max running time "
                    "max_running_seconds=%.1f processed_documents=%s",
                    max_running_seconds,
                    len(results),
                )
                break
            self.store.mark_document_processing(doc_id=document.doc_id, status='processing', error=None)
            try:
                payload = self.store.read_storage_bytes(storage_uri=document.storage_uri)
                extracted = extract_document_text(
                    filename=document.original_filename,
                    payload=payload,
                )
                chunks = chunk_document_text(extracted.text)
                if not chunks:
                    fallback_text = extracted.text.strip() or document.original_filename
                    chunks = chunk_document_text(fallback_text)
                if not chunks:
                    raise ValueError("Document chunking produced no retrievable text.")
                chunk_batch = self.embedding_client.embed_texts([chunk.text for chunk in chunks])
                document_batch = self.embedding_client.embed_texts([extracted.text])
                document_vector = serialize_embedding_vector(document_batch.vectors[0])
                chunk_records = [
                    CaseDocumentChunk(
                        chunk_id=str(uuid.uuid4()),
                        doc_id=document.doc_id,
                        case_id=document.case_id,
                        chunk_index=chunk.chunk_index,
                        chunk_text=chunk.text,
                        embedding_vector=serialize_embedding_vector(vector),
                        embedding_model=chunk_batch.model_name,
                        embedding_dimensions=len(vector),
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        created_at=_now_iso(),
                        updated_at=_now_iso(),
                    )
                    for chunk, vector in zip(chunks, chunk_batch.vectors, strict=True)
                ]
                self.store.upsert_document_content(
                    doc_id=document.doc_id,
                    case_id=document.case_id,
                    extracted_text=extracted.text,
                    embedding_vector=document_vector,
                    embedding_model=document_batch.model_name,
                    embedding_dimensions=len(document_batch.vectors[0]),
                )
                self.store.replace_document_chunks(
                    doc_id=document.doc_id,
                    case_id=document.case_id,
                    chunks=chunk_records,
                )
                self.store.mark_document_processing(doc_id=document.doc_id, status='processed', error=None)
                results.append(
                    ProcessedDocumentResult(
                        doc_id=document.doc_id,
                        case_id=document.case_id,
                        original_filename=document.original_filename,
                        status='processed',
                        extracted_characters=len(extracted.text),
                        extraction_method=extracted.extraction_method,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                self.store.mark_document_processing(doc_id=document.doc_id, status='failed', error=str(exc)[:500])
                logger.warning(
                    "[document-processor] document failed "
                    "doc_id=%s case_id=%s original_filename=%s error=%s",
                    document.doc_id,
                    document.case_id,
                    document.original_filename,
                    str(exc)[:500],
                )
                results.append(
                    ProcessedDocumentResult(
                        doc_id=document.doc_id,
                        case_id=document.case_id,
                        original_filename=document.original_filename,
                        status='failed',
                        extracted_characters=0,
                        extraction_method=None,
                    )
                )
        return results


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
