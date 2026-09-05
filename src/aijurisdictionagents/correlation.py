"""Request/session correlation shared across API, orchestration, models and tools."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4


DebugEventSink = Callable[["CorrelationContext", str, str, str, Mapping[str, Any]], None]


@dataclass(frozen=True)
class CorrelationContext:
    correlation_id: str = ""
    session_id: str = ""
    request_id: str = ""
    parent_request_id: str = ""


_CONTEXT: ContextVar[CorrelationContext] = ContextVar(
    "aijurisdiction_correlation_context", default=CorrelationContext()
)
_DEBUG_SINK: ContextVar[DebugEventSink | None] = ContextVar(
    "aijurisdiction_debug_event_sink", default=None
)


def current_correlation_context() -> CorrelationContext:
    return _CONTEXT.get()


def new_request_id() -> str:
    return str(uuid4())


def correlation_headers() -> dict[str, str]:
    """Return propagation headers for the currently active operation."""

    context = current_correlation_context()
    headers: dict[str, str] = {}
    if context.correlation_id:
        headers["x-correlation-id"] = context.correlation_id
    if context.request_id:
        headers["x-request-id"] = context.request_id
    if context.parent_request_id:
        headers["x-parent-request-id"] = context.parent_request_id
    return headers


@contextmanager
def correlation_scope(
    *,
    correlation_id: str,
    session_id: str = "",
    request_id: str | None = None,
    parent_request_id: str = "",
    debug_sink: DebugEventSink | None = None,
) -> Iterator[CorrelationContext]:
    context = CorrelationContext(
        correlation_id=correlation_id.strip(),
        session_id=session_id.strip(),
        request_id=(request_id or new_request_id()).strip(),
        parent_request_id=parent_request_id.strip(),
    )
    context_token = _CONTEXT.set(context)
    sink_token = _DEBUG_SINK.set(debug_sink if debug_sink is not None else _DEBUG_SINK.get())
    try:
        yield context
    finally:
        _DEBUG_SINK.reset(sink_token)
        _CONTEXT.reset(context_token)


@contextmanager
def child_operation(*, request_id: str | None = None) -> Iterator[CorrelationContext]:
    parent = current_correlation_context()
    with correlation_scope(
        correlation_id=parent.correlation_id,
        session_id=parent.session_id,
        request_id=request_id,
        parent_request_id=parent.request_id,
    ) as context:
        yield context


def record_debug_event(
    component: str,
    stage: str,
    status: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    context = current_correlation_context()
    sink = _DEBUG_SINK.get()
    if sink is None or not context.correlation_id:
        return
    sink(context, component, stage, status, payload or {})
