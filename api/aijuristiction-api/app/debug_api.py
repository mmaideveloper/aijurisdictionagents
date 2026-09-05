"""Admin-only session debugging by exact correlation ID."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import Response

from app.ai_model_admin_api import AdminContext, get_admin_store
from app.case_workflows.service import CaseWorkflowApplicationService, get_case_workflow_service
from app.decision_trace_api import require_decision_trace_admin
from app.observability import AzureApplicationInsightsLogService, ObservabilityConfigurationError
from app.security import require_api_key
from aijurisdictionagents.api_db import ApiDatabaseStore


router = APIRouter(
    prefix="/v1/admin/debug",
    tags=["admin-debug"],
    dependencies=[Depends(require_api_key)],
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,199}$")


def _validated_correlation_id(value: str) -> str:
    normalized = value.strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="Invalid correlation ID")
    return normalized


def _session_payload(correlation_id: str) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    from app.chat.api import _repository

    session = _repository.get_session_by_correlation_id(correlation_id)
    if session is None:
        return None, []
    return (
        session.model_dump(mode="json"),
        [message.model_dump(mode="json") for message in _repository.list_messages(session.id)],
    )


def _application_logs(
    correlation_id: str, *, limit: int
) -> tuple[list[dict[str, object]], str]:
    try:
        result = AzureApplicationInsightsLogService.from_env().query_logs(
            minutes=7 * 24 * 60,
            limit=min(limit, 500),
            correlation_id=correlation_id,
        )
    except ObservabilityConfigurationError as exc:
        return [], str(exc)
    except Exception as exc:  # pragma: no cover - remote Azure failure
        return [], f"Application Insights query unavailable: {type(exc).__name__}"
    return [asdict(record) for record in result.records], ""


def _build_payload(
    *, correlation_id: str, service: CaseWorkflowApplicationService, limit: int = 1000
) -> dict[str, object]:
    debug_events = service.store.list_debug_events(
        correlation_id=correlation_id, limit=limit
    )
    decisions = [
        item.model_dump(mode="json")
        for item in service.store.list_decision_traces_by_correlation(
            correlation_id=correlation_id, limit=min(limit, 1000)
        )
    ]
    session, messages = _session_payload(correlation_id)
    logs, logs_warning = _application_logs(correlation_id, limit=limit)
    timeline: list[dict[str, object]] = []
    for event in debug_events:
        timeline.append({"kind": "debug", **event})
    for decision in decisions:
        timeline.append(
            {
                "kind": "decision",
                "event_id": decision["event_id"],
                "created_at": decision["created_at"],
                "correlation_id": decision["correlation_id"],
                "session_id": decision["session_id"],
                "component": "langgraph",
                "stage": decision["stage"],
                "status": decision["status"],
                "payload": decision,
            }
        )
    for index, log in enumerate(logs):
        timeline.append(
            {
                "kind": "log",
                "event_id": f"log-{index}",
                "created_at": log.get("timestamp", ""),
                "correlation_id": correlation_id,
                "session_id": session.get("id", "") if session else "",
                "component": log.get("application", "unknown"),
                "stage": log.get("source", "log"),
                "status": log.get("level", "info"),
                "payload": log,
            }
        )
    timeline.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("event_id", ""))))
    stages = [
        f"{item.get('component', 'unknown')}:{item.get('stage', 'unknown')}"
        for item in timeline
    ]
    nodes = [
        {"id": stage, "label": stage.replace(":", " → ", 1)}
        for stage in dict.fromkeys(stages)
    ]
    edges = [
        {"from": stages[index - 1], "to": stages[index]}
        for index in range(1, len(stages))
        if stages[index - 1] != stages[index]
    ]
    return {
        "correlation_id": correlation_id,
        "retention_days": 7,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session": session,
        "messages": messages,
        "timeline": timeline,
        "flow": {"nodes": nodes, "edges": edges},
        "decision_traces": decisions,
        "application_logs": logs,
        "warnings": [logs_warning] if logs_warning else [],
    }


def _audit(
    *, store: ApiDatabaseStore, admin: AdminContext, request: Request,
    action: str, correlation_id: str,
) -> None:
    store.record_ai_model_admin_audit_event(
        admin_user_id=admin.user_id,
        admin_email=admin.email,
        action=action,
        entity_type="session_debug_trace",
        entity_id=correlation_id,
        new_value_summary={"correlation_id": correlation_id, "retention_days": 7},
        reason="Administrator troubleshooting by user-provided correlation ID.",
        correlation_id=str(getattr(request.state, "correlation_id", "")),
    )


@router.get("/{correlation_id}")
def get_session_debug_trace(
    request: Request,
    correlation_id: str = Path(min_length=1, max_length=200),
    limit: int = Query(default=1000, ge=1, le=2000),
    admin: AdminContext = Depends(require_decision_trace_admin),
    admin_store: ApiDatabaseStore = Depends(get_admin_store),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> dict[str, object]:
    resolved = _validated_correlation_id(correlation_id)
    payload = _build_payload(correlation_id=resolved, service=service, limit=limit)
    if not payload["timeline"] and payload["session"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debug trace not found or expired")
    _audit(store=admin_store, admin=admin, request=request, action="view_debug_trace", correlation_id=resolved)
    return payload


@router.get("/{correlation_id}/export")
def export_session_debug_trace(
    request: Request,
    correlation_id: str = Path(min_length=1, max_length=200),
    admin: AdminContext = Depends(require_decision_trace_admin),
    admin_store: ApiDatabaseStore = Depends(get_admin_store),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> Response:
    resolved = _validated_correlation_id(correlation_id)
    payload = _build_payload(correlation_id=resolved, service=service)
    if not payload["timeline"] and payload["session"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debug trace not found or expired")
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        manifest = {
            "schema_version": 1,
            "correlation_id": resolved,
            "generated_at": payload["generated_at"],
            "retention_days": 7,
            "exclusions": [
                "credentials", "authorization headers", "environment secrets", "hidden chain-of-thought"
            ],
        }
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for name in ("session", "messages", "timeline", "flow", "decision_traces", "application_logs", "warnings"):
            bundle.writestr(f"{name}.json", json.dumps(payload[name], indent=2, ensure_ascii=False))
    _audit(store=admin_store, admin=admin, request=request, action="export_debug_trace", correlation_id=resolved)
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="debug-{resolved}.zip"'},
    )
