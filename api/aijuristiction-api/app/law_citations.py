from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import importlib
from mimetypes import guess_type
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Sequence, cast
from urllib.parse import urlparse

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobClient, BlobServiceClient

from app.chat.models import Message, MessageRole

from aijurisdictionagents.llm import get_embedding_client
from services.laws_collector import LawsCollectorConfig, LawsCollectorService, PostgresLawStore, SqliteLawStore

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_COLLECTION_CODE = "ZZ"
_EXPLICIT_LAW_PATTERN = re.compile(r"\b(?P<number>\d{1,4})/(?P<year>\d{4})\b")
_ISO_DATE_PATTERN = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
_DOT_DATE_PATTERN = re.compile(r"\b(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{4})\b")
_LEGAL_STOPWORDS = {
    "about",
    "also",
    "contract",
    "document",
    "documents",
    "draft",
    "generate",
    "legal",
    "please",
    "prepare",
    "review",
    "what",
    "with",
    "zmluva",
    "zmluvy",
    "dokument",
    "dokumenty",
    "navrh",
    "návrh",
    "priprav",
    "vygeneruj",
}


@dataclass(frozen=True)
class LawCitation:
    country_code: str
    collection_code: str
    law_year: int
    law_number: int
    law_identifier: str
    title: str
    version_token: str
    effective_from: str
    as_of_date: str
    official_source_url: str
    artifact_kind: str
    open_url: str
    storage_backend: str

    @property
    def summary(self) -> str:
        return (
            f"{self.law_identifier} ({self.title}), version {self.version_token}, "
            f"effective from {self.effective_from}"
        )

    @property
    def label(self) -> str:
        return f"{self.law_identifier} - {self.title}"

    def as_metadata(self) -> dict[str, str]:
        return {
            "country_code": self.country_code,
            "collection_code": self.collection_code,
            "law_year": str(self.law_year),
            "law_number": str(self.law_number),
            "law_identifier": self.law_identifier,
            "title": self.title,
            "version_token": self.version_token,
            "effective_from": self.effective_from,
            "as_of_date": self.as_of_date,
            "official_source_url": self.official_source_url,
            "artifact_kind": self.artifact_kind,
            "open_url": self.open_url,
            "storage_backend": self.storage_backend,
            "label": self.label,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class _ResolvedLawVersion:
    country_code: str
    collection_code: str
    law_year: int
    law_number: int
    law_identifier: str
    title: str
    version_id: str
    version_token: str
    effective_from: str
    official_source_url: str


@dataclass(frozen=True)
class _LawArtifactLocation:
    artifact_kind: str
    source_url: str
    storage_backend: str
    storage_path: str


def resolve_session_law_citations(
    *,
    country_code: str | None,
    messages: Sequence[Message],
    final_recommendation: str,
    limit: int = 3,
) -> list[dict[str, str]]:
    normalized_country = (country_code or "").strip().upper()
    if not normalized_country:
        return []

    effective_on = _resolve_effective_on(messages=messages)
    combined_text = "\n".join(
        [final_recommendation.strip(), *[message.content for message in messages if message.role != MessageRole.SYSTEM]]
    ).strip()
    citations: list[LawCitation] = []
    seen_keys: set[tuple[str, str, int, int]] = set()

    for law_year, law_number in _extract_explicit_law_targets(combined_text):
        citation = _resolve_citation_for_law(
            country_code=normalized_country,
            collection_code=_DEFAULT_COLLECTION_CODE,
            law_year=law_year,
            law_number=law_number,
            effective_on=effective_on,
        )
        if citation is None:
            continue
        key = (citation.country_code, citation.collection_code, citation.law_year, citation.law_number)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        citations.append(citation)
        if len(citations) >= limit:
            return [item.as_metadata() for item in citations]

    semantic_query = _build_semantic_query(messages=messages, final_recommendation=final_recommendation)
    if semantic_query:
        for candidate in _search_semantic_candidates(
            query=semantic_query,
            country_code=normalized_country,
            limit=max(limit * 3, 6),
        ):
            citation = _resolve_citation_for_law(
                country_code=candidate.country_code,
                collection_code=candidate.collection_code,
                law_year=candidate.law_year,
                law_number=candidate.law_number,
                effective_on=effective_on,
            )
            if citation is None:
                continue
            key = (citation.country_code, citation.collection_code, citation.law_year, citation.law_number)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            citations.append(citation)
            if len(citations) >= limit:
                break

    return [item.as_metadata() for item in citations[:limit]]


def read_law_source(
    *,
    country_code: str,
    collection_code: str,
    law_year: int,
    law_number: int,
    version_token: str,
    artifact_kind: str,
) -> tuple[bytes, str, str] | None:
    version = _resolve_exact_version(
        country_code=country_code,
        collection_code=collection_code,
        law_year=law_year,
        law_number=law_number,
        version_token=version_token,
    )
    if version is None:
        return None

    artifact = _load_preferred_artifact(version_id=version.version_id, artifact_kind=artifact_kind)
    if artifact is None:
        return None

    filename = (
        f"{version.collection_code.lower()}-{version.law_year}-{version.law_number}-"
        f"{version.version_token}.{_artifact_extension(artifact.artifact_kind)}"
    )
    media_type = _artifact_media_type(artifact.storage_path, artifact.artifact_kind)
    payload = _read_artifact_bytes(artifact)
    return payload, media_type, filename


def _resolve_effective_on(*, messages: Sequence[Message]) -> str:
    for message in reversed(messages):
        if message.role != MessageRole.USER:
            continue
        detected = _extract_date_reference(message.content)
        if detected is not None:
            return detected
    return date.today().isoformat()


def _extract_date_reference(text: str) -> str | None:
    match = _ISO_DATE_PATTERN.search(text)
    if match is not None:
        return f"{match.group('year')}-{match.group('month')}-{match.group('day')}"
    match = _DOT_DATE_PATTERN.search(text)
    if match is not None:
        try:
            return date(
                year=int(match.group("year")),
                month=int(match.group("month")),
                day=int(match.group("day")),
            ).isoformat()
        except ValueError:
            return None
    return None


def _extract_explicit_law_targets(text: str) -> list[tuple[int, int]]:
    targets: list[tuple[int, int]] = []
    for match in _EXPLICIT_LAW_PATTERN.finditer(text):
        number = int(match.group("number"))
        year = int(match.group("year"))
        candidate = (year, number)
        if candidate not in targets:
            targets.append(candidate)
    return targets


def _build_semantic_query(*, messages: Sequence[Message], final_recommendation: str) -> str:
    segments = [
        final_recommendation.strip(),
        *[
            message.content.strip()
            for message in messages
            if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
        ],
    ]
    text = " ".join(segment for segment in segments if segment).strip()
    if not text:
        return ""
    terms: list[str] = []
    for token in re.findall(r"[^\W\d_]{4,}", text.lower(), flags=re.UNICODE):
        if token in _LEGAL_STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= 24:
            break
    return " ".join(terms) if terms else text[:400]


def _search_semantic_candidates(*, query: str, country_code: str, limit: int) -> Sequence[Any]:
    try:
        config = LawsCollectorConfig.from_env()
        if config.country_code != country_code:
            config = LawsCollectorConfig(
                country_code=country_code,
                db_backend=config.db_backend,
                db_local=config.db_local,
                db_cloud=config.db_cloud,
                storage_local=config.storage_local,
                storage_cloud=config.storage_cloud,
                delta_poll_hours=config.delta_poll_hours,
                initial_import_from=config.initial_import_from,
                historical_import_from=config.historical_import_from,
                import_mode=config.import_mode,
            )
        store: SqliteLawStore | PostgresLawStore
        if config.db_backend == "sqlite":
            if not config.db_path.exists():
                return ()
            store = SqliteLawStore.from_config(config)
        else:
            store = PostgresLawStore.from_config(config)
        service = LawsCollectorService(
            config=config,
            store=store,
            embedding_client=get_embedding_client(),
        )
        return service.search_semantic(query, limit=limit)
    except Exception:
        return ()


def _resolve_citation_for_law(
    *,
    country_code: str,
    collection_code: str,
    law_year: int,
    law_number: int,
    effective_on: str,
) -> LawCitation | None:
    version = _resolve_applicable_version(
        country_code=country_code,
        collection_code=collection_code,
        law_year=law_year,
        law_number=law_number,
        effective_on=effective_on,
    )
    if version is None:
        return None
    artifact = _load_preferred_artifact(version_id=version.version_id, artifact_kind="html")
    if artifact is None:
        artifact = _load_preferred_artifact(version_id=version.version_id, artifact_kind="pdf")
    if artifact is None:
        return None
    return LawCitation(
        country_code=version.country_code,
        collection_code=version.collection_code,
        law_year=version.law_year,
        law_number=version.law_number,
        law_identifier=version.law_identifier,
        title=version.title,
        version_token=version.version_token,
        effective_from=version.effective_from,
        as_of_date=effective_on,
        official_source_url=version.official_source_url,
        artifact_kind=artifact.artifact_kind,
        open_url=_build_law_open_url(
            country_code=version.country_code,
            collection_code=version.collection_code,
            law_year=version.law_year,
            law_number=version.law_number,
            version_token=version.version_token,
            artifact_kind=artifact.artifact_kind,
        ),
        storage_backend=artifact.storage_backend,
    )


def _resolve_applicable_version(
    *,
    country_code: str,
    collection_code: str,
    law_year: int,
    law_number: int,
    effective_on: str,
) -> _ResolvedLawVersion | None:
    query = """
        SELECT
            d.country_code,
            d.collection_code,
            d.law_year,
            d.law_number,
            COALESCE(
                m.law_identifier_text,
                CAST(d.law_number AS TEXT) || '/' || CAST(d.law_year AS TEXT)
            ) AS law_identifier,
            COALESCE(NULLIF(m.title, ''), d.lawyer_title, d.official_name) AS title,
            v.version_id,
            v.version_token,
            v.effective_from,
            d.source_url
        FROM law_documents AS d
        JOIN law_versions AS v ON v.document_id = d.document_id
        LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
        WHERE UPPER(d.country_code) = {country_filter}
          AND UPPER(d.collection_code) = {collection_filter}
          AND d.law_year = {year_filter}
          AND d.law_number = {number_filter}
          AND v.effective_from <= {effective_filter}
        ORDER BY v.effective_from DESC
        LIMIT 1
    """
    row = _fetchone_laws_query(
        query=query.format(
            country_filter=_laws_param("country"),
            collection_filter=_laws_param("collection"),
            year_filter=_laws_param("year"),
            number_filter=_laws_param("number"),
            effective_filter=_laws_param("effective"),
        ),
        params=(country_code, collection_code, law_year, law_number, effective_on),
    )
    if row is None:
        fallback_query = """
            SELECT
                d.country_code,
                d.collection_code,
                d.law_year,
                d.law_number,
                COALESCE(
                    m.law_identifier_text,
                    CAST(d.law_number AS TEXT) || '/' || CAST(d.law_year AS TEXT)
                ) AS law_identifier,
                COALESCE(NULLIF(m.title, ''), d.lawyer_title, d.official_name) AS title,
                v.version_id,
                v.version_token,
                v.effective_from,
                d.source_url
            FROM law_documents AS d
            JOIN law_versions AS v ON v.document_id = d.document_id
            LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
            WHERE UPPER(d.country_code) = {country_filter}
              AND UPPER(d.collection_code) = {collection_filter}
              AND d.law_year = {year_filter}
              AND d.law_number = {number_filter}
            ORDER BY v.effective_from DESC
            LIMIT 1
        """
        row = _fetchone_laws_query(
            query=fallback_query.format(
                country_filter=_laws_param("country"),
                collection_filter=_laws_param("collection"),
                year_filter=_laws_param("year"),
                number_filter=_laws_param("number"),
            ),
            params=(country_code, collection_code, law_year, law_number),
        )
    if row is None:
        return None
    return _resolved_law_version_from_row(row)


def _resolve_exact_version(
    *,
    country_code: str,
    collection_code: str,
    law_year: int,
    law_number: int,
    version_token: str,
) -> _ResolvedLawVersion | None:
    query = """
        SELECT
            d.country_code,
            d.collection_code,
            d.law_year,
            d.law_number,
            COALESCE(
                m.law_identifier_text,
                CAST(d.law_number AS TEXT) || '/' || CAST(d.law_year AS TEXT)
            ) AS law_identifier,
            COALESCE(NULLIF(m.title, ''), d.lawyer_title, d.official_name) AS title,
            v.version_id,
            v.version_token,
            v.effective_from,
            d.source_url
        FROM law_documents AS d
        JOIN law_versions AS v ON v.document_id = d.document_id
        LEFT JOIN law_metadata AS m ON m.version_id = v.version_id
        WHERE UPPER(d.country_code) = {country_filter}
          AND UPPER(d.collection_code) = {collection_filter}
          AND d.law_year = {year_filter}
          AND d.law_number = {number_filter}
          AND v.version_token = {version_filter}
        LIMIT 1
    """
    row = _fetchone_laws_query(
        query=query.format(
            country_filter=_laws_param("country"),
            collection_filter=_laws_param("collection"),
            year_filter=_laws_param("year"),
            number_filter=_laws_param("number"),
            version_filter=_laws_param("version"),
        ),
        params=(country_code, collection_code, law_year, law_number, version_token),
    )
    if row is None:
        return None
    return _resolved_law_version_from_row(row)


def _load_preferred_artifact(*, version_id: str, artifact_kind: str) -> _LawArtifactLocation | None:
    preferred_order: tuple[str, ...]
    if artifact_kind == "html":
        preferred_order = ("html", "pdf")
    elif artifact_kind == "pdf":
        preferred_order = ("pdf", "html")
    else:
        preferred_order = (artifact_kind, "html", "pdf")

    order_cases = " ".join(
        f"WHEN artifact_kind = '{kind}' THEN {index}" for index, kind in enumerate(preferred_order)
    )
    query = f"""
        SELECT artifact_kind, source_url, storage_backend, storage_path
        FROM source_artifacts
        WHERE version_id = {_laws_param("version_id")}
        ORDER BY CASE {order_cases} ELSE 99 END
        LIMIT 1
    """
    row = _fetchone_laws_query(query=query, params=(version_id,))
    if row is None:
        return None
    return _LawArtifactLocation(
        artifact_kind=str(_law_row_value(row, 0)),
        source_url=str(_law_row_value(row, 1)),
        storage_backend=str(_law_row_value(row, 2)),
        storage_path=str(_law_row_value(row, 3)),
    )


def _resolved_law_version_from_row(row: Sequence[Any]) -> _ResolvedLawVersion:
    return _ResolvedLawVersion(
        country_code=str(_law_row_value(row, 0)),
        collection_code=str(_law_row_value(row, 1)),
        law_year=int(_law_row_value(row, 2)),
        law_number=int(_law_row_value(row, 3)),
        law_identifier=str(_law_row_value(row, 4)),
        title=str(_law_row_value(row, 5)),
        version_id=str(_law_row_value(row, 6)),
        version_token=str(_law_row_value(row, 7)),
        effective_from=str(_law_row_value(row, 8)),
        official_source_url=str(_law_row_value(row, 9)),
    )


def _fetchone_laws_query(*, query: str, params: Sequence[Any]) -> Sequence[Any] | None:
    db_backend = os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower()
    db_local = os.getenv(
        "LAWS_DB_LOCAL",
        "./runs/storage/laws-collector/sqlite/sk_laws.sqlite3",
    ).strip()
    db_cloud = os.getenv("LAWS_DB_CLOUD", "").strip()

    if db_backend == "sqlite":
        db_path = _resolve_repo_path(db_local)
        if not db_path.exists():
            return None
        with sqlite3.connect(db_path) as conn:
            return cast(Sequence[Any] | None, conn.execute(query, params).fetchone())

    if db_backend == "postgres" and db_cloud:
        psycopg = importlib.import_module("psycopg")
        with psycopg.connect(db_cloud) as conn:
            return cast(Sequence[Any] | None, conn.execute(query, params).fetchone())
    return None


def _laws_param(name: str) -> str:
    if os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower() == "postgres":
        return "%s"
    return "?"


def _law_row_value(row: Sequence[Any], index: int) -> Any:
    return row[index]


def _build_law_open_url(
    *,
    country_code: str,
    collection_code: str,
    law_year: int,
    law_number: int,
    version_token: str,
    artifact_kind: str,
) -> str:
    return (
        "/v1/laws/source"
        f"?country_code={country_code}"
        f"&collection_code={collection_code}"
        f"&law_year={law_year}"
        f"&law_number={law_number}"
        f"&version_token={version_token}"
        f"&artifact_kind={artifact_kind}"
    )


def _artifact_media_type(storage_path: str, artifact_kind: str) -> str:
    guessed = guess_type(storage_path)[0]
    if guessed:
        return guessed
    if artifact_kind == "html":
        return "text/html; charset=utf-8"
    if artifact_kind == "pdf":
        return "application/pdf"
    return "application/octet-stream"


def _artifact_extension(artifact_kind: str) -> str:
    if artifact_kind == "html":
        return "html"
    if artifact_kind == "pdf":
        return "pdf"
    return "bin"


def _read_artifact_bytes(artifact: _LawArtifactLocation) -> bytes:
    if artifact.storage_backend == "local_file":
        path = Path(artifact.storage_path).resolve()
        path.relative_to(_REPO_ROOT.resolve())
        return path.read_bytes()
    if artifact.storage_backend == "azure_blob":
        return _read_azure_blob(artifact.storage_path)
    raise ValueError(f"Unsupported source artifact storage backend: {artifact.storage_backend}")


def _read_azure_blob(blob_url: str) -> bytes:
    parsed = urlparse(blob_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid Azure Blob URL.")
    if parsed.query:
        return BlobClient.from_blob_url(blob_url).download_blob().readall()

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise ValueError("Azure Blob URL must include container and blob path.")
    container_name = path_parts[0]
    blob_name = "/".join(path_parts[1:])
    account_url = f"{parsed.scheme}://{parsed.netloc}"
    managed_identity_client_id = os.getenv("AZURE_CLIENT_ID", "").strip() or None
    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
        managed_identity_client_id=managed_identity_client_id,
    )
    blob_client = BlobServiceClient(account_url=account_url, credential=credential).get_blob_client(
        container=container_name,
        blob=blob_name,
    )
    return blob_client.download_blob().readall()


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
