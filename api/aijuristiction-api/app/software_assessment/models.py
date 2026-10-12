"""Bounded contracts for preliminary, evidence-based software assessments."""
from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

CASE_TYPE_KEY = "sk.software.regulatory_assessment"
TASK_TYPE = "software_regulatory_assessment"
WARNING = "Preliminary assessment, not a compliance certificate. Legal and medical conclusions require expert review."


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SoftwareFacts(Contract):
    description: str = Field(min_length=10, max_length=8000)
    intended_purpose: str = Field(default="", max_length=2000)
    users: str = Field(default="", max_length=1000)
    lifecycle: str = Field(default="", max_length=500)
    role: str = Field(default="", max_length=1000)
    personal_data: bool | None = None
    health_data: bool | None = None
    uses_ai: bool | None = None
    medical_purpose: bool | None = None
    specimen_analysis: bool | None = None
    automated_decisions: bool | None = None
    suppliers: str = Field(default="", max_length=2000)


class AssessmentRequest(Contract):
    request_id: UUID = Field(default_factory=uuid4)
    facts: SoftwareFacts
    document_ids: list[UUID] = Field(default_factory=list, max_length=10)
    external_acknowledged: bool = False
    selected_model_profile_id: str | None = Field(default=None, max_length=200)


class Evidence(Contract):
    evidence_id: str
    document_id: str
    filename: str
    version: int
    content_hash: str
    page: int | None = None
    section: str
    text: str = Field(max_length=12000)
    uncertainty: str = ""


class LegalSource(Contract):
    source_id: str
    title: str
    source_url: str
    provision: str
    text: str = Field(max_length=15000)
    version_id: str = ""
    effective_from: str = ""
    freshness: str = "requires_expert_verification"
    original_document_id: str = ""


class Applicability(Contract):
    regime: str = Field(max_length=150)
    status: Literal["applicable", "potentially_applicable", "not_applicable"]
    reason: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)


class Action(Contract):
    action_id: str = Field(min_length=1, max_length=100)
    finding: str = Field(min_length=1, max_length=2000)
    classification: Literal["suspected_gap", "missing_evidence"]
    evidence_id: str | None = None
    excerpt: str = Field(default="", max_length=2000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    priority: Literal["high", "medium", "low"]
    action: str = Field(min_length=1, max_length=2000)
    owner: str = Field(min_length=1, max_length=500)
    verification: str = Field(min_length=1, max_length=2000)
    status: Literal["open", "evidence_requested", "ready_for_review", "verified"] = "open"


class ChecklistItem(Contract):
    title: str = Field(min_length=1, max_length=300)
    category: Literal["legal", "contractual", "recommended"]
    purpose: str = Field(min_length=1, max_length=1500)
    owner: str = Field(min_length=1, max_length=300)
    acceptance_criteria: str = Field(min_length=1, max_length=1500)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    status: Literal["missing", "received", "reviewed"] = "missing"


class Verification(Contract):
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["test", "document_review", "clinical_performance_evidence"]
    action_ids: list[str] = Field(default_factory=list, max_length=20)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    method: str = Field(min_length=1, max_length=2000)
    acceptance_criteria: str = Field(min_length=1, max_length=2000)
    reviewer: str = Field(min_length=1, max_length=300)


class AssessmentOutput(Contract):
    summary: str = Field(max_length=3000)
    questions: list[str] = Field(default_factory=list, max_length=15)
    applicability: list[Applicability] = Field(default_factory=list, max_length=30)
    actions: list[Action] = Field(default_factory=list, max_length=60)
    supplier_checklist: list[ChecklistItem] = Field(default_factory=list, max_length=40)
    verification_plan: list[Verification] = Field(default_factory=list, max_length=60)
    recommended_documents: list[str] = Field(default_factory=list, max_length=30)
    architecture_recommendations: list[str] = Field(default_factory=list, max_length=20)
    responsibilities: list[str] = Field(default_factory=list, max_length=20)
    release_blockers: list[str] = Field(default_factory=list, max_length=30)


class ActionDecision(Contract):
    expected_revision: int = Field(ge=1)
    status: Literal["open", "evidence_requested", "ready_for_review", "verified"]
    evidence_note: str = Field(min_length=10, max_length=2000)


class DraftRequest(Contract):
    expected_revision: int = Field(ge=1)
    document_title: str = Field(min_length=3, max_length=300)
    external_acknowledged: bool = False


class DraftEdit(Contract):
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=12000)


class SupplierDecision(Contract):
    expected_revision: int = Field(ge=1)
    status: Literal["missing", "received", "reviewed"]
    evidence_note: str = Field(min_length=10, max_length=2000)
