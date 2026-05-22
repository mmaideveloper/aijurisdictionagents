from __future__ import annotations

import hashlib
import importlib
import io
import json
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ExtractedDocumentContent:
    text: str
    extraction_method: str


@dataclass(frozen=True)
class DocumentChunk:
    chunk_index: int
    text: str
    start_offset: int
    end_offset: int


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


def serialize_embedding_vector(values: Sequence[float]) -> str:
    return json.dumps([float(value) for value in values])


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


def render_pdf_pages_with_poppler(
    payload: bytes,
    *,
    dpi: int = 180,
    max_pages: int = 20,
) -> list[bytes]:
    """Render PDF pages to PNG bytes with Poppler's pdftoppm when it is installed."""
    return _render_pdf_pages_with_poppler(payload, dpi=dpi, max_pages=max_pages)


def chunk_document_text(
    text: str,
    *,
    target_chars: int = 1200,
    overlap_chars: int = 180,
    min_chunk_chars: int = 240,
) -> list[DocumentChunk]:
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[DocumentChunk] = []
    cursor = 0
    while cursor < len(normalized):
        end = min(cursor + target_chars, len(normalized))
        window = normalized[cursor:end]
        if end < len(normalized):
            split_at = max(window.rfind("\n\n"), window.rfind(". "), window.rfind(" "))
            if split_at >= max(target_chars // 2, min_chunk_chars):
                end = cursor + split_at + 1
                window = normalized[cursor:end]
        chunk_text = window.strip()
        if chunk_text:
            chunks.append(
                DocumentChunk(
                    chunk_index=len(chunks),
                    text=chunk_text,
                    start_offset=cursor,
                    end_offset=end,
                )
            )
        if end >= len(normalized):
            break
        cursor = max(end - overlap_chars, cursor + 1)
        while cursor < len(normalized) and normalized[cursor].isspace():
            cursor += 1

    compacted = [chunk for chunk in chunks if len(chunk.text) >= min_chunk_chars or len(chunks) == 1]
    return [
        DocumentChunk(
            chunk_index=index,
            text=chunk.text,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
        )
        for index, chunk in enumerate(compacted or chunks[:1])
    ]


def _has_meaningful_text(value: str) -> bool:
    normalized = " ".join(value.split())
    return len(normalized) >= 40


def _extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
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
        from PIL import Image

        np = importlib.import_module("numpy")
        rapidocr_module = importlib.import_module("rapidocr_onnxruntime")
        rapidocr_factory = getattr(rapidocr_module, "RapidOCR")
    except Exception:
        return ""

    rendered_pages = render_pdf_pages_with_poppler(payload)
    if not rendered_pages:
        rendered_pages = _render_pdf_pages_with_pymupdf(payload)
    if not rendered_pages:
        return ""

    ocr_engine = rapidocr_factory()
    text_parts: list[str] = []
    for page_png in rendered_pages:
        try:
            image = Image.open(io.BytesIO(page_png))
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


def _render_pdf_pages_with_poppler(
    payload: bytes,
    *,
    dpi: int = 180,
    max_pages: int = 20,
) -> list[bytes]:
    pdftoppm_path = shutil.which("pdftoppm")
    if not pdftoppm_path:
        return []

    with tempfile.TemporaryDirectory(prefix="document-pdf-render-") as temp_dir:
        temp_path = Path(temp_dir)
        pdf_path = temp_path / "input.pdf"
        output_prefix = temp_path / "page"
        pdf_path.write_bytes(payload)
        command = [
            pdftoppm_path,
            "-png",
            "-r",
            str(dpi),
            "-f",
            "1",
            "-l",
            str(max_pages),
            str(pdf_path),
            str(output_prefix),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        pages = sorted(temp_path.glob("page-*.png"))
        return [page_path.read_bytes() for page_path in pages]


def _render_pdf_pages_with_pymupdf(
    payload: bytes,
    *,
    dpi: int = 180,
    max_pages: int = 20,
) -> list[bytes]:
    try:
        fitz = importlib.import_module("fitz")
        document = fitz.open(stream=payload, filetype="pdf")
    except Exception:
        return []

    pages: list[bytes] = []
    for page_index in range(min(len(document), max_pages)):
        try:
            page = document[page_index]
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            pages.append(pixmap.tobytes("png"))
        except Exception:
            continue
    return pages
