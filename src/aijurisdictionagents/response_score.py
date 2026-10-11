"""Versioned, metadata-only assessment arithmetic; missing evidence never scores."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Annotated, Literal, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .correlation import record_debug_event

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,199}$")]
Dimension = Literal["grounding", "factual_consistency", "request_coverage", "clarity"]
Gate = Literal["input_security", "output_security", "privacy_consent", "grounding"]
WEIGHTS = {"grounding": 40, "factual_consistency": 30, "request_coverage": 20, "clarity": 10}
GATES = ("input_security", "output_security", "privacy_consent", "grounding")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    answer_revision: Identifier
    evaluator_id: Identifier
    evaluator_version: Identifier
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    source_versions: tuple[Identifier, ...] = Field(default=(), max_length=64)
    model_estimated: bool = False


class DimensionAssessment(Evidence):
    dimension: Dimension
    value: Decimal = Field(ge=0, le=100, allow_inf_nan=False)


class GateAssessment(Evidence):
    gate: Gate
    outcome: Literal["passed", "failed", "blocked", "error", "not_run", "unsupported"]


class ResponseAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    assessment_id: Identifier
    answer_revision: Identifier
    created_at: datetime
    policy_id: Identifier = "response-quality"
    policy_version: Identifier = "1"
    policy_digest: Identifier
    weights: dict[Dimension, int]
    review_threshold: int = 85
    method: Literal["decimal_weighted_sum_half_up"] = "decimal_weighted_sum_half_up"
    scale: Literal[100] = 100
    status: Literal["incomplete", "blocked", "scored"]
    score: Decimal | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    requires_human_review: bool = True
    missing_evidence: tuple[Identifier, ...] = ()
    dimensions: tuple[DimensionAssessment, ...] = ()
    gates: tuple[GateAssessment, ...] = ()

    @model_validator(mode="after")
    def consistent_status(self) -> ResponseAssessment:
        if (self.status == "scored") != (self.score is not None):
            raise ValueError("Assessment status and numeric score disagree")
        if self.status != "scored" and not self.requires_human_review:
            raise ValueError("Incomplete or blocked assessment requires review")
        return self


def assess_response(
    answer_revision: str, *, dimensions: Sequence[DimensionAssessment] = (),
    gates: Sequence[GateAssessment] = (), existing_human_review: bool = True,
) -> ResponseAssessment:
    """Accept only explicit evidence for this exact answer; never infer assessments."""
    if len({item.dimension for item in dimensions}) != len(dimensions):
        raise ValueError("Duplicate assessment dimension")
    if len({item.gate for item in gates}) != len(gates):
        raise ValueError("Duplicate assessment gate")
    current_dimensions = {item.dimension: item for item in dimensions if item.answer_revision == answer_revision}
    current_gates = {item.gate: item for item in gates if item.answer_revision == answer_revision}
    missing = [f"dimension:{name}" for name in WEIGHTS if name not in current_dimensions]
    missing += [f"gate:{name}" for name in GATES if name not in current_gates or current_gates[name].outcome != "passed"]
    grounding = current_dimensions.get("grounding")
    grounding_gate = current_gates.get("grounding")
    if not grounding or not grounding.source_versions or not grounding_gate or not grounding_gate.source_versions:
        missing.append("grounding_source_versions")
    blocked = any(item.outcome in {"failed", "blocked"} for item in current_gates.values())
    score = None
    if not blocked and not missing:
        score = sum((current_dimensions[name].value * weight / Decimal(100) for name, weight in WEIGHTS.items()), Decimal(0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    policy = {"id": "response-quality", "version": "1", "weights": WEIGHTS, "threshold": 85, "method": "decimal_weighted_sum_half_up"}
    return ResponseAssessment(
        assessment_id=str(uuid4()), answer_revision=answer_revision, created_at=datetime.now(timezone.utc),
        policy_digest=hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest(),
        weights=dict(WEIGHTS), status="blocked" if blocked else "incomplete" if missing else "scored",
        score=score, missing_evidence=tuple(missing),
        requires_human_review=existing_human_review or score is None or score < 85,
        dimensions=tuple(current_dimensions.values()), gates=tuple(current_gates.values()),
    )


def record_response_assessment(assessment: ResponseAssessment) -> None:
    record_debug_event("response_quality", "assessment", assessment.status, assessment.model_dump(mode="json"))
