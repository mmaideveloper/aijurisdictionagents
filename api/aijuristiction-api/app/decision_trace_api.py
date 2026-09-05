"""Admin-only access to privacy-safe orchestration decision timelines."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.ai_model_admin_api import AdminContext, get_admin_store, require_ai_model_admin
from app.case_workflows.models import DecisionTraceListResponse
from app.case_workflows.service import CaseWorkflowApplicationService, get_case_workflow_service
from app.security import require_api_key
from aijurisdictionagents.api_db import ApiDatabaseStore


router = APIRouter(
    prefix="/v1/admin/chat-sessions",
    tags=["admin-decision-traces"],
    dependencies=[Depends(require_api_key)],
)


def require_decision_trace_admin(
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AdminContext:
    """Require a current server-side enabled admin role, not a client assertion."""

    user = store.find_user_by_id(user_id=admin.user_id) if admin.user_id else None
    if user is None or user.role != "admin" or not user.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required",
        )
    return admin


@router.get(
    "/{session_id}/decision-trace",
    response_model=DecisionTraceListResponse,
)
def get_session_decision_trace(
    session_id: str = Path(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AdminContext = Depends(require_decision_trace_admin),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> DecisionTraceListResponse:
    items, has_more = service.store.list_decision_traces(
        session_id=session_id, limit=limit, offset=offset
    )
    if not items:
        # Exact identifiers only, and no distinction between an unknown session
        # and a session with no trace records.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Decision trace not found",
        )
    return DecisionTraceListResponse(
        items=items,
        limit=limit,
        offset=offset,
        next_offset=offset + len(items) if has_more else None,
    )
