from __future__ import annotations

import importlib
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Sequence

from app.chat.models import Message, MessageRole, Session
from app.versioning import get_core_version

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

    knowledge_last_updated_at = _latest_legal_update_for_country(session.country)
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
            "knowledge_last_updated_at": knowledge_last_updated_at,
            "knowledge_last_updated_source": (
                "law_documents" if knowledge_last_updated_at else "unavailable"
            ),
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


def _latest_legal_update_for_country(country_code: str | None) -> str | None:
    normalized_country = (country_code or "").strip().upper()
    if not normalized_country:
        return None

    db_backend = os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower()
    db_local = os.getenv(
        "LAWS_DB_LOCAL",
        "./databases/laws-collector/sk_laws.sqlite3",
    ).strip()
    db_cloud = os.getenv("LAWS_DB_CLOUD", "").strip()

    if db_backend == "sqlite":
        db_path = _resolve_repo_path(db_local)
        if not db_path.exists():
            return None
        try:
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    """
                    SELECT MAX(last_stored_at)
                    FROM law_documents
                    WHERE UPPER(country_code) = ?
                    """,
                    (normalized_country,),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None or row[0] is None:
            return None
        return str(row[0])

    if db_backend == "postgres" and db_cloud:
        try:
            psycopg = importlib.import_module("psycopg")

            with psycopg.connect(db_cloud) as conn:
                row = conn.execute(
                    """
                    SELECT MAX(last_stored_at)
                    FROM law_documents
                    WHERE UPPER(country_code) = %s
                    """,
                    (normalized_country,),
                ).fetchone()
        except Exception:
            return None
        if row is None or row[0] is None:
            return None
        return str(row[0])

    return None


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
