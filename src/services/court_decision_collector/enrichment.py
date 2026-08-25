from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlparse

import httpx

from aijurisdictionagents.llm.embeddings import EmbeddingClient, get_embedding_client
from services.document_processor.runtime import chunk_document_text, extract_document_text

from .infosud_source import InfoSudSourceClient
from .postgres_store import PostgresCourtDecisionStore
from .pseudonymization import (
    UnsafePseudonymizationError,
    pseudonymize_court_decision_text,
    validate_pseudonymized_court_decision_text,
)

_ALLOWED_HOST = "obcan.justice.sk"
_TOPIC_STOPWORDS = {
    "ktorý", "ktorá", "ktoré", "tento", "tejto", "súd", "rozhodol", "rozhodnutie",
    "podľa", "žalobca", "žalovaný", "navrhovateľ", "odporca", "konanie", "spis",
}


@dataclass(frozen=True)
class EnrichmentResult:
    decision_id: str
    version_id: str
    status: str
    cache_hit: bool
    metadata: dict[str, object]
    pdf_path: str
    pdf_sha256: str
    extraction_method: str
    pseudonymized_summary: str
    legal_topics: tuple[str, ...]
    embedding_model: str
    embedding_dimensions: int
    chunk_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class OnDemandCourtDecisionEnricher:
    def __init__(
        self,
        *,
        store: PostgresCourtDecisionStore,
        source: InfoSudSourceClient,
        storage_root: Path,
        embedding_client: EmbeddingClient | None = None,
        max_pdf_bytes: int = 25 * 1024 * 1024,
        downloader: Callable[[str], bytes] | None = None,
    ) -> None:
        self.store = store
        self.source = source
        self.storage_root = storage_root
        self.embedding_client = embedding_client
        self.max_pdf_bytes = max_pdf_bytes
        self.downloader = downloader or self._download_pdf

    def enrich_source_url(
        self, source_url: str, *, priority_class: str = "user_requested"
    ) -> EnrichmentResult:
        guid = _guid_from_source_url(source_url, expected_base_url=self.source.base_url)
        record = self.source.get_decision(guid)
        stored = self.store.upsert_decision(record)
        enqueue = getattr(self.store, "enqueue_enrichment", None)
        if callable(enqueue):
            enqueue(
                decision_id=stored.decision_id,
                version_id=stored.version_id,
                priority_class=priority_class,
            )
        cached = self.store.get_enrichment(version_id=stored.version_id)
        if cached and cached.get("status") == "ready" and Path(str(cached["pdf_path"])).is_file():
            return _result_from_row(cached, metadata=record.metadata, cache_hit=True)

        document = record.metadata.get("dokument")
        if not isinstance(document, dict):
            raise ValueError("InfoSud decision metadata does not contain dokument metadata")
        pdf_url = str(document.get("url", "")).strip()
        filename = _safe_pdf_filename(str(document.get("name", "decision.pdf")))
        expected_size = int(document.get("size", 0) or 0)
        _validate_infosud_url(pdf_url, expected_prefix="/content/public/item/")

        self.store.mark_enrichment_processing(
            decision_id=stored.decision_id,
            version_id=stored.version_id,
            source_url=record.source_url,
            pdf_url=pdf_url,
            pdf_filename=filename,
            expected_size=expected_size,
            metadata=record.metadata,
        )
        try:
            payload = self.downloader(pdf_url)
            _validate_pdf(payload, expected_size=expected_size, max_bytes=self.max_pdf_bytes)
            digest = sha256(payload).hexdigest()
            target = self.storage_root / stored.decision_id / stored.version_id / filename
            extracted = extract_document_text(filename=filename, payload=payload)
            public_text = pseudonymize_court_decision_text(extracted.text)
            validate_pseudonymized_court_decision_text(public_text)
            summary = build_local_extract_summary(public_text)
            topics = extract_legal_topics(public_text)
            chunks = chunk_document_text(public_text)
            inputs = [summary, *[chunk.text for chunk in chunks]]
            embedding_client = self.embedding_client or get_embedding_client()
            batch = embedding_client.embed_texts(inputs)
            dimensions = len(batch.vectors[0]) if batch.vectors else 0
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".part")
            temporary.write_bytes(payload)
            temporary.replace(target)
            self.store.save_enrichment(
                decision_id=stored.decision_id,
                version_id=stored.version_id,
                pdf_path=str(target),
                pdf_sha256=digest,
                actual_size=len(payload),
                extraction_method=extracted.extraction_method,
                raw_text=extracted.text,
                pseudonymized_text=public_text,
                summary=summary,
                legal_topics=topics,
                embedding_model=batch.model_name,
                vectors=batch.vectors,
                chunks=chunks,
            )
            return EnrichmentResult(
                decision_id=stored.decision_id,
                version_id=stored.version_id,
                status="ready",
                cache_hit=False,
                metadata=record.metadata,
                pdf_path=str(target),
                pdf_sha256=digest,
                extraction_method=extracted.extraction_method,
                pseudonymized_summary=summary,
                legal_topics=topics,
                embedding_model=batch.model_name,
                embedding_dimensions=dimensions,
                chunk_count=len(chunks),
            )
        except UnsafePseudonymizationError as exc:
            quarantine = getattr(self.store, "mark_enrichment_quarantined", None)
            if callable(quarantine):
                quarantine(version_id=stored.version_id, error_type=type(exc).__name__)
            raise
        except Exception as exc:
            self.store.mark_enrichment_failed(version_id=stored.version_id, error_type=type(exc).__name__)
            raise

    def _download_pdf(self, url: str) -> bytes:
        _validate_infosud_url(url, expected_prefix="/content/public/item/")
        with httpx.Client(timeout=self.source.timeout_seconds, verify=self.source.tls_verify) as client:
            current = url
            for _ in range(4):
                response = client.get(current, follow_redirects=False)
                if response.is_redirect:
                    if response.next_request is None:
                        raise ValueError("InfoSud redirect is missing a target")
                    current = str(response.next_request.url)
                    _validate_infosud_url(current, expected_prefix="/content/public/item/")
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not any(value in content_type for value in ("pdf", "octet-stream")):
                    raise ValueError("InfoSud document response is not a PDF content type")
                return response.content
        raise ValueError("Too many InfoSud PDF redirects")


def build_local_extract_summary(text: str, *, max_chars: int = 1200) -> str:
    normalized = " ".join(text.split())
    outcome_match = re.search(r"(?:r\s*o\s*z\s*h\s*o\s*d\s*o\s*l|rozhodol)\s*:?", normalized, re.IGNORECASE)
    if outcome_match:
        normalized = "Výrok rozhodnutia: " + normalized[outcome_match.end() :].strip()
    normalized = re.sub(r"\bIČO\s*:\s*[0-9 ]{6,15}\b", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b\d{3}\s*\d{2}\s+[A-ZÁ-Ž][A-Za-zÁ-ž -]+", "[ADDRESS]", normalized)
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    selected: list[str] = []
    for sentence in sentences:
        if len(sentence) < 25:
            continue
        if sum(len(item) for item in selected) + len(sentence) > max_chars:
            break
        selected.append(sentence)
        if len(selected) >= 5:
            break
    summary = " ".join(selected) or normalized[:max_chars]
    return summary[:max_chars].rstrip()


def extract_legal_topics(text: str, *, limit: int = 8) -> tuple[str, ...]:
    words = re.findall(r"[A-Za-zÁ-ž]{5,}", text.lower())
    counts = Counter(word for word in words if word not in _TOPIC_STOPWORDS)
    return tuple(word for word, _count in counts.most_common(limit))


def _guid_from_source_url(source_url: str, *, expected_base_url: str) -> str:
    _validate_infosud_url(source_url, expected_prefix="/pilot/api/ress-isu-service/v1/rozhodnutie/")
    if not source_url.startswith(expected_base_url.rstrip("/") + "/rozhodnutie/"):
        raise ValueError("source_url does not match configured InfoSud decision endpoint")
    guid = source_url.rstrip("/").rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9:-]{20,200}", guid):
        raise ValueError("Invalid InfoSud decision GUID")
    return guid


def _validate_infosud_url(url: str, *, expected_prefix: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST or not parsed.path.startswith(expected_prefix):
        raise ValueError("Only allowlisted InfoSud HTTPS URLs are accepted")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("InfoSud URL contains disallowed authority components")


def _safe_pdf_filename(value: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name or "decision.pdf"


def _validate_pdf(payload: bytes, *, expected_size: int, max_bytes: int) -> None:
    if not payload.startswith(b"%PDF-"):
        raise ValueError("Downloaded artifact does not have a PDF signature")
    if len(payload) > max_bytes:
        raise ValueError("Downloaded PDF exceeds configured size limit")
    if expected_size and len(payload) != expected_size:
        raise ValueError("Downloaded PDF size differs from InfoSud metadata")


def _result_from_row(row: dict[str, object], *, metadata: dict[str, object], cache_hit: bool) -> EnrichmentResult:
    raw_topics = row.get("legal_topics", [])
    topics: list[object]
    if isinstance(raw_topics, str):
        decoded = json.loads(raw_topics)
        topics = decoded if isinstance(decoded, list) else []
    elif isinstance(raw_topics, list):
        topics = raw_topics
    else:
        topics = []
    return EnrichmentResult(
        decision_id=str(row["decision_id"]), version_id=str(row["version_id"]),
        status=str(row["status"]), cache_hit=cache_hit, metadata=metadata,
        pdf_path=str(row["pdf_path"]), pdf_sha256=str(row["pdf_sha256"]),
        extraction_method=str(row["extraction_method"]),
        pseudonymized_summary=str(row["pseudonymized_summary"]),
        legal_topics=tuple(str(item) for item in topics),
        embedding_model=str(row["embedding_model"]),
        embedding_dimensions=int(str(row["embedding_dimensions"])), chunk_count=int(str(row["chunk_count"])),
    )
