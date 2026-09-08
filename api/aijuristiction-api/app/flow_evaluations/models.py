from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.case_workflows.models import WorkflowAssignmentResponse

EvaluationMode = Literal["routing_only", "full_graph"]


class EvaluationCaseCreate(BaseModel):
    case_key: str = Field(min_length=2, max_length=100)
    mode: EvaluationMode
    synthetic_input: dict[str, Any]
    expected_route: str = Field(min_length=2, max_length=200)
    required_source_ids: list[str] = Field(default_factory=list, max_length=100)
    human_review_required: bool = True


class EvaluationSuiteCreate(BaseModel):
    suite_key: str = Field(min_length=3, max_length=100)
    version: int = Field(ge=1)
    jurisdiction: str = Field(min_length=2, max_length=8)
    title: str = Field(min_length=3, max_length=200)
    synthetic_only: Literal[True]
    synthetic_data_confirmed: Literal[True]
    routing_accuracy_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    retention_days: int = Field(default=14, ge=1, le=30)
    cases: list[EvaluationCaseCreate] = Field(min_length=1, max_length=500)


class EvaluationSuiteResponse(BaseModel):
    suite_id: str
    suite_key: str
    version: int
    jurisdiction: str
    title: str
    synthetic_only: bool
    routing_accuracy_threshold: float
    retention_days: int
    suite_hash: str
    case_count: int
    created_by: str
    created_at: datetime


class EvaluationObservation(BaseModel):
    case_key: str
    actual_route: str = Field(min_length=1, max_length=200)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    schema_valid: bool
    provenance_valid: bool
    privacy_violation_count: int = Field(default=0, ge=0)
    unsupported_auto_finalization: bool = False
    human_review_present: bool = True


class EvaluationRunCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=200)
    synthetic_run_id: str = Field(min_length=3, max_length=200)
    suite_id: str
    flow_key: str
    flow_version: int = Field(ge=1)
    jurisdiction: str = Field(min_length=2, max_length=8)
    graph_version: str = Field(min_length=1, max_length=100)
    routing_policy: dict[str, Any]
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    provider_route: str = Field(min_length=1, max_length=200)
    mode: EvaluationMode
    observations: list[EvaluationObservation] = Field(min_length=1, max_length=500)


class EvaluationRunResponse(BaseModel):
    run_id: str
    idempotency_key: str
    synthetic_run_id: str
    suite_id: str
    suite_key: str
    suite_version: int
    suite_hash: str
    flow_id: str
    flow_key: str
    flow_version: int
    flow_definition_hash: str
    graph_version: str
    routing_policy_hash: str
    provider: str
    model: str
    provider_route: str
    mode: EvaluationMode
    status: Literal["passed", "failed"]
    metrics: dict[str, Any]
    gates: dict[str, bool]
    created_by: str
    created_at: datetime
    expires_at: datetime


class ProductionApprovalRequest(BaseModel):
    run_id: str
    reason: str = Field(min_length=5, max_length=1000)


class ProductionApprovalResponse(BaseModel):
    approval_id: str
    flow_id: str
    run_id: str
    definition_hash: str
    approved_by: str
    reason: str
    approved_at: datetime


class FlowPromotionPreviewRequest(BaseModel):
    case_type_key: str = Field(min_length=3, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=8)
    graph_key: str = Field(min_length=3, max_length=100)
    graph_version: int = Field(ge=1)
    flow_key: str = Field(min_length=3, max_length=200)
    flow_version: int = Field(ge=1)


class FlowPromotionRequest(FlowPromotionPreviewRequest):
    idempotency_key: str = Field(min_length=8, max_length=200)
    approval_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=5, max_length=1000)
    confirmation: Literal[True]
    expected_current_assignment_id: str | None = Field(default=None, max_length=200)


class FlowRollbackRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=200)
    reason: str = Field(min_length=5, max_length=1000)
    confirmation: Literal[True]
    expected_current_assignment_id: str = Field(min_length=1, max_length=200)


class PromotionApprovalSummary(BaseModel):
    approval_id: str
    run_id: str
    definition_hash: str
    approved_by: str
    approval_reason: str
    approved_at: datetime
    run_expires_at: datetime
    suite_key: str
    suite_version: int
    suite_hash: str
    graph_version: str
    routing_policy_hash: str
    provider: str
    model: str
    provider_route: str
    gates: dict[str, bool]


class FlowPromotionPreviewResponse(BaseModel):
    candidate_flow_id: str
    candidate_definition_hash: str
    candidate_lifecycle_state: str
    requested_assignment: FlowPromotionPreviewRequest
    current_assignment: WorkflowAssignmentResponse | None
    approval: PromotionApprovalSummary | None
    compatibility_status: str
    compatibility_message: str
    blockers: list[str]
    impact: str
    can_promote: bool


class FlowPromotionResponse(BaseModel):
    promotion_id: str
    idempotency_key: str
    action: Literal["promote", "rollback"]
    request_hash: str
    flow_id: str
    approval: PromotionApprovalSummary
    prior_assignment: WorkflowAssignmentResponse | None
    target_assignment: WorkflowAssignmentResponse
    target_assignment_hash: str
    promoted_by: str
    reason: str
    promoted_at: datetime
    retention_until: datetime
    rollback_of_promotion_id: str | None


class FlowPromotionListResponse(BaseModel):
    items: list[FlowPromotionResponse]
