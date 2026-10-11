"""Authenticated, content-free client observations of an owned stream request."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.cases_api import get_store, _ensure_case_access
from app.case_workflows.service import CaseWorkflowApplicationService, get_case_workflow_service
from app.security import require_api_key
from aijurisdictionagents.api_db import ApiDatabaseStore

router = APIRouter(prefix="/v1/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


class ClientObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,199}$")
    phase: Literal["dispatch", "headers_received", "stream_completed", "cancelled", "interrupted", "network_error"]
    elapsed_ms: int = Field(ge=0, le=86_400_000, strict=True)


@router.post("/sessions/{session_id}/client-observations", status_code=202)
def observe_client_stream(
    session_id: UUID, observation: ClientObservation,
    device_id: str = Header(default="", alias="x-jurisdigta-device-id"),
    device_token: str = Header(default="", alias="x-jurisdigta-device-token"),
    store: ApiDatabaseStore = Depends(get_store),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> dict[str, bool]:
    from app.chat.api import _repository

    user_id = str(observation.user_id)
    user = store.authenticate_user_device_auth_token(user_id=user_id, device_id=device_id, token=device_token)
    if user is None or not user.is_enabled:
        raise HTTPException(401, "Authentication required")
    session = _repository.get_session(session_id)
    if session is None or str(session.user_id) != user_id or session.created_at <= datetime.now(timezone.utc) - timedelta(days=7):
        raise HTTPException(404, "Owned session unavailable")
    if session.case_id:
        _ensure_case_access(case_id=session.case_id, user_id=user_id, store=store)
    events = service.store.list_debug_events(correlation_id=session.correlation_id, limit=2000)
    # The client cannot create an execution root or link to another session's
    # request. Its report still does not prove receipt/rendering or execution.
    target_path = f"/v1/chat/sessions/{session_id}/stream"
    if not any(event.get("request_id") == observation.request_id and event.get("component") == "api"
               and event.get("stage") == "http_request" and event.get("payload", {}).get("path") == target_path
               for event in events):
        raise HTTPException(404, "Retained stream request unavailable")
    reports = [event for event in events if event.get("component") == "frontend"]
    if any(event.get("parent_request_id") == observation.request_id and event.get("stage") == observation.phase for event in reports):
        return {"accepted": True}
    if len(reports) >= 200:
        raise HTTPException(429, "Client observation limit reached")
    service.store.record_debug_event(
        correlation_id=session.correlation_id, session_id=str(session_id), request_id=str(uuid4()),
        parent_request_id=observation.request_id, component="frontend", stage=observation.phase,
        status="client_reported", payload={"schema_version": 1, "source": "client_reported_unverified",
            "elapsed_ms": observation.elapsed_ms, "target_request_id": observation.request_id},
    )
    return {"accepted": True}
