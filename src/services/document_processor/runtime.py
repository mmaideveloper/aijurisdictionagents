from __future__ import annotations

import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ExtractedDocumentContent:
    text: str
    extraction_method: str


def extract_document_text(*, filename: str, payload: bytes) -> ExtractedDocumentContent:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".json", ".csv", ".html", ".xml"}:
        return ExtractedDocumentContent(
            text=payload.decode("utf-8", errors="replace"),
            extraction_method="plain_text",
        )
    if suffix == ".pdf":
        direct_text = _extract_pdf_text(payload)
        if _has_meaningful_text(direct_text):
            return ExtractedDocumentContent(
                text=direct_text,
                extraction_method="pdf_text",
            )
        ocr_text = _extract_pdf_text_with_ocr(payload)
        if _has_meaningful_text(ocr_text):
            return ExtractedDocumentContent(
                text=ocr_text,
                extraction_method="pdf_ocr",
            )
        fallback = direct_text.strip() or f"PDF document: {filename}"
        return ExtractedDocumentContent(
            text=fallback,
            extraction_method="pdf_fallback",
        )
    return ExtractedDocumentContent(
        text=payload.decode("utf-8", errors="replace"),
        extraction_method="binary_decode",
    )


def build_embedding_vector(text: str, *, dimensions: int = 32) -> str:
    normalized = normalize_retrieval_text(text) or "empty-document"
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        chunk = digest[(index * 4) % len(digest) : ((index * 4) % len(digest)) + 4]
        if len(chunk) < 4:
            chunk = (chunk + digest)[:4]
        integer = int.from_bytes(chunk, "big", signed=False)
        values.append(round((integer / 2**32) * 2 - 1, 6))
    return json.dumps(values)


def parse_embedding_vector(raw: str) -> list[float]:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    values: list[float] = []
    for item in decoded:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            return []
    return values


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def normalize_retrieval_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^\w\s]+", " ", lowered, flags=re.UNICODE)
    lowered = re.sub(r"\s+", " ", lowered, flags=re.UNICODE)
    return lowered.strip()


def lexical_overlap_score(query: str, document_text: str) -> int:
    query_tokens = {
        token
        for token in normalize_retrieval_text(query).split()
        if len(token) >= 3
    }
    if not query_tokens:
        return 0
    document_tokens = set(normalize_retrieval_text(document_text).split())
    return len(query_tokens.intersection(document_tokens))


def render_documents_for_prompt(
    documents: Iterable[tuple[str, str]],
    *,
    max_chars: int = 12000,
    per_document_chars: int = 2400,
) -> str:
    chunks = ["Context documents:"]
    total = len(chunks[0])
    for filename, content in documents:
        header = f"[{Path(filename).name}]"
        body = " ".join(content.strip().split())
        snippet = body[:per_document_chars]
        entry = f"{header} {snippet}"
        if total + len(entry) > max_chars:
            break
        chunks.append(entry)
        total += len(entry)
    return "\n".join(chunks)


def _has_meaningful_text(value: str) -> bool:
    normalized = " ".join(value.split())
    return len(normalized) >= 40


def _extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except Exception:
        return ""
    try:
        reader = PdfReader(io.BytesIO(payload))
    except Exception:
        return ""
    text_parts: list[str] = []
    for page in reader.pages:
        try:
            text_parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(part for part in text_parts if part).strip()


def _extract_pdf_text_with_ocr(payload: bytes) -> str:
    try:
        import fitz  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except Exception:
        return ""

    try:
        document = fitz.open(stream=payload, filetype="pdf")
    except Exception:
        return ""

    ocr_engine = RapidOCR()
    text_parts: list[str] = []
    for page in document:
        try:
            pixmap = page.get_pixmap(dpi=180, alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            image_array = np.array(image)
            result, _elapsed = ocr_engine(image_array)
            if not result:
                continue
            page_lines = [str(line[1]).strip() for line in result if len(line) > 1]
            page_text = "\n".join(line for line in page_lines if line)
            if page_text.strip():
                text_parts.append(page_text)
        except Exception:
            continue
    return "\n".join(text_parts).strip()
