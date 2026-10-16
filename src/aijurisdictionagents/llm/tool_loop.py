"""Bounded native tool execution. Only server-owned registrations confer authority."""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
from contextvars import copy_context
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
import json
import logging
import time
from threading import Thread
from typing import Any, Literal

from jsonschema import Draft202012Validator, SchemaError

from .turn_contracts import AgentTurnContext, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)
RELEASE_ONE_TOOLS = frozenset({"searchLaws", "getLawText", "getVersion", "getStatistics"})
TerminalReason = Literal[
    "completed", "forbidden", "invalid_schema", "invalid_arguments", "unsupported_tool",
    "duplicate_call", "call_limit", "iteration_limit", "deadline", "cancelled",
    "result_limit", "context_limit", "unavailable", "tool_error", "empty_answer",
    "tool_required", "deterministic_retrieval_adapter",
]


async def run_read_only(operation: Callable[[], Any]) -> Any:
    """Bound the caller's wait without joining an uncancellable transport thread.

    Only read-only work is permitted. A request already accepted by the upstream
    may complete, but its late result cannot resume a cancelled loop.
    """
    future: Future[Any] = Future()

    def worker() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(operation())
        except BaseException as exc:
            future.set_exception(exc)

    context = copy_context()
    Thread(target=lambda: context.run(worker), daemon=True, name="readonly-agent-tool").start()
    return await asyncio.wrap_future(future)


@dataclass(frozen=True)
class ModelStep:
    text: str = ""
    calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    execute: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    # Re-evaluated immediately before execution, including live privacy controls.
    authorize: Callable[[], bool]
    sanitize: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class LoopLimits:
    iterations: int = 4
    calls: int = 6
    seconds: float = 45.0
    result_bytes: int = 24000

    def __post_init__(self) -> None:
        if not (1 <= self.iterations <= 10 and 1 <= self.calls <= 20
                and 0 < self.seconds <= 120 and 256 <= self.result_bytes <= 64000):
            raise ValueError("invalid_loop_limits")


@dataclass(frozen=True)
class LoopResult:
    reason: TerminalReason
    text: str = ""
    calls: int = 0
    # Sanitized evidence is turn-scoped, never operational log data.
    evidence: tuple[dict[str, Any], ...] = field(default=(), repr=False)


async def run_tool_loop(
    context: AgentTurnContext,
    infer: Callable[[Sequence[dict[str, Any]], Sequence[ToolDefinition], float], Awaitable[ModelStep]],
    tools: Sequence[RegisteredTool],
    *,
    limits: LoopLimits = LoopLimits(),
    cancelled: Callable[[], bool] = lambda: False,
    require_initial_tool: bool = False,
) -> LoopResult:
    """One invocation is one idempotency scope; repeats fail before re-execution.

    Stop cancels pending awaits. Transport adapters must also enforce the supplied
    remaining deadline; read-only transports may finish an already sent request.
    No partial model answer is published on a failed turn.
    """
    deadline = time.monotonic() + limits.seconds
    history: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    seen_calls: set[str] = set()
    seen_ids: set[str] = set()
    count = 0

    def finish(reason: TerminalReason, text: str = "") -> LoopResult:
        logger.info("agent_tool_loop reason=%s calls=%d", reason, count)
        return LoopResult(reason, text, count, tuple(evidence))

    async def bounded(operation: Awaitable[Any]) -> Any:
        task = asyncio.ensure_future(operation)
        try:
            while True:
                if cancelled():
                    raise asyncio.CancelledError
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                done, _ = await asyncio.wait({task}, timeout=min(remaining, 0.05))
                if done:
                    result = task.result()
                    if cancelled():
                        raise asyncio.CancelledError
                    if time.monotonic() >= deadline:
                        raise TimeoutError
                    return result
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    try:
        if context.governance.processing_restricted:
            return finish("forbidden")
        registry = {tool.definition.tool_id: tool for tool in tools}
        if len(registry) != len(tools):
            return finish("invalid_schema")
        definitions = tuple(tool.definition for tool in tools)
        for tool in tools:
            definition = tool.definition
            if (definition.tool_id not in RELEASE_ONE_TOOLS or not definition.read_only
                    or definition.approval_required):
                return finish("forbidden")
            schema = json.loads(definition.input_schema_json)
            Draft202012Validator.check_schema(schema)
            if schema.get("additionalProperties") is not False or "$ref" in json.dumps(schema):
                return finish("invalid_schema")
        for _ in range(limits.iterations):
            if cancelled():
                return finish("cancelled")
            step = await bounded(infer(history, definitions, max(0.001, deadline - time.monotonic())))
            if not step.calls:
                if require_initial_tool and count == 0:
                    return finish("tool_required")
                if not step.text.strip():
                    return finish("empty_answer")
                return finish("completed", step.text)
            if count + len(step.calls) > limits.calls:
                return finish("call_limit")
            # Validate the whole batch before executing its first member.
            pending = []
            for call in step.calls:
                registered = registry.get(call.tool_id)
                if registered is None:
                    return finish("unsupported_tool")
                arguments = json.loads(call.arguments_json)
                validator = Draft202012Validator(json.loads(registered.definition.input_schema_json))
                if not validator.is_valid(arguments):
                    return finish("invalid_arguments")
                fingerprint = call.tool_id + json.dumps(arguments, sort_keys=True, separators=(",", ":"))
                if call.call_id in seen_ids or fingerprint in seen_calls:
                    return finish("duplicate_call")
                seen_ids.add(call.call_id)
                seen_calls.add(fingerprint)
                pending.append((call, registered, arguments))
            history.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": call.call_id, "type": "function", "function": {
                    "name": call.tool_id, "arguments": call.arguments_json}}
                for call in step.calls
            ]})
            for call, tool, arguments in pending:
                if cancelled():
                    return finish("cancelled")
                if time.monotonic() >= deadline:
                    return finish("deadline")
                if not await bounded(run_read_only(tool.authorize)):
                    return finish("forbidden")
                count += 1
                raw = await bounded(tool.execute(arguments))
                if (not isinstance(raw, dict) or raw.get("isError") or raw.get("error")
                        or raw.get("status") in {"error", "degraded", "unavailable"}):
                    return finish("tool_error")
                safe = tool.sanitize(raw)
                encoded = json.dumps({"type": "untrusted_tool_result", "tool": call.tool_id,
                                      "data": safe}, allow_nan=False, ensure_ascii=True)
                if len(encoded.encode()) > limits.result_bytes:
                    return finish("result_limit")
                candidate = history + [{"role": "tool", "tool_call_id": call.call_id, "content": encoded}]
                # Bound the cumulative transcript, including tool-call arguments.
                if len(json.dumps(candidate).encode()) > context.budget.max_characters:
                    return finish("context_limit")
                history = candidate
                evidence.append({"tool": call.tool_id, "data": safe})
                logger.info("agent_tool_call tool=%s status=completed", call.tool_id)
        return finish("iteration_limit")
    except asyncio.CancelledError:
        return finish("cancelled")
    except SchemaError:
        return finish("invalid_schema")
    except TimeoutError:
        return finish("deadline")
    except PermissionError:
        return finish("forbidden")
    except Exception:
        # Never include exception messages, provider bodies, arguments or results.
        return finish("unavailable")


def native_schemas(definitions: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": tool.tool_id,
             "description": tool.description, "parameters": json.loads(tool.input_schema_json)}}
            for tool in definitions]


def decode_native_message(message: Mapping[str, Any]) -> ModelStep:
    calls = tuple(ToolCall(call_id=call["id"], tool_id=call["function"]["name"],
                           arguments_json=call["function"]["arguments"])
                  for call in message.get("tool_calls", ()))
    return ModelStep(text=str(message.get("content") or ""), calls=calls)
