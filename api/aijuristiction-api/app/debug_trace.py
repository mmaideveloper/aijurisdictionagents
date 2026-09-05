"""Seven-day, session-scoped diagnostic event recording."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from aijurisdictionagents.correlation import CorrelationContext


_LOGGER = logging.getLogger(__name__)


def debug_event_sink(
    context: CorrelationContext,
    component: str,
    stage: str,
    status: str,
    payload: Mapping[str, Any],
) -> None:
    try:
        from app.case_workflows.service import get_case_workflow_service

        get_case_workflow_service().store.record_debug_event(
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            request_id=context.request_id,
            parent_request_id=context.parent_request_id,
            component=component,
            stage=stage,
            status=status,
            payload=dict(payload),
        )
    except Exception:
        _LOGGER.warning(
            "Optional session debug event sink unavailable correlation_id=%s request_id=%s",
            context.correlation_id,
            context.request_id,
            exc_info=True,
        )
