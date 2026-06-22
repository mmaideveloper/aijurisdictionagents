from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any

from aijurisdictionagents.schemas import Document as CoreDocument

_LOGGER = logging.getLogger(__name__)
_LAW_IDENTIFIER_RE = re.compile(r"\b(?P<number>\d{1,4})\s*/\s*(?P<year>\d{4})\b")
_SECTION_RE = re.compile(r"(?:§|paragraf(?:u|om)?)\s*(?P<section>\d+[a-zA-Z]?)", re.IGNORECASE)
_LEGAL_QUERY_MARKERS = (
    "zakon",
    "zákon",
    "paragraf",
    "§",
    "pravny predpis",
    "právny predpis",
    "aktualne znenie",
    "aktuálne znenie",
    "ucinne znenie",
    "účinné znenie",
    "cituj",
    "citacia",
    "citácia",
    "obciansk",
    "občiansk",
    "obchodny zakonnik",
    "obchodný zákonník",
    "zakonnik prace",
    "zákonník práce",
    "family act",
    "civil code",
    "commercial code",
    "labour code",
    "law",
    "statute",
    "section",
)


@dataclass(frozen=True)
class McpLawContext:
    prompt_note: str
    document: CoreDocument | None
    processing_event: dict[str, object]


def build_mcp_law_context(
    *,
    query: str,
    country: str,
    language: str | None,
    search_limit: int = 3,
    text_limit: int = 2,
    max_chars_per_law: int = 3000,
) -> McpLawContext | None:
    """Build law context through the same MCP law tools exposed to external assistants."""

    if not _should_use_mcp_law_context(query=query, country=country, language=language):
        return None

    try:
        search_arguments = _search_arguments(query=query, limit=search_limit)
        search_payload = _call_mcp_tool("searchLaws", search_arguments)
        results = _tool_results(search_payload)
        law_texts = [
            _law_text_payload(result=result, max_chars=max_chars_per_law)
            for result in results[:text_limit]
        ]
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Internal MCP law context lookup failed", exc_info=True)
        return _unavailable_context()

    if not results:
        return _empty_context(query=query)

    prompt_note = _prompt_note(
        query=query,
        search_arguments=search_arguments,
        results=results,
        law_texts=law_texts,
    )
    document = CoreDocument(
        doc_id="internal-mcp-law-context",
        path="internal-mcp-law-context.txt",
        content=_document_content(results=results, law_texts=law_texts),
    )
    return McpLawContext(
        prompt_note=prompt_note,
        document=document,
        processing_event={
            "stage": "mcp_law_context",
            "message": "JurisDigta MCP law tools searched current Slovak law context.",
            "details": {
                "tool_calls": ["searchLaws", *("getLawText" for _item in law_texts)],
                "result_count": len(results),
                "document_ids": [str(result.get("document_id", "")) for result in results],
            },
        },
    )


def _should_use_mcp_law_context(*, query: str, country: str, language: str | None) -> bool:
    normalized_country = country.strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country != "SK" and not normalized_language.startswith("sk"):
        return False
    normalized_query = _canonical(query)
    if _LAW_IDENTIFIER_RE.search(query):
        return True
    return any(marker in normalized_query for marker in _LEGAL_QUERY_MARKERS)


def _search_arguments(*, query: str, limit: int) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "query": query.strip(),
        "country_code": "SK",
        "limit": limit,
    }
    match = _LAW_IDENTIFIER_RE.search(query)
    if match is not None:
        arguments["law_number"] = int(match.group("number"))
        arguments["law_year"] = int(match.group("year"))
    return arguments


def _law_text_payload(*, result: dict[str, Any], max_chars: int) -> dict[str, Any]:
    document_id = str(result.get("document_id", "")).strip()
    if not document_id:
        return {}
    arguments: dict[str, Any] = {
        "document_id": document_id,
        "max_chars": max_chars,
    }
    section = _section_start_from_query(str(result.get("matched_query", "")))
    if section:
        arguments["section_start"] = section
    return _call_mcp_tool("getLawText", arguments)


def _section_start_from_query(query: str) -> str:
    match = _SECTION_RE.search(query)
    return match.group("section") if match is not None else ""


def _call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.mcp_api import _call_tool

    payload = _call_tool(name, arguments)
    return payload if isinstance(payload, dict) else {}


def _tool_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return []
    return [item for item in raw_results if isinstance(item, dict)]


def _prompt_note(
    *,
    query: str,
    search_arguments: dict[str, Any],
    results: list[dict[str, Any]],
    law_texts: list[dict[str, Any]],
) -> str:
    lines = [
        "INTERNAL MCP LAW TOOL CONTEXT:",
        "- The assistant backend has already queried JurisDigta MCP tools for this Slovak legal turn.",
        "- Treat these results as the mandatory current-law source before answering from model memory.",
        "- Cite the law identifier and relevant section/paragraph when available.",
        "- If the legal conclusion depends on effective wording, amendment status, or missing facts, say so explicitly.",
        "- Do not invent legal citations that are not present in the MCP results.",
        f"- MCP searchLaws arguments: {_compact_json(search_arguments)}",
        f"- User query: {query.strip()}",
        "",
        "MCP searchLaws results:",
    ]
    for index, result in enumerate(results, start=1):
        lines.append(
            f"{index}. document_id={result.get('document_id', '')}; "
            f"identifier={result.get('law_identifier_text', '')}; "
            f"title={result.get('title') or result.get('lawyer_title') or result.get('official_name') or ''}"
        )
    if law_texts:
        lines.extend(["", "MCP getLawText excerpts:"])
    for index, text_payload in enumerate(law_texts, start=1):
        lines.append(
            f"{index}. identifier={text_payload.get('law_identifier_text', '')}; "
            f"title={text_payload.get('title') or text_payload.get('official_name') or ''}; "
            f"content={str(text_payload.get('content_text', '')).strip()}"
        )
    return "\n".join(lines).strip()


def _document_content(*, results: list[dict[str, Any]], law_texts: list[dict[str, Any]]) -> str:
    lines = ["JurisDigta MCP law context", "", "Search results:"]
    for result in results:
        lines.append(
            f"- {result.get('law_identifier_text', '')}: "
            f"{result.get('title') or result.get('lawyer_title') or result.get('official_name') or ''} "
            f"(document_id={result.get('document_id', '')})"
        )
    if law_texts:
        lines.extend(["", "Law text excerpts:"])
    for payload in law_texts:
        lines.append(
            f"\n{payload.get('law_identifier_text', '')} "
            f"{payload.get('title') or payload.get('official_name') or ''}\n"
            f"{str(payload.get('content_text', '')).strip()}"
        )
    return "\n".join(lines).strip()


def _empty_context(*, query: str) -> McpLawContext:
    return McpLawContext(
        prompt_note=(
            "INTERNAL MCP LAW TOOL CONTEXT:\n"
            "- JurisDigta MCP searchLaws was called for this Slovak legal turn but returned no matching law.\n"
            f"- User query: {query.strip()}\n"
            "- Tell the user that current-law lookup did not find a matching source and avoid exact legal citations."
        ),
        document=None,
        processing_event={
            "stage": "mcp_law_context",
            "message": "JurisDigta MCP law search returned no matching law context.",
            "details": {"tool_calls": ["searchLaws"], "result_count": 0},
        },
    )


def _unavailable_context() -> McpLawContext:
    return McpLawContext(
        prompt_note=(
            "INTERNAL MCP LAW TOOL CONTEXT:\n"
            "- JurisDigta MCP law lookup was attempted but is temporarily unavailable.\n"
            "- Be transparent that current-law verification could not be completed in this turn.\n"
            "- Avoid exact legal citations unless they are already present in uploaded documents or case history."
        ),
        document=None,
        processing_event={
            "stage": "mcp_law_context",
            "message": "JurisDigta MCP law lookup is temporarily unavailable.",
            "details": {"tool_calls": ["searchLaws"], "status": "unavailable"},
        },
    )


def _compact_json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_only).strip()
