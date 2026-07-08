from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from aijurisdictionagents.schemas import Document as CoreDocument

from app.chat.mcp_law_context import _call_mcp_tool

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpStatusContext:
    prompt_note: str
    document: CoreDocument | None
    processing_event: dict[str, object]


def build_mcp_status_context(
    *,
    query: str,
    country: str,
    language: str | None,
) -> McpStatusContext | None:
    """Build aggregate JurisDigta MCP status context for model formatting."""

    if not _should_use_mcp_status_context(query=query, country=country, language=language):
        return None

    try:
        version_payload = _call_mcp_tool("getVersion", {})
        statistics_payload = _call_mcp_tool("getStatistics", {"country_code": "SK"})
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Internal MCP status/statistics lookup failed", exc_info=True)
        return McpStatusContext(
            prompt_note=(
                "INTERNAL MCP STATUS CONTEXT:\n"
                "- JurisDigta MCP getVersion and getStatistics were attempted but are temporarily unavailable.\n"
                "- Tell the user the MCP status could not be verified in this turn and do not invent version, law count, "
                "or jurisdiction values."
            ),
            document=None,
            processing_event={
                "stage": "mcp_status_context",
                "message": "JurisDigta MCP status/statistics lookup is temporarily unavailable.",
                "details": {"tool_calls": ["getVersion", "getStatistics"], "status": "unavailable"},
            },
        )

    status_payload = {
        "getVersion": version_payload,
        "getStatistics": statistics_payload,
    }
    prompt_note = (
        "INTERNAL MCP STATUS CONTEXT:\n"
        "- The assistant backend has already queried JurisDigta MCP tools getVersion and getStatistics.\n"
        "- Use only the JSON below for MCP version, imported law count, and jurisdiction/statistics values.\n"
        "- Format the JSON into a short, readable Slovak preview for the user.\n"
        "- Do not invent or estimate values that are missing from this JSON; say that a value is unavailable instead.\n"
        f"- User query: {query.strip()}\n"
        f"- MCP JSON: {_compact_json(status_payload)}"
    )
    return McpStatusContext(
        prompt_note=prompt_note,
        document=CoreDocument(
            doc_id="internal-mcp-status-context",
            path="internal-mcp-status-context.json",
            content=json.dumps(status_payload, ensure_ascii=False, indent=2, sort_keys=True),
        ),
        processing_event={
            "stage": "mcp_status_context",
            "message": "JurisDigta MCP getVersion and getStatistics returned aggregate status data.",
            "details": {
                "tool_calls": ["getVersion", "getStatistics"],
                "source_origin": "jurisdigta_mcp",
                "result_count": 2,
                "country_code": "SK",
            },
        },
    )


def _should_use_mcp_status_context(*, query: str, country: str, language: str | None) -> bool:
    normalized_country = country.strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country != "SK" and not normalized_language.startswith("sk"):
        return False
    normalized_query = _canonical(query)
    status_markers = (
        "verzi",
        "version",
        "server",
        "servr",
        "system",
        "sistem",
        "statistik",
        "statistics",
        "importovan",
        "import",
        "zakon",
        "jurisdik",
    )
    if "mcp" in normalized_query:
        return any(marker in normalized_query for marker in status_markers)

    imported_law_count_patterns = (
        r"\bkolko\b.*\bzakon\w*\b.*\b(importovan\w*|system\w*|sistem\w*)",
        r"\bkolko\b.*\b(importovan\w*)\b.*\bzakon\w*\b",
        r"\b(pocet|count|number)\b.*\b(importovan\w*|imported)\b.*\b(zakon\w*|laws?)\b",
        r"\b(importovan\w*|imported)\b.*\b(zakon\w*|laws?)\b.*\b(pocet|count|number)\b",
    )
    return any(re.search(pattern, normalized_query) for pattern in imported_law_count_patterns)


def _compact_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_only).strip()
