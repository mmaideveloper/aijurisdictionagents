from __future__ import annotations

import importlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence, cast
from urllib.request import Request, urlopen

from app.chat.models import Message, MessageRole, Session
from app.law_citations import resolve_session_law_citations
from app.versioning import get_api_version, get_core_version

from aijurisdictionagents.agents import AIWebSearchAgent, AIAgentsValidator, ValidatorInputs
from aijurisdictionagents.agents.validator import EvaluationCriterion
from aijurisdictionagents.api_db import ApiDatabaseStore

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_MODEL_KNOWLEDGE_SOURCE_URL = "https://platform.openai.com/docs/models"
_MODEL_KNOWLEDGE_MEMORY_KEY = "llm_model_setup"
_UNAVAILABLE_MODEL_KNOWLEDGE_SOURCE = "unavailable"
_OFFICIAL_MODEL_SOURCE_HOSTS = ("platform.openai.com", "openai.com")
_MONTH_NAME_FORMATS = (
    "%b %d, %Y",
    "%B %d, %Y",
)
_KNOWN_MODEL_KNOWLEDGE_CUTOFFS: dict[str, tuple[str, str]] = {
    "gpt-4o-mini": ("2023-10-01", "https://platform.openai.com/docs/models/gpt-4o-mini"),
    "gpt-4.1": ("2024-06-01", "https://platform.openai.com/docs/models/gpt-4.1"),
}

_SESSION_VALIDATION_CRITERIA: tuple[EvaluationCriterion, ...] = (
    EvaluationCriterion(
        name="legal_accuracy",
        description="Whether the final answer aligns with the user's legal problem and document context.",
        weight=0.35,
    ),
    EvaluationCriterion(
        name="coverage",
        description="Whether the response covers the main issues surfaced in the conversation.",
        weight=0.25,
    ),
    EvaluationCriterion(
        name="clarity",
        description="Whether the answer is understandable and concise for the user.",
        weight=0.15,
    ),
    EvaluationCriterion(
        name="risk_awareness",
        description="Whether the answer highlights legal risks, gaps, and next steps.",
        weight=0.15,
    ),
    EvaluationCriterion(
        name="human_likeness",
        description="Whether the exchange resembles a realistic lawyer-client consultation.",
        weight=0.10,
    ),
)

_STOPWORDS = {
    "about",
    "after",
    "also",
    "analysis",
    "analyze",
    "between",
    "contract",
    "country",
    "current",
    "document",
    "documents",
    "final",
    "identify",
    "information",
    "legal",
    "missing",
    "please",
    "problem",
    "problems",
    "provide",
    "review",
    "rights",
    "should",
    "summary",
    "under",
    "what",
    "which",
    "with",
    "zhrnutie",
    "analyza",
    "analyzuj",
    "dokument",
    "dokumenty",
    "law",
}


@dataclass(frozen=True)
class LawKnowledgeSnapshot:
    last_law_update_date: str | None
    last_law_update_source: str
    model_knowledge_cutoff_date: str | None
    model_knowledge_cutoff_source: str
    last_collector_run_at: str | None = None
    last_processed_law: str | None = None
    reference_links: tuple[str, ...] = ()


def build_session_result_metadata(
    *,
    session: Session,
    messages: Sequence[Message],
    final_recommendation: str,
    base_metadata: dict[str, Any] | None = None,
    routed_model_name: str | None = None,
) -> dict[str, Any]:
    metadata = dict(base_metadata or {})
    visible_messages = _visible_messages(messages)
    first_user_message = next(
        (message.content for message in visible_messages if message.role == MessageRole.USER),
        "",
    )
    expected_points = _derive_expected_points(
        question=first_user_message,
        final_recommendation=final_recommendation,
        messages=visible_messages,
    )

    validator = AIAgentsValidator(criteria=_SESSION_VALIDATION_CRITERIA)
    report = validator.evaluate(
        communication_payload={
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in visible_messages
            ]
        },
        inputs=ValidatorInputs(
            country=(session.country or "").strip().upper(),
            question=first_user_message or final_recommendation,
            expected_points=expected_points,
        ),
        final_result=final_recommendation,
    )

    knowledge_snapshot = get_law_knowledge_snapshot(session.country, model_name=routed_model_name)
    law_citations = resolve_session_law_citations(
        country_code=session.country,
        messages=visible_messages,
        final_recommendation=final_recommendation,
    )
    metadata.update(
        {
            "validation_accuracy": report.weighted_accuracy,
            "validation_summary": report.summary,
            "validation_scores": [
                {
                    "name": score.name,
                    "score": score.score,
                    "rationale": score.rationale,
                }
                for score in report.scores
            ],
            "knowledge_last_updated_at": (
                knowledge_snapshot.last_law_update_date
                or knowledge_snapshot.model_knowledge_cutoff_date
            ),
            "knowledge_last_updated_source": (
                knowledge_snapshot.last_law_update_source
                if knowledge_snapshot.last_law_update_date
                else knowledge_snapshot.model_knowledge_cutoff_source
            ),
            "last_law_update_date": knowledge_snapshot.last_law_update_date,
            "last_law_update_source": knowledge_snapshot.last_law_update_source,
            "last_collector_run_at": knowledge_snapshot.last_collector_run_at,
            "last_processed_law": knowledge_snapshot.last_processed_law,
            "model_knowledge_cutoff_date": knowledge_snapshot.model_knowledge_cutoff_date,
            "model_knowledge_cutoff_source": knowledge_snapshot.model_knowledge_cutoff_source,
            "law_reference_links": list(knowledge_snapshot.reference_links),
            "law_citations": law_citations,
            "api_version": get_api_version(),
            "core_version": get_core_version(),
        }
    )
    return metadata


def _visible_messages(messages: Sequence[Message]) -> list[Message]:
    cleaned: list[Message] = []
    for message in messages:
        content = _visible_content(message.content)
        if not content:
            continue
        cleaned.append(
            Message(
                id=message.id,
                session_id=message.session_id,
                role=message.role,
                content=content,
                agent_name=message.agent_name,
                created_at=message.created_at,
                attachments=message.attachments,
            )
        )
    return cleaned


def _visible_content(content: str) -> str:
    marker = re.search(r"\*{0,2}\s*CASE_UPDATE_JSON\s*:?\s*\*{0,2}", content, flags=re.IGNORECASE)
    visible = content[: marker.start()] if marker is not None else content
    return visible.strip()


def _derive_expected_points(
    *,
    question: str,
    final_recommendation: str,
    messages: Sequence[Message],
) -> tuple[str, ...]:
    candidate_text = " ".join(
        [
            question,
            final_recommendation,
            " ".join(message.content for message in messages if message.role == MessageRole.ASSISTANT),
        ]
    )
    tokens: list[str] = []
    for token in re.findall(r"[^\W\d_]{4,}", candidate_text, flags=re.UNICODE):
        lowered = token.lower()
        if lowered in _STOPWORDS:
            continue
        if lowered not in tokens:
            tokens.append(lowered)
        if len(tokens) >= 6:
            break
    if tokens:
        return tuple(tokens)
    fallback = question.strip() or final_recommendation.strip()
    if not fallback:
        return ()
    return (fallback[:120],)


def get_law_knowledge_snapshot(
    country_code: str | None,
    *,
    model_name: str | None = None,
) -> LawKnowledgeSnapshot:
    normalized_country = (country_code or "").strip().upper()
    scope = "country" if normalized_country else "global"
    model_cutoff = _read_or_create_model_knowledge_cutoff_snapshot(model_name=model_name)

    db_backend = os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower()
    db_local = os.getenv(
        "LAWS_DB_LOCAL",
        "./runs/storage/laws-collector/sqlite/sk_laws.sqlite3",
    ).strip()
    db_cloud = os.getenv("LAWS_DB_CLOUD", "").strip()

    if db_backend == "sqlite":
        db_path = _resolve_repo_path(db_local)
        if not db_path.exists():
            return _law_snapshot_without_db(model_cutoff=model_cutoff)
        try:
            with sqlite3.connect(db_path) as conn:
                if normalized_country:
                    row = _fetchone_sqlite(
                        conn=conn,
                        query=_law_snapshot_sqlite_query(filtered=True),
                        params=(normalized_country,),
                    )
                else:
                    row = conn.execute(_law_snapshot_sqlite_query(filtered=False)).fetchone()
                progress_row = _collector_progress_sqlite_row(conn=conn, country_code=normalized_country)
        except sqlite3.Error:
            return _law_snapshot_without_db(model_cutoff=model_cutoff)
        snapshot = _law_snapshot_from_row(
            row,
            scope=scope,
            model_cutoff=model_cutoff,
            progress_row=progress_row,
        )
        if snapshot.last_law_update_date is not None:
            return snapshot
        return _law_snapshot_without_db(model_cutoff=model_cutoff)

    if db_backend == "postgres" and db_cloud:
        try:
            psycopg = importlib.import_module("psycopg")

            with psycopg.connect(db_cloud) as conn:
                if normalized_country:
                    row = _fetchone_postgres(
                        conn=conn,
                        query=_law_snapshot_postgres_query(filtered=True),
                        params=(normalized_country,),
                    )
                else:
                    row = conn.execute(_law_snapshot_postgres_query(filtered=False)).fetchone()
                progress_row = _collector_progress_postgres_row(conn=conn, country_code=normalized_country)
        except Exception:
            return _law_snapshot_without_db(model_cutoff=model_cutoff)
        snapshot = _law_snapshot_from_row(
            row,
            scope=scope,
            model_cutoff=model_cutoff,
            progress_row=progress_row,
        )
        if snapshot.last_law_update_date is not None:
            return snapshot
        return _law_snapshot_without_db(model_cutoff=model_cutoff)

    return _law_snapshot_without_db(model_cutoff=model_cutoff)


def _fetchone_sqlite(
    *,
    conn: sqlite3.Connection,
    query: str,
    params: Sequence[Any] = (),
) -> Sequence[Any] | None:
    return cast(Sequence[Any] | None, conn.execute(query, params).fetchone())


def _fetchone_postgres(
    *,
    conn: Any,
    query: str,
    params: Sequence[Any] = (),
) -> Sequence[Any] | None:
    return cast(Sequence[Any] | None, conn.execute(query, params).fetchone())


def _law_snapshot_sqlite_query(*, filtered: bool) -> str:
    where_clause = "WHERE UPPER(country_code) = ?" if filtered else ""
    return f"""
        SELECT
            MAX(last_stored_at) AS latest_update,
            GROUP_CONCAT(source_url, '||') AS source_urls
        FROM (
            SELECT last_stored_at, source_url
            FROM law_documents
            {where_clause}
            ORDER BY last_stored_at DESC, source_url ASC
            LIMIT 5
        )
    """


def _law_snapshot_postgres_query(*, filtered: bool) -> str:
    where_clause = "WHERE UPPER(country_code) = %s" if filtered else ""
    return f"""
        SELECT
            MAX(last_stored_at) AS latest_update,
            STRING_AGG(source_url, '||') AS source_urls
        FROM (
            SELECT last_stored_at, source_url
            FROM law_documents
            {where_clause}
            ORDER BY last_stored_at DESC, source_url ASC
            LIMIT 5
        ) AS latest_laws
    """


def _law_snapshot_from_row(
    row: Sequence[Any] | None,
    *,
    scope: str,
    model_cutoff: tuple[str | None, str],
    progress_row: Sequence[Any] | None,
) -> LawKnowledgeSnapshot:
    collector_run_at, last_processed_law = _collector_progress_values(progress_row)
    if row is None:
        return _law_snapshot_without_db(
            model_cutoff=model_cutoff,
            last_collector_run_at=collector_run_at,
            last_processed_law=last_processed_law,
            reference_links=(),
        )
    latest_update = row[0]
    raw_links = row[1] if len(row) > 1 else None
    links = _parse_reference_links(raw_links)
    if latest_update is None:
        return _law_snapshot_without_db(
            model_cutoff=model_cutoff,
            last_collector_run_at=collector_run_at,
            last_processed_law=last_processed_law,
            reference_links=links,
        )
    return LawKnowledgeSnapshot(
        last_law_update_date=str(latest_update),
        last_law_update_source=f"law_documents_{scope}",
        model_knowledge_cutoff_date=model_cutoff[0],
        model_knowledge_cutoff_source=model_cutoff[1],
        last_collector_run_at=collector_run_at,
        last_processed_law=last_processed_law,
        reference_links=links,
    )


def _parse_reference_links(raw_links: Any) -> tuple[str, ...]:
    if raw_links is None:
        return ()
    seen: list[str] = []
    for raw_value in str(raw_links).split("||"):
        value = raw_value.strip()
        if not value or value in seen:
            continue
        seen.append(value)
    return tuple(seen)


def _law_snapshot_without_db(
    *,
    model_cutoff: tuple[str | None, str],
    last_collector_run_at: str | None = None,
    last_processed_law: str | None = None,
    reference_links: tuple[str, ...] = (),
) -> LawKnowledgeSnapshot:
    return LawKnowledgeSnapshot(
        last_law_update_date=None,
        last_law_update_source="unavailable",
        model_knowledge_cutoff_date=model_cutoff[0],
        model_knowledge_cutoff_source=model_cutoff[1],
        last_collector_run_at=last_collector_run_at,
        last_processed_law=last_processed_law,
        reference_links=reference_links,
    )


def _read_or_create_model_knowledge_cutoff_snapshot(
    *,
    model_name: str | None = None,
) -> tuple[str | None, str]:
    model_name = (model_name or "").strip() or _resolve_llm_model_name()
    manual_cutoff = str(os.getenv("MODEL_KNOWLEDGE_CUTOFF_DATE") or "").strip()
    cache_path = _resolve_model_knowledge_cutoff_cache_path()

    try:
        store = ApiDatabaseStore.from_env()
    except Exception:
        store = None

    if manual_cutoff:
        snapshot = (manual_cutoff, "env:MODEL_KNOWLEDGE_CUTOFF_DATE")
        _persist_model_knowledge_cutoff_snapshot(
            store=store,
            model_name=model_name,
            snapshot=snapshot,
            source_url=None,
        )
        if cache_path is not None:
            _write_model_knowledge_cutoff_cache(cache_path=cache_path, model_name=model_name, snapshot=snapshot)
        return snapshot

    stored_snapshot = _read_model_knowledge_cutoff_from_permanent_memory(store=store, model_name=model_name)
    if stored_snapshot is not None:
        if cache_path is not None:
            _write_model_knowledge_cutoff_cache(
                cache_path=cache_path,
                model_name=model_name,
                snapshot=stored_snapshot,
            )
        return stored_snapshot

    if cache_path is not None:
        cached_snapshot = _read_model_knowledge_cutoff_cache(cache_path=cache_path, model_name=model_name)
        if cached_snapshot is not None:
            _persist_model_knowledge_cutoff_snapshot(
                store=store,
                model_name=model_name,
                snapshot=cached_snapshot,
                source_url=cached_snapshot[1] if cached_snapshot[1].startswith("http") else None,
            )
            return cached_snapshot

    resolved_snapshot = _resolve_model_knowledge_cutoff_via_web_search(model_name=model_name)
    if resolved_snapshot is not None:
        _persist_model_knowledge_cutoff_snapshot(
            store=store,
            model_name=model_name,
            snapshot=resolved_snapshot,
            source_url=resolved_snapshot[1] if resolved_snapshot[1].startswith("http") else None,
        )
        if cache_path is not None:
            _write_model_knowledge_cutoff_cache(
                cache_path=cache_path,
                model_name=model_name,
                snapshot=resolved_snapshot,
            )
        return resolved_snapshot

    _ensure_model_knowledge_permanent_memory_entry(store=store, model_name=model_name)
    return (None, _UNAVAILABLE_MODEL_KNOWLEDGE_SOURCE)


def _read_model_knowledge_cutoff_cache(
    *,
    cache_path: Path,
    model_name: str,
) -> tuple[str, str] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    cached_model_name = str(payload.get("llm_modelname") or "").strip()
    if cached_model_name and cached_model_name != model_name:
        return None
    cutoff_date = str(payload.get("model_knowledge_cutoff_date") or "").strip()
    if not cutoff_date:
        return None
    source = str(payload.get("source") or _UNAVAILABLE_MODEL_KNOWLEDGE_SOURCE).strip()
    return (cutoff_date, source or _UNAVAILABLE_MODEL_KNOWLEDGE_SOURCE)


def _write_model_knowledge_cutoff_cache(
    *,
    cache_path: Path,
    model_name: str,
    snapshot: tuple[str | None, str],
) -> None:
    if snapshot[0] is None:
        return
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "llm_modelname": model_name,
                    "model_knowledge_cutoff_date": snapshot[0],
                    "source": snapshot[1],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _ensure_model_knowledge_permanent_memory_entry(
    *,
    store: ApiDatabaseStore | None,
    model_name: str,
) -> None:
    memory_payload = {
        "llm_modelname": model_name,
        "cutoff_date": None,
        "cutoff_source": _DEFAULT_MODEL_KNOWLEDGE_SOURCE_URL,
    }
    if store is None:
        return
    try:
        existing_entry = store.get_permanent_memory(_MODEL_KNOWLEDGE_MEMORY_KEY)
        if existing_entry is None:
            store.upsert_permanent_memory(
                key=_MODEL_KNOWLEDGE_MEMORY_KEY,
                value=memory_payload,
                entry_type="llm_model_metadata",
                source_url=_DEFAULT_MODEL_KNOWLEDGE_SOURCE_URL,
            )
    except Exception:
        return


def _resolve_llm_model_name() -> str:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "mock":
        return "mock"
    return "unknown"


def _resolve_model_knowledge_cutoff_cache_path() -> Path | None:
    configured = str(os.getenv("MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE") or "").strip()
    if not configured:
        return None
    return _resolve_repo_path(configured)


def _read_model_knowledge_cutoff_from_permanent_memory(
    *,
    store: ApiDatabaseStore | None,
    model_name: str,
) -> tuple[str, str] | None:
    if store is None:
        return None
    try:
        entry = store.get_permanent_memory(_MODEL_KNOWLEDGE_MEMORY_KEY)
    except Exception:
        return None
    if entry is None:
        return None
    stored_model_name = str(entry.value.get("llm_modelname") or "").strip()
    if stored_model_name and stored_model_name != model_name:
        return None
    cutoff_date = str(entry.value.get("cutoff_date") or "").strip()
    if not cutoff_date:
        return None
    cutoff_source = str(entry.value.get("cutoff_source") or entry.source_url or "").strip()
    return (cutoff_date, cutoff_source or _UNAVAILABLE_MODEL_KNOWLEDGE_SOURCE)


def _persist_model_knowledge_cutoff_snapshot(
    *,
    store: ApiDatabaseStore | None,
    model_name: str,
    snapshot: tuple[str | None, str],
    source_url: str | None,
) -> None:
    if store is None or snapshot[0] is None:
        return
    try:
        store.upsert_permanent_memory(
            key=_MODEL_KNOWLEDGE_MEMORY_KEY,
            value={
                "llm_modelname": model_name,
                "cutoff_date": snapshot[0],
                "cutoff_source": snapshot[1],
            },
            entry_type="llm_model_metadata",
            source_url=source_url or (snapshot[1] if snapshot[1].startswith("http") else None),
        )
    except Exception:
        return


def _resolve_model_knowledge_cutoff_via_web_search(model_name: str) -> tuple[str, str] | None:
    if not model_name or model_name == "unknown":
        return None
    fast_snapshot = _known_model_knowledge_cutoff_fast_path(model_name)
    if fast_snapshot is not None:
        return fast_snapshot
    agent = AIWebSearchAgent()
    for lookup_candidate in _model_lookup_candidates(model_name):
        try:
            records = agent.search(
                query=f'site:platform.openai.com/docs/models "{lookup_candidate}" "knowledge cutoff"',
                max_results=5,
            )
        except Exception:
            records = []
        for record in records:
            source_url = str(record.url).strip()
            if not _is_official_model_source_url(source_url):
                continue
            snippet_date = _extract_knowledge_cutoff_date(record.snippet)
            if snippet_date is not None:
                return (snippet_date, source_url)
            page_text = _fetch_text_from_url(source_url)
            if not page_text:
                continue
            page_date = _extract_knowledge_cutoff_date(page_text)
            if page_date is not None:
                return (page_date, source_url)
        for source_url in _candidate_openai_model_source_urls(lookup_candidate):
            page_text = _fetch_text_from_url(source_url)
            if not page_text:
                continue
            page_date = _extract_knowledge_cutoff_date(page_text)
            if page_date is not None:
                return (page_date, source_url)
    for lookup_candidate in _model_lookup_candidates(model_name):
        known_snapshot = _KNOWN_MODEL_KNOWLEDGE_CUTOFFS.get(lookup_candidate)
        if known_snapshot is not None:
            return known_snapshot
    return None


def _known_model_knowledge_cutoff_fast_path(model_name: str) -> tuple[str, str] | None:
    for lookup_candidate in _model_lookup_candidates(model_name):
        if lookup_candidate == "gpt-4o-mini":
            return _KNOWN_MODEL_KNOWLEDGE_CUTOFFS[lookup_candidate]
    return None


def _candidate_openai_model_source_urls(model_name: str) -> tuple[str, ...]:
    normalized = model_name.strip().strip("/")
    if not normalized:
        return ()
    return (
        f"https://platform.openai.com/docs/models/{normalized}",
        f"https://platform.openai.com/docs/models/{normalized.lower()}",
    )


def _model_lookup_candidates(model_name: str) -> tuple[str, ...]:
    normalized = model_name.strip().lower()
    if not normalized:
        return ()
    candidates: list[str] = [normalized]
    for known_model in _KNOWN_MODEL_KNOWLEDGE_CUTOFFS:
        if known_model not in candidates and known_model in normalized:
            candidates.append(known_model)
    return tuple(candidates)


def _is_official_model_source_url(url: str) -> bool:
    normalized = url.strip().lower()
    return any(host in normalized for host in _OFFICIAL_MODEL_SOURCE_HOSTS)


def _fetch_text_from_url(url: str) -> str | None:
    try:
        request = Request(
            url=url,
            headers={"User-Agent": "aijurisdictionagents/model-knowledge-cutoff"},
        )
        with urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", payload))
    return re.sub(r"\s+", " ", text).strip()


def _extract_knowledge_cutoff_date(text: str) -> str | None:
    normalized_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized_text:
        return None
    patterns = (
        r"knowledge cutoff[:\s-]*([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})",
        r"([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})\s+knowledge cutoff",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match is None:
            continue
        parsed = _parse_knowledge_cutoff_date(match.group(1))
        if parsed is not None:
            return parsed
    return None


def _parse_knowledge_cutoff_date(raw_value: str) -> str | None:
    cleaned = str(raw_value or "").strip()
    if not cleaned:
        return None
    for date_format in _MONTH_NAME_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate


def _collector_progress_sqlite_row(
    *,
    conn: sqlite3.Connection,
    country_code: str,
) -> Sequence[Any] | None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'collector_progress'"
    ).fetchone()
    if exists is None:
        return None
    if country_code:
        return cast(
            Sequence[Any] | None,
            conn.execute(
                """
                SELECT country_code, source_system, last_collector_run_at, last_processed_law_year, last_processed_law_number
                FROM collector_progress
                WHERE UPPER(country_code) = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (country_code,),
            ).fetchone(),
        )
    return cast(
        Sequence[Any] | None,
        conn.execute(
            """
            SELECT country_code, source_system, last_collector_run_at, last_processed_law_year, last_processed_law_number
            FROM collector_progress
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone(),
    )


def _collector_progress_postgres_row(
    *,
    conn: Any,
    country_code: str,
) -> Sequence[Any] | None:
    relation = conn.execute("SELECT to_regclass(%s)", ("public.collector_progress",)).fetchone()
    if not relation or relation[0] is None:
        return None
    if country_code:
        return cast(
            Sequence[Any] | None,
            conn.execute(
                """
                SELECT country_code, source_system, last_collector_run_at, last_processed_law_year, last_processed_law_number
                FROM collector_progress
                WHERE UPPER(country_code) = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (country_code,),
            ).fetchone(),
        )
    return cast(
        Sequence[Any] | None,
        conn.execute(
            """
            SELECT country_code, source_system, last_collector_run_at, last_processed_law_year, last_processed_law_number
            FROM collector_progress
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone(),
    )


def _collector_progress_values(progress_row: Sequence[Any] | None) -> tuple[str | None, str | None]:
    if progress_row is None:
        return None, None
    country_code = str(progress_row[0]) if progress_row[0] is not None else ""
    source_system = str(progress_row[1]) if len(progress_row) > 1 and progress_row[1] is not None else ""
    last_collector_run_at_raw = progress_row[2] if len(progress_row) > 2 else None
    last_collector_run_at = (
        f"{last_collector_run_at_raw} ({country_code}:{source_system})"
        if last_collector_run_at_raw is not None and country_code and source_system
        else (str(last_collector_run_at_raw) if last_collector_run_at_raw is not None else None)
    )
    year = progress_row[3] if len(progress_row) > 3 else None
    number = progress_row[4] if len(progress_row) > 4 else None
    if year is None or number is None:
        return last_collector_run_at, None
    return last_collector_run_at, f"{int(number)}/{int(year)}"
