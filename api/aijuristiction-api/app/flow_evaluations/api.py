from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.ai_model_admin_api import AdminContext, require_ai_model_admin
from app.flow_evaluations.models import (
    EvaluationRunCreate,
    EvaluationRunResponse,
    EvaluationSuiteCreate,
    EvaluationSuiteResponse,
    FlowPromotionListResponse,
    FlowPromotionPreviewRequest,
    FlowPromotionPreviewResponse,
    FlowPromotionRequest,
    FlowPromotionResponse,
    FlowRollbackRequest,
    ProductionApprovalRequest,
    ProductionApprovalResponse,
)
from app.case_workflows.service import CaseWorkflowApplicationService, get_case_workflow_service
from app.flow_evaluations.service import FlowEvaluationService
from app.flow_evaluations.store import (
    EvaluationConflictError,
    EvaluationNotFoundError,
    FlowEvaluationStore,
)
from app.flow_packs.api import get_flow_pack_store
from app.flow_packs.store import (
    FlowPackAmbiguousError,
    FlowPackImmutableError,
    FlowPackNotFoundError,
    FlowPackStore,
)
from app.security import require_api_key

router = APIRouter(
    prefix="/v1/flow-evaluations",
    tags=["flow-evaluations"],
    dependencies=[Depends(require_api_key)],
)


@lru_cache(maxsize=1)
def get_flow_evaluation_store() -> FlowEvaluationStore:
    return FlowEvaluationStore.from_env()


def _service(
    flows: FlowPackStore = Depends(get_flow_pack_store),
    evaluations: FlowEvaluationStore = Depends(get_flow_evaluation_store),
) -> FlowEvaluationService:
    return FlowEvaluationService(flows, evaluations)


def _promotion_service(
    flows: FlowPackStore = Depends(get_flow_pack_store),
    evaluations: FlowEvaluationStore = Depends(get_flow_evaluation_store),
    workflows: CaseWorkflowApplicationService = Depends(get_case_workflow_service),
) -> FlowEvaluationService:
    return FlowEvaluationService(flows, evaluations, workflows)


@router.post("/suites", response_model=EvaluationSuiteResponse, status_code=status.HTTP_201_CREATED)
def create_suite(
    payload: EvaluationSuiteCreate,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: FlowEvaluationStore = Depends(get_flow_evaluation_store),
) -> EvaluationSuiteResponse:
    try:
        return store.create_suite(payload, actor_id=admin.user_id)
    except EvaluationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/suites/{suite_id}", response_model=EvaluationSuiteResponse)
def get_suite(
    suite_id: str,
    _: AdminContext = Depends(require_ai_model_admin),
    store: FlowEvaluationStore = Depends(get_flow_evaluation_store),
) -> EvaluationSuiteResponse:
    try:
        return store.get_suite(suite_id)
    except EvaluationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runs", response_model=EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: EvaluationRunCreate,
    admin: AdminContext = Depends(require_ai_model_admin),
    service: FlowEvaluationService = Depends(_service),
) -> EvaluationRunResponse:
    try:
        return service.evaluate(payload, actor_id=admin.user_id)
    except (FlowPackNotFoundError, EvaluationNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FlowPackAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (FlowPackImmutableError, EvaluationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=EvaluationRunResponse)
def get_run(
    run_id: str,
    _: AdminContext = Depends(require_ai_model_admin),
    store: FlowEvaluationStore = Depends(get_flow_evaluation_store),
) -> EvaluationRunResponse:
    try:
        return store.get_run(run_id)
    except EvaluationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/flows/{flow_key}/versions/{version}/production-approval",
    response_model=ProductionApprovalResponse,
)
def approve_flow_for_production(
    flow_key: str,
    version: int,
    payload: ProductionApprovalRequest,
    admin: AdminContext = Depends(require_ai_model_admin),
    jurisdiction: str = Query(min_length=2, max_length=8),
    service: FlowEvaluationService = Depends(_service),
) -> ProductionApprovalResponse:
    try:
        return service.approve(
            flow_key=flow_key, version=version, jurisdiction=jurisdiction,
            run_id=payload.run_id, actor_id=admin.user_id, reason=payload.reason,
        )
    except (FlowPackNotFoundError, EvaluationNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (FlowPackImmutableError, EvaluationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/promotions/preview", response_model=FlowPromotionPreviewResponse)
def preview_flow_promotion(
    payload: FlowPromotionPreviewRequest,
    _: AdminContext = Depends(require_ai_model_admin),
    service: FlowEvaluationService = Depends(_promotion_service),
) -> FlowPromotionPreviewResponse:
    try:
        return service.preview_promotion(payload)
    except FlowPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/promotions",
    response_model=FlowPromotionResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_flow(
    payload: FlowPromotionRequest,
    admin: AdminContext = Depends(require_ai_model_admin),
    service: FlowEvaluationService = Depends(_promotion_service),
) -> FlowPromotionResponse:
    try:
        return service.promote(payload, actor_id=admin.user_id)
    except (FlowPackNotFoundError, EvaluationNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (FlowPackImmutableError, EvaluationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/promotions", response_model=FlowPromotionListResponse)
def list_flow_promotions(
    _: AdminContext = Depends(require_ai_model_admin),
    jurisdiction: str | None = Query(default=None, min_length=2, max_length=8),
    case_type_key: str | None = Query(default=None, min_length=3, max_length=200),
    store: FlowEvaluationStore = Depends(get_flow_evaluation_store),
) -> FlowPromotionListResponse:
    return FlowPromotionListResponse(
        items=store.list_promotions(
            jurisdiction=jurisdiction,
            case_type_key=case_type_key,
        )
    )


@router.delete("/promotions/expired")
def purge_expired_flow_promotions(
    _: AdminContext = Depends(require_ai_model_admin),
    store: FlowEvaluationStore = Depends(get_flow_evaluation_store),
) -> dict[str, int]:
    return {"deleted_promotions": store.purge_expired_promotions()}


@router.post(
    "/promotions/{promotion_id}/rollback",
    response_model=FlowPromotionResponse,
    status_code=status.HTTP_201_CREATED,
)
def rollback_flow_promotion(
    promotion_id: str,
    payload: FlowRollbackRequest,
    admin: AdminContext = Depends(require_ai_model_admin),
    service: FlowEvaluationService = Depends(_promotion_service),
) -> FlowPromotionResponse:
    try:
        return service.rollback(promotion_id, payload, actor_id=admin.user_id)
    except (FlowPackNotFoundError, EvaluationNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (FlowPackImmutableError, EvaluationConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/expired")
def purge_expired_evaluation_runs(
    _: AdminContext = Depends(require_ai_model_admin),
    store: FlowEvaluationStore = Depends(get_flow_evaluation_store),
) -> dict[str, int]:
    return {"deleted_runs": store.purge_expired()}
