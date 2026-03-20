from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

from aijurisdictionagents.api_db import ApiDatabaseStore


@dataclass(frozen=True)
class ProcessedDocumentResult:
    doc_id: str
    case_id: str
    original_filename: str
    status: str
    extracted_characters: int


class DocumentProcessor:
    """Best-effort document extraction + deterministic embedding generation."""

    def __init__(self, store: ApiDatabaseStore) -> None:
        self.store = store

    def run_once(self, *, limit: int = 20) -> list[ProcessedDocumentResult]:
        results: list[ProcessedDocumentResult] = []
        for document in self.store.list_unprocessed_case_documents(limit=limit):
            self.store.mark_document_processing(doc_id=document.doc_id, status='processing', error=None)
            try:
                payload = self.store.read_storage_bytes(storage_uri=document.storage_uri)
                extracted_text = self._extract_text(filename=document.original_filename, payload=payload)
                embedding_vector = self._build_embedding_vector(extracted_text)
                self.store.upsert_document_content(
                    doc_id=document.doc_id,
                    case_id=document.case_id,
                    extracted_text=extracted_text,
                    embedding_vector=embedding_vector,
                )
                self.store.mark_document_processing(doc_id=document.doc_id, status='processed', error=None)
                results.append(
                    ProcessedDocumentResult(
                        doc_id=document.doc_id,
                        case_id=document.case_id,
                        original_filename=document.original_filename,
                        status='processed',
                        extracted_characters=len(extracted_text),
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
                    )
                )
        return results

    def _extract_text(self, *, filename: str, payload: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {'.txt', '.md', '.json', '.csv', '.html', '.xml'}:
            return payload.decode('utf-8', errors='replace')
        if suffix == '.pdf':
            try:
                from pypdf import PdfReader  # type: ignore[import-not-found]
            except Exception:
                return payload.decode('utf-8', errors='replace')
            text_parts: list[str] = []
            reader = PdfReader(io.BytesIO(payload))
            for page in reader.pages:
                text_parts.append(page.extract_text() or '')
            return '\n'.join(part for part in text_parts if part).strip() or f'PDF document: {filename}'
        return payload.decode('utf-8', errors='replace')

    def _build_embedding_vector(self, text: str, *, dimensions: int = 8) -> str:
        normalized = text.strip() or 'empty-document'
        digest = hashlib.sha256(normalized.encode('utf-8')).digest()
        values: list[float] = []
        for index in range(dimensions):
            chunk = digest[index * 4:(index + 1) * 4]
            integer = int.from_bytes(chunk, 'big', signed=False)
            values.append(round((integer / 2**32) * 2 - 1, 6))
        return json.dumps(values)
