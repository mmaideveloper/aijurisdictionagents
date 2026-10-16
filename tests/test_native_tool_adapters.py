"""Native SDK wire contract, including continuation and privacy-safe auditing."""
from types import SimpleNamespace

import pytest

from aijurisdictionagents.correlation import correlation_scope
from aijurisdictionagents.llm.native_tools import complete_native_step
from aijurisdictionagents.llm.turn_context import legacy_turn_context
from aijurisdictionagents.llm.turn_contracts import ToolDefinition
from aijurisdictionagents.schemas import Message


@pytest.mark.parametrize("provider", ["azurefoundry", "openai"])
@pytest.mark.parametrize("initial_tool", [None, "getVersion"])
def test_native_sdk_tools_and_results_continue_with_bounded_transport(provider, initial_tool):
    observed = {}
    audit = []

    def create(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            model_dump=lambda **kw: {"tool_calls": [{"id": "c1", "function": {
                "name": "getVersion", "arguments": "{}"}}]}))], model="synthetic-model")

    def options(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    adapter = SimpleNamespace(_config=SimpleNamespace(
        deployment="synthetic-deployment", model="synthetic-model", temperature=0,
        provider_label=provider, model_parameters={}, max_tokens=64 if provider == "openai" else None),
        _client=SimpleNamespace(with_options=options))
    context = legacy_turn_context("private policy", [Message(role="user", agent_name="User",
                                                              content="private request")], [])
    tool = ToolDefinition(tool_id="getVersion", description="Version", required_scope="read",
                          input_schema_json='{"type":"object","additionalProperties":false}')
    continuation = [{"role": "tool", "tool_call_id": "prior", "content": "untrusted"}]
    with correlation_scope(correlation_id="synthetic-661", debug_sink=lambda *args: audit.append(args[-1])):
        step = complete_native_step(adapter, context, continuation, [tool], 2,
                                    initial_tool_id=initial_tool)
    assert step.calls[0].tool_id == "getVersion"
    assert observed["timeout"] == 2 and observed["max_retries"] == 0
    if provider == "openai":
        assert observed["max_tokens"] == 64
    assert observed["messages"][-1] == continuation[-1]
    assert observed["tools"][0]["function"]["name"] == "getVersion"
    assert observed["tool_choice"] == ({"type": "function", "function": {"name": "getVersion"}}
                                       if initial_tool else "auto")
    assert observed["extra_headers"]["x-correlation-id"] == "synthetic-661"
    assert "private request" not in str(audit)
    assert audit[0]["effective_messages"] == []
