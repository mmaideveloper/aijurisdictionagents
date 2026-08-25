from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import re
from typing import Any

import httpx

from aijurisdictionagents.agents import AIWebSearchAgent
from aijurisdictionagents.schemas import Document as CoreDocument
from services.court_decision_collector.query import parse_court_decision_query

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
_COURT_QUERY_MARKERS = (
    "sudne rozhodnut",
    "súdne rozhodnut",
    "sudnych rozhodnut",
    "súdnych rozhodnut",
    "rozhodnutia",
    "judikat",
    "judikát",
    "case law",
    "court decision",
    "court decisions",
    "okresneho sudu",
    "okresny sud",
)
_LEGAL_DOCUMENT_QUERY_MARKERS = (
    "zmluv",
    "dohod",
    "splnomocnen",
    "zalob",
    "žalob",
    "navrh",
    "návrh",
    "podanie",
    "dokument",
    "listin",
    "spis",
    "prevod obchodneho podielu",
    "prevod obchodného podielu",
    "najomn",
    "nájomn",
    "podnajm",
    "podnájm",
)
_OFFICIAL_LEGAL_SOURCE_HOSTS = (
    "slov-lex.sk",
    "obcan.justice.sk",
    "justice.gov.sk",
    "nsud.sk",
    "ustavnysud.sk",
)
_INTERNAL_MCP_SECRET_HEADER = "X-JurisDigta-Internal-MCP-Secret"


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
    web_search_approved: bool = False,
) -> McpLawContext | None:
    """Build law context through the same MCP law tools exposed to external assistants."""

    if not _should_use_mcp_law_context(query=query, country=country, language=language):
        return None

    if _should_search_court_decisions(query):
        if _is_latest_court_query(query):
            return _build_latest_court_context(
                query=query,
                search_limit=search_limit,
                language=language,
                web_search_approved=web_search_approved,
            )
        return _build_combined_legal_context(
            query=query,
            search_limit=max(search_limit, 5),
            text_limit=text_limit,
            max_chars_per_law=max_chars_per_law,
            language=language,
            web_search_approved=web_search_approved,
        )
    return _build_laws_only_context(
        query=query,
        search_limit=search_limit,
        text_limit=text_limit,
        max_chars_per_law=max_chars_per_law,
        language=language,
        web_search_approved=web_search_approved,
    )


def _build_latest_court_context(
    *, query: str, search_limit: int, language: str | None, web_search_approved: bool
) -> McpLawContext:
    profile = parse_court_decision_query(query)
    limit = profile.requested_limit or max(search_limit, 5)
    arguments: dict[str, Any] = {
        "query": profile.topic_query or query.strip(),
        "limit": limit,
        "sort": "latest",
        "include_snippets": True,
        "include_summaries": True,
    }
    court_name = _court_name_filter(query)
    if court_name:
        arguments["court_name"] = court_name
    try:
        payload = _call_mcp_tool("searchCourtDecisions", arguments)
        decisions = _tool_results(payload)[:limit]
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Internal MCP latest court-decision lookup failed", exc_info=True)
        return _unavailable_context(tool_calls=["searchCourtDecisions"], language=language)
    if not decisions:
        fallback = _official_web_fallback_context(
            query=query,
            reason="mcp_court_decisions_empty",
            language=language,
            web_search_approved=web_search_approved,
        )
        return fallback or _empty_context(query=query, tool_calls=["searchCourtDecisions"], language=language)
    coverage_notice = str(payload.get("coverage_notice") or "").strip()
    prompt_note = _prompt_note(
        query=query,
        search_arguments=arguments,
        laws=[],
        law_texts=[],
        court_decisions=decisions,
        fallback_records=[],
    )
    if coverage_notice:
        prompt_note += f"\n\nCORPUS COVERAGE NOTICE: {coverage_notice} Tell the user this limitation."
    return McpLawContext(
        prompt_note=prompt_note,
        document=CoreDocument(
            doc_id="internal-mcp-court-decision-context",
            path="internal-mcp-court-decision-context.txt",
            content=_document_content(laws=[], law_texts=[], court_decisions=decisions, fallback_records=[]),
        ),
        processing_event={
            "stage": "mcp_law_context",
            "message": _mcp_contact_notice(language),
            "details": {
                "tool_calls": ["searchCourtDecisions"],
                "result_count": len(decisions),
                "court_decision_count": len(decisions),
                "source_origin": "system_vector_db",
                "coverage": payload.get("coverage", {}),
                "coverage_notice": coverage_notice,
                "human_review_required": True,
                "citations": _court_decision_citations(decisions),
                "source_notice_i18n": _mcp_contact_notice_messages(),
                "user_visible": True,
                "web_search_status": "not_requested",
            },
        },
    )


def _build_laws_only_context(
    *,
    query: str,
    search_limit: int,
    text_limit: int,
    max_chars_per_law: int,
    language: str | None,
    web_search_approved: bool,
) -> McpLawContext:
    try:
        search_arguments = _search_arguments(query=query, limit=search_limit)
        search_payload = _call_mcp_tool("searchLaws", search_arguments)
        laws = _tool_results(search_payload)
        law_texts = [_law_text_payload(result=result, max_chars=max_chars_per_law) for result in laws[:text_limit]]
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Internal MCP law context lookup failed", exc_info=True)
        return _unavailable_context(tool_calls=["searchLaws"], language=language)

    if not laws:
        fallback = _official_web_fallback_context(
            query=query,
            reason="mcp_laws_empty",
            language=language,
            web_search_approved=web_search_approved,
        )
        return fallback or _empty_context(query=query, tool_calls=["searchLaws"], language=language)

    prompt_note = _prompt_note(
        query=query,
        search_arguments=search_arguments,
        laws=laws,
        law_texts=law_texts,
        court_decisions=[],
        fallback_records=[],
    )
    document = CoreDocument(
        doc_id="internal-mcp-law-context",
        path="internal-mcp-law-context.txt",
        content=_document_content(laws=laws, law_texts=law_texts, court_decisions=[], fallback_records=[]),
    )
    return McpLawContext(
        prompt_note=prompt_note,
        document=document,
        processing_event={
            "stage": "mcp_law_context",
            "message": _mcp_contact_notice(language),
            "details": {
                "tool_calls": ["searchLaws", *("getLawText" for _item in law_texts)],
                "result_count": len(laws),
                "document_ids": [str(result.get("document_id", "")) for result in laws],
                "source_origin": "system_vector_db",
                "citations": _law_citations(laws),
                "source_notice_i18n": _mcp_contact_notice_messages(),
                "user_visible": True,
                "web_search_status": "not_requested",
            },
        },
    )


def _build_combined_legal_context(
    *,
    query: str,
    search_limit: int,
    text_limit: int,
    max_chars_per_law: int,
    language: str | None,
    web_search_approved: bool,
) -> McpLawContext:
    try:
        search_arguments = {
            "query": query.strip(),
            "country_code": "SK",
            "source_types": ["laws", "court_decisions"],
            "limit_per_source": search_limit,
        }
        court_name = _court_name_filter(query)
        if court_name:
            search_arguments["court_name"] = court_name
        if _is_latest_court_query(query):
            search_arguments["sort"] = "latest"
        search_payload = _call_mcp_tool("searchLegalSources", search_arguments)
        laws = _tool_results_from_key(search_payload, "laws")
        court_decisions = _tool_results_from_key(search_payload, "court_decisions")[:search_limit]
        law_texts = [_law_text_payload(result=result, max_chars=max_chars_per_law) for result in laws[:text_limit]]
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Internal MCP combined legal source lookup failed", exc_info=True)
        return _unavailable_context(tool_calls=["searchLegalSources"], language=language)

    if not laws and not court_decisions:
        fallback = _official_web_fallback_context(
            query=query,
            reason="mcp_legal_sources_empty",
            language=language,
            web_search_approved=web_search_approved,
        )
        return fallback or _empty_context(
            query=query,
            tool_calls=["searchLegalSources"],
            language=language,
        )

    prompt_note = _prompt_note(
        query=query,
        search_arguments=search_arguments,
        laws=laws,
        law_texts=law_texts,
        court_decisions=court_decisions,
        fallback_records=[],
    )
    document = CoreDocument(
        doc_id="internal-mcp-legal-source-context",
        path="internal-mcp-legal-source-context.txt",
        content=_document_content(
            laws=laws,
            law_texts=law_texts,
            court_decisions=court_decisions,
            fallback_records=[],
        ),
    )
    return McpLawContext(
        prompt_note=prompt_note,
        document=document,
        processing_event={
            "stage": "mcp_law_context",
            "message": _mcp_contact_notice(language),
            "details": {
                "tool_calls": ["searchLegalSources", *("getLawText" for _item in law_texts)],
                "result_count": len(laws) + len(court_decisions),
                "law_count": len(laws),
                "court_decision_count": len(court_decisions),
                "source_origin": "system_vector_db",
                "citations": [*_law_citations(laws), *_court_decision_citations(court_decisions)],
                "source_notice_i18n": _mcp_contact_notice_messages(),
                "user_visible": True,
                "web_search_status": "not_requested",
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
    return any(
        marker in normalized_query
        for marker in (*_LEGAL_QUERY_MARKERS, *_COURT_QUERY_MARKERS, *_LEGAL_DOCUMENT_QUERY_MARKERS)
    )


def _should_search_court_decisions(query: str) -> bool:
    normalized_query = _canonical(query)
    return any(marker in normalized_query for marker in _COURT_QUERY_MARKERS)


def _search_arguments(*, query: str, limit: int) -> dict[str, Any]:
    match = _LAW_IDENTIFIER_RE.search(query)
    search_query = query.strip()
    latest_law_query = _is_latest_law_query(query)
    if match is not None:
        search_query = f"{int(match.group('number'))}/{int(match.group('year'))}"
    elif latest_law_query:
        search_query = "zakon"
    arguments: dict[str, Any] = {
        "query": search_query,
        "country_code": "SK",
        "limit": 1 if latest_law_query else limit,
    }
    if latest_law_query:
        arguments["sort"] = "latest"
    if match is not None:
        arguments["law_number"] = int(match.group("number"))
        arguments["law_year"] = int(match.group("year"))
    return arguments


def _is_latest_law_query(query: str) -> bool:
    normalized = _canonical(query)
    if "zmen" in normalized or "podla posled" in normalized:
        return False
    latest_then_law = re.search(
        r"\b(posledn\w*|najnovs\w*|latest|newest|last)\b(?:\s+\w+){0,3}\s+"
        r"(zakon\w*|pravny predpis|law|statute)\b",
        normalized,
    )
    law_then_latest = re.search(
        r"\b(zakon\w*|pravny predpis|law|statute)\b(?:\s+\w+){0,3}\s+"
        r"(posledn\w*|najnovs\w*|latest|newest|last)\b",
        normalized,
    )
    return latest_then_law is not None or law_then_latest is not None


def _is_latest_court_query(query: str) -> bool:
    normalized = _canonical(query)
    return bool(re.search(r"\b(posledn\w*|najnovs\w*|latest|newest)\b", normalized))


def _court_name_filter(query: str) -> str | None:
    normalized = _canonical(query)
    match = re.search(r"\bokresn(?:y|eho)\s+sud(?:u)?\s+([a-z][a-z-]*)\b", normalized)
    if match is None:
        return None
    city = match.group(1)
    return f"Okresny sud {city.title()}"


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
    remote_base_url = _remote_mcp_base_url()
    if remote_base_url:
        return _call_remote_mcp_tool(remote_base_url=remote_base_url, name=name, arguments=arguments)

    from app.mcp_api import _call_tool

    payload = _call_tool(name, arguments)
    return payload if isinstance(payload, dict) else {}


def _remote_mcp_base_url() -> str:
    raw_value = os.getenv("INTERNAL_MCP_BASE_URL", os.getenv("MCP_PUBLIC_BASE_URL", "")).strip()
    if raw_value in {"", "unknown-variable"}:
        return ""
    return raw_value.rstrip("/")


def _call_remote_mcp_tool(*, remote_base_url: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments,
        },
    }
    headers = {"Content-Type": "application/json"}
    internal_secret = _internal_mcp_shared_secret()
    if internal_secret:
        headers[_INTERNAL_MCP_SECRET_HEADER] = internal_secret
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{remote_base_url}/mcp",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        envelope = response.json()
    if not isinstance(envelope, dict):
        return {}
    error = envelope.get("error")
    if error:
        raise RuntimeError(f"MCP tool {name} failed: {error}")
    result = envelope.get("result")
    if not isinstance(result, dict):
        return {}
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return {}
    first = content[0]
    if not isinstance(first, dict):
        return {}
    text = first.get("text")
    if not isinstance(text, str) or not text.strip():
        return {}
    decoded = json.loads(text)
    return decoded if isinstance(decoded, dict) else {}


def _internal_mcp_shared_secret() -> str:
    raw_value = os.getenv("INTERNAL_MCP_SHARED_SECRET", "").strip()
    if raw_value in {"", "unknown-variable"}:
        raw_value = os.getenv("MCP_API_JWT_SECRET", "").strip()
    return "" if raw_value in {"", "unknown-variable"} else raw_value


def _tool_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return []
    return [item for item in raw_results if isinstance(item, dict)]


def _tool_results_from_key(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw_results = payload.get(key, [])
    if not isinstance(raw_results, list):
        return []
    return [item for item in raw_results if isinstance(item, dict)]


def _prompt_note(
    *,
    query: str,
    search_arguments: dict[str, Any],
    laws: list[dict[str, Any]],
    law_texts: list[dict[str, Any]],
    court_decisions: list[dict[str, Any]],
    fallback_records: list[dict[str, str]],
) -> str:
    lines = [
        "INTERNAL MCP LAW TOOL CONTEXT:",
        "- The assistant backend has already queried JurisDigta MCP tools for this Slovak legal turn whenever system data was available.",
        "- Treat JurisDigta MCP results as the mandatory current-law and case-law source before answering from model memory.",
        "- Cite the law identifier and relevant section/paragraph when available; cite court decisions as case-law support, not binding statutory text.",
        "- If the legal conclusion depends on effective wording, amendment status, or missing facts, say so explicitly.",
        "- Do not invent legal citations that are not present in the MCP or official-source fallback results.",
        "- Do not show raw MCP JSON, raw tool output, or internal field names to the user; turn the data into a short human-readable answer.",
        f"- Tool path: {_tool_path_label(search_arguments)}.",
        f"- MCP search arguments: {_compact_json(search_arguments)}",
        f"- User query: {query.strip()}",
        "",
        "MCP law results:",
    ]
    if search_arguments.get("sort") == "latest":
        lines.insert(
            6,
            "- The user asked for the latest law in the JurisDigta system; use the first MCP law result as the latest imported law.",
        )
    for index, result in enumerate(laws, start=1):
        lines.append(
            f"{index}. document_id={result.get('document_id', '')}; "
            f"identifier={result.get('law_identifier_text', '')}; "
            f"title={result.get('title') or result.get('lawyer_title') or result.get('official_name') or ''}"
        )
    if court_decisions:
        lines.extend(["", "MCP court-decision results:"])
    for index, decision in enumerate(court_decisions, start=1):
        summary = str(decision.get("summary") or decision.get("snippet") or "").strip()
        lines.append(f"{index}. {_court_decision_label(decision)}; summary={summary}")
    if law_texts:
        lines.extend(["", "MCP getLawText excerpts:"])
    for index, text_payload in enumerate(law_texts, start=1):
        lines.append(
            f"{index}. identifier={text_payload.get('law_identifier_text', '')}; "
            f"title={text_payload.get('title') or text_payload.get('official_name') or ''}; "
            f"content={str(text_payload.get('content_text', '')).strip()}"
        )
    if fallback_records:
        lines.extend(
            [
                "",
                "OFFICIAL WEB FALLBACK RESULTS:",
                "- WARNING: These sources came from AIWebSearchAgent official web fallback, not from JurisDigta system vector DB.",
                "- Tell the user that human legal review is required before relying on these fallback sources.",
            ]
        )
    for index, record in enumerate(fallback_records, start=1):
        lines.append(f"{index}. title={record.get('title', '')}; url={record.get('url', '')}; snippet={record.get('snippet', '')}")
    return "\n".join(lines).strip()


def _document_content(
    *,
    laws: list[dict[str, Any]],
    law_texts: list[dict[str, Any]],
    court_decisions: list[dict[str, Any]],
    fallback_records: list[dict[str, str]],
) -> str:
    lines = ["JurisDigta legal retrieval context", "", "Law search results:"]
    for result in laws:
        lines.append(
            f"- {result.get('law_identifier_text', '')}: "
            f"{result.get('title') or result.get('lawyer_title') or result.get('official_name') or ''} "
            f"(document_id={result.get('document_id', '')})"
        )
    if court_decisions:
        lines.extend(["", "Court-decision search results:"])
    for decision in court_decisions:
        summary = str(decision.get("summary") or decision.get("snippet") or "").strip()
        lines.append(f"- {_court_decision_label(decision)}\n  Summary: {summary}")
    if law_texts:
        lines.extend(["", "Law text excerpts:"])
    for payload in law_texts:
        lines.append(
            f"\n{payload.get('law_identifier_text', '')} "
            f"{payload.get('title') or payload.get('official_name') or ''}\n"
            f"{str(payload.get('content_text', '')).strip()}"
        )
    if fallback_records:
        lines.extend(["", "Official web fallback results:"])
    for record in fallback_records:
        lines.append(f"- {record.get('title', '')}: {record.get('url', '')} - {record.get('snippet', '')}")
    return "\n".join(lines).strip()


def _empty_context(*, query: str, tool_calls: list[str], language: str | None) -> McpLawContext:
    return McpLawContext(
        prompt_note=(
            "INTERNAL MCP LAW TOOL CONTEXT:\n"
            "- JurisDigta MCP legal-source search was called for this Slovak legal turn but returned no matching source.\n"
            f"- User query: {query.strip()}\n"
            "- AIWebSearchAgent internet fallback was not used because this turn has no explicit user approval for external web search.\n"
            "- Tell the user that current-law lookup did not find a matching source and avoid exact legal citations."
        ),
        document=None,
        processing_event={
            "stage": "mcp_law_context",
            "message": _mcp_contact_notice(language),
            "details": {
                "tool_calls": tool_calls,
                "result_count": 0,
                "source_origin": "system_vector_db",
                "source_notice_i18n": _mcp_contact_notice_messages(),
                "user_visible": True,
                "web_search_status": "blocked_pending_user_approval",
                "web_search_approval_required": True,
            },
        },
    )


def _unavailable_context(*, tool_calls: list[str], language: str | None) -> McpLawContext:
    return McpLawContext(
        prompt_note=(
            "INTERNAL MCP LAW TOOL CONTEXT:\n"
            "- JurisDigta MCP law lookup was attempted but is temporarily unavailable.\n"
            "- AIWebSearchAgent internet fallback was not used because this turn has no explicit user approval for external web search.\n"
            "- Be transparent that current-law verification could not be completed in this turn.\n"
            "- Avoid exact legal citations unless they are already present in uploaded documents or case history."
        ),
        document=None,
        processing_event={
            "stage": "mcp_law_context",
            "message": _mcp_contact_notice(language),
            "details": {
                "tool_calls": tool_calls,
                "status": "unavailable",
                "source_notice_i18n": _mcp_contact_notice_messages(),
                "user_visible": True,
                "web_search_status": "blocked_pending_user_approval",
                "web_search_approval_required": True,
            },
        },
    )


def _compact_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tool_path_label(search_arguments: dict[str, Any]) -> str:
    if str(search_arguments.get("fallback") or "") == "AIWebSearchAgent":
        return "AIWebSearchAgent"
    if search_arguments.get("source_types"):
        return "searchLegalSources"
    return "searchLaws -> getLawText"


def _canonical(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_only).strip()


def _official_web_fallback_context(
    *,
    query: str,
    reason: str,
    language: str | None,
    web_search_approved: bool,
) -> McpLawContext | None:
    if not web_search_approved:
        return None
    records = _official_web_fallback_records(query=query)
    if not records:
        return None
    prompt_note = _prompt_note(
        query=query,
        search_arguments={"query": query.strip(), "fallback": "AIWebSearchAgent", "official_sources_only": True},
        laws=[],
        law_texts=[],
        court_decisions=[],
        fallback_records=records,
    )
    return McpLawContext(
        prompt_note=prompt_note,
        document=CoreDocument(
            doc_id="official-web-legal-fallback-context",
            path="official-web-legal-fallback-context.txt",
            content=_document_content(laws=[], law_texts=[], court_decisions=[], fallback_records=records),
        ),
        processing_event={
            "stage": "mcp_law_context",
            "message": "Official web fallback used because JurisDigta MCP returned no legal source.",
            "details": {
                "tool_calls": ["searchLegalSources", "AIWebSearchAgent"],
                "result_count": len(records),
                "fallback_reason": reason,
                "source_origin": "official_web_fallback",
                "mcp_contact_notice": _mcp_contact_notice(language),
                "source_notice_i18n": _mcp_contact_notice_messages(),
                "web_search_status": "approved",
                "web_search_approved": True,
                "warning_required": True,
                "human_review_required": True,
                "warning": (
                    "Legal sources were retrieved from AIWebSearchAgent official web fallback, "
                    "not from the JurisDigta system vector database."
                ),
                "citations": _web_citations(records),
            },
        },
    )


def _official_web_fallback_records(*, query: str) -> list[dict[str, str]]:
    try:
        records = AIWebSearchAgent().search(
            query=f"{query.strip()} site:slov-lex.sk OR site:obcan.justice.sk OR site:justice.gov.sk",
            max_results=5,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.warning("AIWebSearchAgent official legal fallback failed", exc_info=True)
        return []
    fallback_records: list[dict[str, str]] = []
    for record in records:
        url = str(record.url).strip()
        if not _is_official_legal_source_url(url):
            continue
        fallback_records.append(
            {
                "title": str(record.title).strip(),
                "url": url,
                "snippet": str(record.snippet).strip(),
            }
        )
    return fallback_records


def _mcp_contact_notice(language: str | None) -> str:
    normalized = (language or "").strip().lower()
    messages = _mcp_contact_notice_messages()
    if normalized.startswith("sk"):
        return messages["sk"]
    if normalized.startswith("de") or normalized.startswith("ge"):
        return messages["de"]
    return messages["en"]


def _mcp_contact_notice_messages() -> dict[str, str]:
    return {
        "sk": "JurisDigta MCP server bol kontaktovaný na získanie najnovších právnych informácií.",
        "de": "Der JurisDigta MCP-Server wurde kontaktiert, um aktuelle Rechtsinformationen abzurufen.",
        "en": "JurisDigta MCP Server was contacted to retrieve the latest legal information.",
    }


def _is_official_legal_source_url(url: str) -> bool:
    normalized = url.strip().lower()
    return any(host in normalized for host in _OFFICIAL_LEGAL_SOURCE_HOSTS)


def _law_citations(laws: list[dict[str, Any]]) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    for result in laws:
        label = str(result.get("law_identifier_text") or "").strip()
        title = str(result.get("title") or result.get("lawyer_title") or result.get("official_name") or label).strip()
        citations.append(
            {
                "source_type": "law",
                "source_id": str(result.get("document_id") or "").strip() or None,
                "source_url": str(result.get("source_url") or "").strip() or None,
                "title": title or "Law",
                "citation_label": label or title or "Law",
                "law_number": label or None,
                "effective_from": str(result.get("effective_from") or "").strip() or None,
                "retrieval_tool": "JurisDigta MCP searchLaws",
                "relevance_score": 1.0,
            }
        )
    return citations


def _court_decision_citations(court_decisions: list[dict[str, Any]]) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    for decision in court_decisions:
        label = _court_decision_label(decision)
        citations.append(
            {
                "source_type": "court_decision",
                "source_id": str(decision.get("decision_id") or "").strip() or None,
                "source_url": str(decision.get("source_url") or "").strip() or None,
                "title": label,
                "citation_label": label,
                "court": str(decision.get("court_name") or "").strip() or None,
                "ecli": str(decision.get("ecli") or "").strip() or None,
                "file_number": str(decision.get("file_number") or decision.get("case_number") or "").strip() or None,
                "decision_date": str(decision.get("issue_date") or "").strip() or None,
                "snippet": str(decision.get("snippet") or "").strip() or None,
                "retrieval_tool": "JurisDigta MCP searchCourtDecisions",
                "relevance_score": _optional_score(decision.get("score"), default=1.0),
            }
        )
    return citations


def _web_citations(records: list[dict[str, str]]) -> list[dict[str, object]]:
    return [
        {
            "source_type": "web",
            "source_id": record["url"],
            "source_url": record["url"],
            "title": record["title"] or record["url"],
            "citation_label": record["title"] or record["url"],
            "snippet": record["snippet"],
            "retrieval_tool": "AIWebSearchAgent official web fallback",
            "relevance_score": 0.9,
        }
        for record in records
    ]


def _court_decision_label(decision: dict[str, Any]) -> str:
    court = str(decision.get("court_name") or "").strip()
    file_number = str(decision.get("file_number") or decision.get("case_number") or "").strip()
    ecli = str(decision.get("ecli") or "").strip()
    issue_date = str(decision.get("issue_date") or "").strip()
    year = issue_date[:4] if len(issue_date) >= 4 else ""
    reference = ecli or file_number or str(decision.get("decision_id") or "").strip()
    parts = [part for part in (court, reference, year or issue_date) if part]
    return " - ".join(parts) if parts else "Court decision"


def _optional_score(value: object, *, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default
