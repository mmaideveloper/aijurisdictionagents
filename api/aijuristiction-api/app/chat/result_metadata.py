from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Sequence, cast

from app.chat.models import Message, MessageRole, Session
from app.versioning import get_api_version, get_core_version

from aijurisdictionagents.agents import AIAgentsValidator, ValidatorInputs
from aijurisdictionagents.agents.validator import EvaluationCriterion

_REPO_ROOT = Path(__file__).resolve().parents[4]

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
    reference_links: tuple[str, ...] = ()


def build_session_result_metadata(
    *,
    session: Session,
    messages: Sequence[Message],
    final_recommendation: str,
    base_metadata: dict[str, Any] | None = None,
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

    knowledge_snapshot = get_law_knowledge_snapshot(session.country)
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
            "model_knowledge_cutoff_date": knowledge_snapshot.model_knowledge_cutoff_date,
            "model_knowledge_cutoff_source": knowledge_snapshot.model_knowledge_cutoff_source,
            "law_reference_links": list(knowledge_snapshot.reference_links),
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


def get_law_knowledge_snapshot(country_code: str | None) -> LawKnowledgeSnapshot:
    normalized_country = (country_code or "").strip().upper()
    scope = "country" if normalized_country else "global"
    model_cutoff = _read_or_create_model_knowledge_cutoff_snapshot()

    db_backend = os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower()
    db_local = os.getenv(
        "LAWS_DB_LOCAL",
        "./databases/laws-collector/sk_laws.sqlite3",
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
                    row = _fetchone_sqlite(
                        conn=conn,
                        query=_law_snapshot_sqlite_query(filtered=False),
                    )
        except sqlite3.Error:
            return _law_snapshot_without_db(model_cutoff=model_cutoff)
        snapshot = _law_snapshot_from_row(row, scope=scope, model_cutoff=model_cutoff)
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
                    row = _fetchone_postgres(
                        conn=conn,
                        query=_law_snapshot_postgres_query(filtered=False),
                    )
        except Exception:
            return _law_snapshot_without_db(model_cutoff=model_cutoff)
        snapshot = _law_snapshot_from_row(row, scope=scope, model_cutoff=model_cutoff)
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
) -> LawKnowledgeSnapshot:
    if row is None:
        return _law_snapshot_without_db(
            model_cutoff=model_cutoff,
            reference_links=(),
        )
    latest_update = row[0]
    raw_links = row[1] if len(row) > 1 else None
    links = _parse_reference_links(raw_links)
    if latest_update is None:
        return _law_snapshot_without_db(
            model_cutoff=model_cutoff,
            reference_links=links,
        )
    return LawKnowledgeSnapshot(
        last_law_update_date=str(latest_update),
        last_law_update_source=f"law_documents_{scope}",
        model_knowledge_cutoff_date=model_cutoff[0],
        model_knowledge_cutoff_source=model_cutoff[1],
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
    reference_links: tuple[str, ...] = (),
) -> LawKnowledgeSnapshot:
    return LawKnowledgeSnapshot(
        last_law_update_date=None,
        last_law_update_source="unavailable",
        model_knowledge_cutoff_date=model_cutoff[0],
        model_knowledge_cutoff_source=model_cutoff[1],
        reference_links=reference_links,
    )


def _read_or_create_model_knowledge_cutoff_snapshot() -> tuple[str | None, str]:
    cache_path = _resolve_repo_path(
        os.getenv(
            "MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE",
            "./databases/model_knowledge_cutoff_cache.json",
        ).strip()
    )
    cached_snapshot = _read_model_knowledge_cutoff_cache(cache_path)
    if cached_snapshot is not None:
        return cached_snapshot

    configured_cutoff = os.getenv("MODEL_KNOWLEDGE_CUTOFF_DATE", "").strip()
    if not configured_cutoff:
        return (None, "unavailable")

    snapshot = (configured_cutoff, "model_knowledge_cutoff_cache")
    _write_model_knowledge_cutoff_cache(cache_path, snapshot)
    return snapshot


def _read_model_knowledge_cutoff_cache(cache_path: Path) -> tuple[str, str] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    cutoff_date = str(payload.get("model_knowledge_cutoff_date") or "").strip()
    if not cutoff_date:
        return None
    source = str(payload.get("source") or "model_knowledge_cutoff_cache").strip()
    return (cutoff_date, source or "model_knowledge_cutoff_cache")


def _write_model_knowledge_cutoff_cache(
    cache_path: Path,
    snapshot: tuple[str | None, str],
) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "model_knowledge_cutoff_date": snapshot[0],
                    "source": snapshot[1],
                    "provider": os.getenv("LLM_PROVIDER", "").strip().lower(),
                    "deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip(),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
