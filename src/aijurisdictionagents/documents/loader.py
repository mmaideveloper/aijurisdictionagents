from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, List

from ..schemas import Document, Source

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md"}


def load_documents(data_dir: Path, allow_pdf: bool = False) -> List[Document]:
    if not data_dir.exists():
        logger.warning("Data directory not found: %s", data_dir)
        return []

    documents: List[Document] = []
    for path in sorted(data_dir.iterdir()):
        if path.is_dir():
            continue
        ext = path.suffix.lower()
        if ext in TEXT_EXTENSIONS:
            content = path.read_text(encoding="utf-8", errors="ignore")
        elif ext == ".pdf":
            if not allow_pdf:
                logger.info("Skipping PDF without allow_pdf: %s", path)
                continue
            content = _read_pdf(path)
        else:
            continue

        doc_id = f"doc-{len(documents) + 1}"
        documents.append(Document(doc_id=doc_id, path=str(path), content=content))

    return documents


def select_sources(
    documents: Iterable[Document],
    query: str,
    max_sources: int = 3,
    snippet_len: int = 220,
) -> List[Source]:
    terms = _query_terms(query)
    scored: List[tuple[int, Document]] = []
    for doc in documents:
        content_lower = doc.content.lower()
        score = sum(content_lower.count(term) for term in terms)
        scored.append((score, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    sources: List[Source] = []
    for _, doc in scored:
        if not doc.content.strip():
            continue
        snippet = _find_snippet(doc.content, terms, snippet_len)
        sources.append(Source(filename=Path(doc.path).name, snippet=snippet))
        if len(sources) >= max_sources:
            break

    return sources


def _query_terms(query: str) -> List[str]:
    tokens = [token.lower() for token in re.findall(r"\w+", query)]
    return [token for token in tokens if len(token) > 2]


def _find_snippet(content: str, terms: List[str], snippet_len: int) -> str:
    content_lower = content.lower()
    for term in terms:
        idx = content_lower.find(term)
        if idx != -1:
            start = max(idx - 40, 0)
            end = min(start + snippet_len, len(content))
            snippet = content[start:end].strip()
            return _clean_snippet(snippet)

    return _clean_snippet(content[:snippet_len])


def _clean_snippet(text: str) -> str:
    return " ".join(text.split())


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required to read PDFs. Install with 'pip install pypdf'."
        ) from exc

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)
