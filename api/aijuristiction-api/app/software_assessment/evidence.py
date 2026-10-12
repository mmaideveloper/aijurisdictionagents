"""Extract bounded page/paragraph evidence from original, case-authorized uploads."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from aijurisdictionagents.api_db import ApiDatabaseStore
from pypdf import PdfReader
from services.document_processor.uploads import extract_docx, validate_upload

from app.software_assessment.models import Evidence

MAX_TOTAL_CHARS = 100000


def extract_evidence(store: ApiDatabaseStore, case_id: str, document_ids: list[str]) -> list[Evidence]:
    items: list[Evidence] = []
    total = 0
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("Select each document once.")
    for doc_id in document_ids:
        document = store.get_case_document(case_id=case_id, doc_id=doc_id)
        if document.kind != "uploaded":
            raise ValueError("Select original uploaded supplier or software documents.")
        payload = store.read_storage_bytes(storage_uri=document.storage_uri)
        validate_upload(document.original_filename, payload)
        digest = hashlib.sha256(payload).hexdigest()
        suffix = Path(document.original_filename).suffix.lower()
        chunks: list[tuple[int | None, str, str]]
        if suffix == ".pdf":
            chunks = [(index, f"Page {index}", page.extract_text() or "")
                      for index, page in enumerate(PdfReader(io.BytesIO(payload)).pages, 1)]
        elif suffix == ".docx":
            chunks = [(None, f"Paragraph {index}", text)
                      for index, text in enumerate(extract_docx(payload).split("\n\n"), 1)]
        elif suffix in {".txt", ".md", ".json", ".csv", ".html", ".xml"}:
            chunks = [(None, f"Paragraph {index}", text)
                      for index, text in enumerate(payload.decode("utf-8-sig").split("\n\n"), 1)]
        else:
            chunks = [(None, "Image", "")]
        for page_number, section, text in chunks:
            total += len(text)
            if total > MAX_TOTAL_CHARS or len(text) > 12000 or len(items) >= 200:
                raise ValueError("Evidence exceeds assessment limits. Split documents or select fewer files.")
            items.append(Evidence(
                evidence_id=f"d{len(items) + 1}", document_id=doc_id,
                filename=document.original_filename, version=document.version,
                content_hash=digest, page=page_number, section=section, text=text,
                uncertainty="Unreadable/scanned evidence: inspect the original; no page text was assessed."
                if not text.strip() else "DOCX/text pagination unavailable." if page_number is None else "",
            ))
    return items
