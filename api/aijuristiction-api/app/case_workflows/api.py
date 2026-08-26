from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.ai_model_admin_api import AdminContext, require_ai_model_admin
from app.case_workflows.models import (
    RegisteredGraphResponse,
    WorkflowAssignmentListResponse,
    WorkflowAssignmentRequest,
    WorkflowAssignmentResponse,
    WorkflowEventListResponse,
    WorkflowResumeRequest,
    WorkflowRunResponse,
    WorkflowStartRequest,
)
from app.case_workflows.service import (
    CaseWorkflowApplicationService,
    WorkflowConfigurationError,
    get_case_workflow_service,
    registered_graphs,
)
from app.case_workflows.store import (
    WorkflowAssignmentNotFoundError,
    WorkflowOwnershipError,
    WorkflowRunNotFoundError,
)
from app.security import require_api_key

router = APIRouter(
    prefix="/v1/case-workflows",
    tags=["case-workflows"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/graphs", response_model=list[RegisteredGraphResponse])
def list_registered_graphs() -> list[RegisteredGraphResponse]:
    return list(registered_graphs())


@router.get("/assignments", response_model=WorkflowAssignmentListResponse)
def list_assignments(
    case_type_key: str | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> WorkflowAssignmentListResponse:
    return WorkflowAssignmentListResponse(
        items=service.store.list_assignments(
            case_type_key=case_type_key, jurisdiction=jurisdiction
        )
    )


@router.post(
    "/assignments/validate",
    response_model=dict[str, str],
)
def validate_assignment(
    payload: WorkflowAssignmentRequest,
    _: AdminContext = Depends(require_ai_model_admin),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> dict[str, str]:
    try:
        validation_status, message = service.validate_assignment(payload)
        return {"status": validation_status, "message": message}
    except WorkflowConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/assignments",
    response_model=WorkflowAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    payload: WorkflowAssignmentRequest,
    admin: AdminContext = Depends(require_ai_model_admin),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> WorkflowAssignmentResponse:
    try:
        return service.assign(payload, actor=admin.user_id)
    except WorkflowConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/runs", response_model=WorkflowRunResponse, status_code=status.HTTP_201_CREATED)
def start_workflow(
    payload: WorkflowStartRequest,
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> WorkflowRunResponse:
    try:
        return service.start(payload)
    except WorkflowAssignmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/runs/latest", response_model=WorkflowRunResponse)
def get_latest_workflow_run(
    case_id: str = Query(min_length=1, max_length=200),
    user_id: str = Query(min_length=1, max_length=200),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> WorkflowRunResponse:
    run = service.store.get_latest_run_for_case(case_id=case_id, user_id=user_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    return run


@router.post("/runs/{workflow_run_id}/resume", response_model=WorkflowRunResponse)
def resume_workflow(
    workflow_run_id: str,
    payload: WorkflowResumeRequest,
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> WorkflowRunResponse:
    try:
        return service.resume(workflow_run_id, user_id=payload.user_id, value=payload.value)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/runs/{workflow_run_id}", response_model=WorkflowRunResponse)
def get_workflow_run(
    workflow_run_id: str,
    user_id: str = Query(min_length=1, max_length=200),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> WorkflowRunResponse:
    try:
        return service.store.get_run(workflow_run_id, user_id=user_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/runs/{workflow_run_id}/events", response_model=WorkflowEventListResponse)
def list_workflow_events(
    workflow_run_id: str,
    user_id: str = Query(min_length=1, max_length=200),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> WorkflowEventListResponse:
    try:
        return WorkflowEventListResponse(
            items=service.store.list_events(workflow_run_id, user_id=user_id)
        )
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/runs/{workflow_run_id}/artifacts/{artifact_id}/pdf")
def download_workflow_artifact_pdf(
    workflow_run_id: str,
    artifact_id: str,
    user_id: str = Query(min_length=1, max_length=200),
    service: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> Response:
    from app.chat.api import _build_professional_document_pdf

    try:
        run = service.store.get_run(workflow_run_id, user_id=user_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    artifact = next(
        (item for item in run.artifacts if str(item.get("artifact_id", "")) == artifact_id),
        None,
    )
    if artifact is None or run.status != "completed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Completed artifact not found")
    pdf = _build_professional_document_pdf(
        title="Potvrdenie o zaplatení pôžičky",
        lines=run.final_answer.splitlines(),
        country=run.jurisdiction,
        language="sk-SK",
        generated_at=run.updated_at.isoformat(),
        case_id=run.case_id,
        session_id=run.session_id,
        user_id=run.user_id,
        footer_line="AI-assisted draft – ľudská kontrola je povinná pred použitím.",
        disclaimer=(
            "Právne upozornenie",
            "Dokument bol pripravený s podporou AI a pred podpisom vyžaduje ľudskú kontrolu.",
            "Skontrolujte údaje a právne účinky.",
        ),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="payment-confirmation.pdf"'},
    )
