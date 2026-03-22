from __future__ import annotations

from dataclasses import dataclass

from aijurisdictionagents.api_db import ApiDatabaseStore

from .runtime import build_embedding_vector, extract_document_text


@dataclass(frozen=True)
class ProcessedDocumentResult:
    doc_id: str
    case_id: str
    original_filename: str
    status: str
    extracted_characters: int
    extraction_method: str | None = None


class DocumentProcessor:
    """Best-effort document extraction + deterministic embedding generation."""

    def __init__(self, store: ApiDatabaseStore) -> None:
        self.store = store

    def run_once(self, *, limit: int = 20) -> list[ProcessedDocumentResult]:
        documents = self.store.list_unprocessed_case_documents(limit=limit)
        return self.process_documents(documents)

    def process_documents(self, documents: list) -> list[ProcessedDocumentResult]:
        results: list[ProcessedDocumentResult] = []
        for document in documents:
            self.store.mark_document_processing(doc_id=document.doc_id, status='processing', error=None)
            try:
                payload = self.store.read_storage_bytes(storage_uri=document.storage_uri)
                extracted = extract_document_text(
                    filename=document.original_filename,
                    payload=payload,
                )
                embedding_vector = build_embedding_vector(extracted.text)
                self.store.upsert_document_content(
                    doc_id=document.doc_id,
                    case_id=document.case_id,
                    extracted_text=extracted.text,
                    embedding_vector=embedding_vector,
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
