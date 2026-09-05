from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RegisteredGraphResponse(BaseModel):
    graph_key: str
    graph_version: int
    node_names: tuple[str, ...]
    supports_interrupt_resume: bool
    supports_automated_finalization: bool


class WorkflowAssignmentRequest(BaseModel):
    case_type_key: str = Field(min_length=3, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=8)
    graph_key: str = Field(min_length=3, max_length=100)
    graph_version: int = Field(ge=1)
    flow_key: str = Field(min_length=3, max_length=200)
    flow_version: int = Field(ge=1)
    confirmation: bool = False


class WorkflowAssignmentResponse(BaseModel):
    assignment_id: str
    case_type_key: str
    jurisdiction: str
    graph_key: str
    graph_version: int
    flow_key: str
    flow_version: int
    is_active: bool
    validation_status: str
    validation_message: str
    effective_from: datetime
    effective_to: datetime | None
    created_by: str
    created_at: datetime
    supersedes_assignment_id: str | None


class WorkflowAssignmentListResponse(BaseModel):
    items: list[WorkflowAssignmentResponse]


class WorkflowStartRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    user_id: str = Field(min_length=1, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=8)
    case_type_key: str = Field(min_length=3, max_length=200)
    request_text: str = Field(min_length=1, max_length=12000)
    language: str = Field(default="sk-SK", max_length=16)
    routing_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    routing_evidence: list[str] = Field(default_factory=list, max_length=10)
    facts: dict[str, str] = Field(default_factory=dict)
    consented_checks: list[str] = Field(default_factory=list)
    external_provider_acknowledged: bool = False
    execution_deadline_at: datetime | None = None
    session_expires_at: datetime | None = None


class WorkflowResumeRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    value: str | dict[str, str]


class WorkflowControlRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)


class WorkflowRunResponse(BaseModel):
    workflow_run_id: str
    correlation_id: str
    case_id: str
    session_id: str
    user_id: str
    jurisdiction: str
    case_type_key: str
    assignment_id: str
    graph_key: str
    graph_version: int
    flow_key: str
    flow_version: int
    status: Literal[
        "running", "waiting_for_user", "completed", "human_review_required", "blocked"
    ]
    current_stage: str
    pending_action: dict[str, Any] = Field(default_factory=dict)
    final_answer: str = ""
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    review_decisions: dict[str, str] = Field(default_factory=dict)
    escalation_reason: str = ""
    termination_reason: Literal[
        "",
        "quality_approved",
        "human_review_required",
        "revision_budget_exhausted",
        "input_attempts_exhausted",
        "no_progress",
        "privacy_blocked",
        "provenance_missing",
        "user_cancelled",
        "session_expired",
        "deadline_exceeded",
        "operational_failure",
    ] = ""
    input_attempt_count: int = 0
    quality_revision_count: int = 0
    technical_retry_count: int = 0
    created_at: datetime
    updated_at: datetime


class WorkflowEventResponse(BaseModel):
    event_id: str
    workflow_run_id: str
    correlation_id: str
    event_type: str
    stage: str
    status: str
    details: dict[str, str | int | float | bool | None]
    created_at: datetime


class WorkflowEventListResponse(BaseModel):
    items: list[WorkflowEventResponse]
