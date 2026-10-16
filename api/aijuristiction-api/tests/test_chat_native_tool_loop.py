"""Contract tests for API-owned tool authorization, minimization and routing."""
import json
from types import SimpleNamespace

import pytest

from app.chat.typed_tool_loop import GovernedToolClient, registrations, sanitize_public_result
from aijurisdictionagents.llm.tool_loop import ModelStep
from aijurisdictionagents.llm.turn_contracts import ToolCall
from aijurisdictionagents.schemas import Message


def test_public_result_allowlist_and_bounds():
    raw = {"results": [{"document_id": "synthetic-661", "content_text": "x" * 10000,
                         "api_key": "secret", "raw_provider_payload": "private"}],
           "credentials": "private"}
    safe = sanitize_public_result(raw)
    assert len(safe["results"][0]["content_text"]) == 8000
    assert "private" not in json.dumps(safe) and "secret" not in json.dumps(safe)


def test_release_one_registration_uses_mcp_schemas():
    tools = registrations(SimpleNamespace(authorize_internal_tool=lambda: True))
    assert {tool.definition.tool_id for tool in tools} == {
        "searchLaws", "getLawText", "getVersion", "getStatistics"}
    search = next(tool for tool in tools if tool.definition.tool_id == "searchLaws")
    schema = json.loads(search.definition.input_schema_json)
    assert schema["properties"]["country_code"]["enum"] == ["SK"]
    assert schema["properties"]["query"]["maxLength"] == 1000
    assert not registrations(SimpleNamespace())[0].authorize()


def test_native_chat_uses_same_turn_and_minimized_tool_result(monkeypatch):
    from app.chat import mcp_law_context
    seen = []
    events = []
    monkeypatch.setattr(mcp_law_context, "_call_mcp_tool", lambda *args, **kwargs: {
        "results": [{"document_id": "synthetic-661", "title": "Synthetic law"}], "token": "secret"})

    class Client:
        def authorize_internal_tool(self):
            return True

        def complete_tool_step(self, context, history, definitions, remaining, **kwargs):
            seen.append(list(history))
            if not history:
                return ModelStep(calls=(ToolCall(call_id="c1", tool_id="searchLaws",
                                                 arguments_json='{"query":"synthetic law"}'),))
            assert "secret" not in json.dumps(history)
            assert history[-1]["role"] == "tool"
            return ModelStep("Synthetic law [synthetic-661]. Human review required.")

    reply = GovernedToolClient(Client(), events.append).complete("Lawyer", "policy", [
        Message(role="user", agent_name="User", content="Explain synthetic law")], [])
    assert "synthetic-661" in reply
    assert len(seen) == 2 and events[0].reason == "completed"
    assert events[0].evidence[0]["data"]["results"][0]["document_id"] == "synthetic-661"


def test_unsupported_model_declares_deterministic_adapter():
    events = []
    client = SimpleNamespace(complete=lambda *args: "pre-retrieved answer")
    assert GovernedToolClient(client, events.append).complete("lawyer", "policy", [], []) == "pre-retrieved answer"
    assert events[0].reason == "deterministic_retrieval_adapter"


def test_failure_does_not_publish_partial_answer():
    client = SimpleNamespace(complete_tool_step=lambda *args, **kwargs: ModelStep("partial", calls=(
        ToolCall(call_id="c", tool_id="shell", arguments_json="{}"),)))
    events = []
    with pytest.raises(RuntimeError, match="agent_tool_loop_unsupported_tool"):
        GovernedToolClient(client, events.append).complete("lawyer", "policy", [], [])
    assert events[0].text == ""


def test_status_sanitization_keeps_versions_and_excludes_court_data():
    assert sanitize_public_result({"api_version": "synthetic", "processed_laws": 1,
                                   "court_decisions": {"text": "private"}}) == {
                                       "api_version": "synthetic", "processed_laws": 1}


def test_live_model_consent_cannot_be_bypassed_by_native_method():
    from aijurisdictionagents.privacy import PrivacyCheckedClient
    calls = []

    def deny(*args):
        raise PermissionError("consent_revoked")

    controls = SimpleNamespace(require_processing=deny)
    underlying = SimpleNamespace(complete_tool_step=lambda *args, **kwargs: calls.append("called"))
    client = PrivacyCheckedClient(underlying, controls, "synthetic-user", True)
    with pytest.raises(PermissionError):
        client.complete_tool_step(None, [], [], 1)
    assert calls == []
