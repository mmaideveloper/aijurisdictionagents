"""API-owned Release 1 tool registrations; clients never grant tool permission."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Sequence, cast

from aijurisdictionagents.llm.base import LLMClient
from aijurisdictionagents.llm.tool_loop import (
    LoopResult, RELEASE_ONE_TOOLS, RegisteredTool, run_tool_loop, run_read_only,
)
from aijurisdictionagents.llm.turn_context import legacy_turn_context
from aijurisdictionagents.llm.turn_contracts import ToolDefinition
from aijurisdictionagents.schemas import Document, Message

# Recursive allowlist drops raw provider/debug/credential fields. Legislation is
# public evidence; courts and external/personal-data tools are never registered.
_FIELDS = frozenset({
    "results", "laws", "items", "document_id", "law_id", "id", "title", "text", "content",
    "law_number", "law_year", "law_identifier", "law_identifier_text", "source_url",
    "country_code", "effective_from", "effective_to", "section_number", "paragraph_number",
    "sections", "paragraphs", "citations", "source_id", "locator", "version", "api",
    "content_text", "version_id", "version_token", "section_text", "heading",
    "api_version", "mcp_server_version", "system_version", "mobile_app_version", "web_app_version",
    "processed_laws", "last_processed_law", "last_processed_day",
    "system", "mobile", "web", "total", "total_laws", "laws_total", "countries", "status",
    "statistics", "count", "jurisdictions", "summary", "snippet", "provision_id",
})
_DESCRIPTIONS = {
    "searchLaws": "Search public Slovak legislation. For a numbered act, query only its number/year, "
                  "for example 661/2026, without surrounding words. Results supply document_id. "
                  "If there are no results, disclose missing evidence; never invent a document_id.",
    "getLawText": "Read a law using the exact document_id returned by searchLaws or supplied evidence. "
                  "A law number such as 661/2026 is not a document_id. Never guess this identifier. "
                  "Use section_number to request a specific paragraph marked §.",
    "getVersion": "Read public API, MCP, system, mobile and web application versions.",
    "getStatistics": "Read aggregate public legislation counts and import status for Slovakia.",
}


def sanitize_public_result(payload: dict[str, Any]) -> dict[str, Any]:
    def clean(value: Any, depth: int = 0) -> Any:
        if depth > 6:
            return None
        if isinstance(value, dict):
            return {key: clean(item, depth + 1) for key, item in value.items() if key in _FIELDS}
        if isinstance(value, list):
            return [clean(item, depth + 1) for item in value[:20]]
        if isinstance(value, str):
            return "".join(ch for ch in value[:8000] if ch >= " " or ch in "\n\t")
        return value if value is None or isinstance(value, (int, float, bool)) else None
    return dict(clean(payload))


def registrations(client: Any) -> tuple[RegisteredTool, ...]:
    from app.mcp_api import _mcp_tools
    from app.chat.mcp_law_context import _call_mcp_tool

    def authorize() -> bool:
        # An authenticated privacy wrapper is mandatory; no anonymous bypass.
        check = getattr(client, "authorize_internal_tool", None)
        return bool(check and check())

    result = []
    for row in _mcp_tools():
        name = row["name"]
        if name not in RELEASE_ONE_TOOLS:
            continue
        schema = row["inputSchema"]
        # Model-driven retrieval has tighter bounds than the general MCP surface.
        properties = schema.get("properties", {})
        if "query" in properties:
            properties["query"]["maxLength"] = 1000
        if "limit" in properties:
            properties["limit"]["maximum"] = 10
        if "max_chars" in properties:
            properties["max_chars"]["maximum"] = 8000
        if "country_code" in properties:
            properties["country_code"]["enum"] = ["SK"]

        async def execute(arguments: dict[str, Any], tool_name: str = name) -> dict[str, Any]:
            # Existing #320 transport owns credentials and service routing.
            from aijurisdictionagents.correlation import suppress_debug_payloads
            with suppress_debug_payloads():
                return cast(dict[str, Any], await run_read_only(
                    lambda: _call_mcp_tool(tool_name, arguments, metadata_only=True)))

        result.append(RegisteredTool(ToolDefinition(
            tool_id=name, description=_DESCRIPTIONS[name],
            input_schema_json=json.dumps(schema), required_scope="internal_public_legal_read",
            approval_required=False, read_only=True,
        ), execute, authorize, sanitize_public_result))
    return tuple(result)


class GovernedToolClient:
    """Native-capable routes use tools; other routes explicitly retain retrieval.

    The caller already performs deterministic MCP retrieval. This adapter declares
    that mode for unsupported providers instead of pretending they used tools.
    """
    def __init__(self, client: LLMClient, publish: Callable[[LoopResult], None],
                 cancelled: Callable[[], bool] = lambda: False, *, country: str = "SK") -> None:
        self.client = client
        self.publish = publish
        self.cancelled = cancelled
        self.country = country

    def complete(self, agent_name: str, system_prompt: str,
                 conversation: Sequence[Message], documents: Sequence[Document]) -> str:
        if agent_name == "ConversationHistorySummarizer":
            return cast(str, self.client.complete(agent_name, system_prompt, conversation, documents))
        native = getattr(self.client, "complete_tool_step", None)
        underlying = getattr(self.client, "client", self.client)
        if self.country != "SK" or not callable(getattr(underlying, "complete_tool_step", None)):
            self.publish(LoopResult("deterministic_retrieval_adapter"))
            return cast(str, self.client.complete(agent_name, system_prompt, conversation, documents))
        if not callable(native):
            raise RuntimeError("native_adapter_unavailable")
        context = legacy_turn_context(system_prompt, conversation, documents)
        from app.chat.mcp_law_context import _should_use_mcp_law_context
        from app.chat.mcp_status_context import _should_use_mcp_status_context
        query = conversation[-1].content if conversation else ""
        legal_lookup = _should_use_mcp_law_context(query=query, country=self.country, language="sk")
        status_lookup = _should_use_mcp_status_context(query=query, country=self.country, language="sk")
        require_grounding = legal_lookup or status_lookup
        initial_tool = "searchLaws" if legal_lookup else "getVersion" if status_lookup else None

        async def infer(history: Any, definitions: Any, remaining: float) -> Any:
            return await run_read_only(lambda: native(context, history, definitions, remaining,
                require_tool=require_grounding and not history,
                initial_tool_id=initial_tool if not history else None))

        async def run() -> LoopResult:
            return cast(LoopResult, await run_tool_loop(context, infer, registrations(self.client),
                                                       cancelled=self.cancelled,
                                                       require_initial_tool=require_grounding))

        result = asyncio.run(run())
        self.publish(result)
        if result.reason != "completed":
            # Stable privacy-safe failure; no incomplete model answer escapes.
            raise RuntimeError(f"agent_tool_loop_{result.reason}")
        return cast(str, result.text)
