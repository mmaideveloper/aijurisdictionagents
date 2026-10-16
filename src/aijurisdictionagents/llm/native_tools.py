"""OpenAI-compatible native tools shared by Azure Foundry and OpenAI adapters."""
from __future__ import annotations

import json
from typing import Any, Sequence

from .context_boundary import build_turn_provider_messages
from .base import execute_correlated_model_call, private_model_io
from .tool_loop import ModelStep, decode_native_message, native_schemas
from .turn_contracts import AgentTurnContext, ToolDefinition
from ..correlation import correlation_headers


def complete_native_step(
    client: Any, context: AgentTurnContext, history: Sequence[dict[str, Any]],
    definitions: Sequence[ToolDefinition], remaining_seconds: float,
    *, require_tool: bool = False,
    initial_tool_id: str | None = None,
) -> ModelStep:
    messages: list[dict[str, Any]] = list(build_turn_provider_messages(
        context.model_copy(update={"tools": ()}), external_provider=True))
    messages.extend(history)
    schemas = native_schemas(definitions)
    # Include native schemas, framing and the entire tool transcript in the budget.
    encoded = json.dumps({"messages": messages, "tools": schemas}, ensure_ascii=True)
    if (len(encoded) > context.budget.max_characters
            or len(encoded.encode()) > context.budget.max_tokens - context.budget.reserved_output_tokens):
        raise ValueError("context_budget_exceeded")
    config = client._config
    kwargs: dict[str, Any] = dict(config.model_parameters)
    kwargs.update(model=getattr(config, "deployment", None) or config.model,
                  messages=messages, tools=schemas,
                  tool_choice="required" if require_tool else "auto", parallel_tool_calls=False)
    if initial_tool_id is not None:
        if initial_tool_id not in {tool.tool_id for tool in definitions}:
            raise ValueError("unsupported_initial_tool")
        kwargs["tool_choice"] = {"type": "function", "function": {"name": initial_tool_id}}
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if getattr(config, "max_tokens", None) is not None:
        kwargs.setdefault("max_tokens", config.max_tokens)
    # No SDK retry may outlive the turn deadline.
    with private_model_io():
        response = execute_correlated_model_call(
            provider=getattr(config, "provider_label", "azurefoundry"),
            model=kwargs["model"], agent_name="GovernedToolAgent",
            request_payload=messages,
            route_snapshot=getattr(client, "_audit_route_provenance", None),
            invoke=lambda: client._client.with_options(
                timeout=remaining_seconds, max_retries=0).chat.completions.create(
                    **kwargs, extra_headers=correlation_headers()),
        )
    if not response.choices:
        raise ValueError("empty_model_response")
    return decode_native_message(response.choices[0].message.model_dump(exclude_none=True))
