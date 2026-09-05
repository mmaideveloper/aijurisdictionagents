"""Privacy-safe, versioned orchestration decision traces.

The contract deliberately records bounded decision provenance, never narrative
reasoning, prompts, messages, documents, facts, or tool payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Literal, Mapping, Protocol, Sequence


TRACE_SCHEMA_VERSION = 1
MAX_CANDIDATES = 20
MAX_EVIDENCE = 50
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,254}$")

DecisionActor = Literal["system", "model", "orchestrator"]
TraceStatus = Literal[
    "running",
    "completed",
    "passed",
    "failed",
    "blocked",
    "cancelled",
    "timed_out",
    "human_review_required",
    "waiting_for_user",
]


class DecisionTraceValidationError(ValueError):
    """Raised when a candidate trace cannot pass the privacy allowlist."""


def _identifier(value: str, field_name: str, *, required: bool = True) -> str:
    normalized = value.strip()
    if not normalized:
        if required:
            raise DecisionTraceValidationError(f"{field_name} is required")
        return ""
    if not _SAFE_IDENTIFIER.fullmatch(normalized):
        raise DecisionTraceValidationError(f"{field_name} is not a bounded identifier")
    return normalized


def _timestamp(value: str) -> str:
    if len(value) > 64:
        raise DecisionTraceValidationError("created_at is not a bounded timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DecisionTraceValidationError("created_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DecisionTraceValidationError("created_at must include a timezone")
    return value


def _reject_unknown(
    value: Mapping[str, Any], allowed: set[str], object_name: str
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise DecisionTraceValidationError(
            f"non-contract {object_name} fields rejected: {', '.join(sorted(unknown))}"
        )


@dataclass(frozen=True)
class EvidenceReference:
    evidence_type: str
    reference_id: str
    content_hash: str = ""
    version: str = ""
    verification_status: str = "unverified"

    def safe_dict(self) -> dict[str, str]:
        return {
            "evidence_type": _identifier(self.evidence_type, "evidence_type"),
            "reference_id": _identifier(self.reference_id, "reference_id"),
            "content_hash": _identifier(self.content_hash, "content_hash", required=False),
            "version": _identifier(self.version, "version", required=False),
            "verification_status": _identifier(
                self.verification_status, "verification_status"
            ),
        }


@dataclass(frozen=True)
class TracePrivacyMetadata:
    data_classification: str = "confidential_metadata"
    redaction_policy: str = "decision-trace-allowlist"
    redaction_policy_version: str = "1"
    retention_class: str = "owning_session"
    user_export_allowed: bool = False
    operator_telemetry_allowed: bool = True
    evaluation_artifact_allowed: bool = False

    def safe_dict(self) -> dict[str, str | bool]:
        return {
            "data_classification": _identifier(
                self.data_classification, "data_classification"
            ),
            "redaction_policy": _identifier(self.redaction_policy, "redaction_policy"),
            "redaction_policy_version": _identifier(
                self.redaction_policy_version, "redaction_policy_version"
            ),
            "retention_class": _identifier(self.retention_class, "retention_class"),
            "user_export_allowed": self.user_export_allowed,
            "operator_telemetry_allowed": self.operator_telemetry_allowed,
            "evaluation_artifact_allowed": self.evaluation_artifact_allowed,
        }


@dataclass(frozen=True)
class DecisionRecord:
    decision_type: str
    policy_id: str
    policy_version: str
    selected_outcome: str
    reason_code: str
    candidate_ids: tuple[str, ...] = ()
    field_ids: tuple[str, ...] = ()
    metrics: tuple[tuple[str, int], ...] = ()
    confidence_band: str = "unknown"
    calibrated_score: float | None = None
    fallback: bool = False
    escalation: bool = False
    human_review_required: bool = False

    def safe_dict(self) -> dict[str, object]:
        if len(self.candidate_ids) > MAX_CANDIDATES:
            raise DecisionTraceValidationError("candidate_ids exceeds the allowlisted maximum")
        if len(self.field_ids) > MAX_CANDIDATES:
            raise DecisionTraceValidationError("field_ids exceeds the allowlisted maximum")
        if len(self.metrics) > MAX_CANDIDATES:
            raise DecisionTraceValidationError("metrics exceeds the allowlisted maximum")
        score = self.calibrated_score
        if score is not None and not 0.0 <= score <= 1.0:
            raise DecisionTraceValidationError("calibrated_score must be between 0 and 1")
        return {
            "decision_type": _identifier(self.decision_type, "decision_type"),
            "policy_id": _identifier(self.policy_id, "policy_id"),
            "policy_version": _identifier(self.policy_version, "policy_version"),
            "candidate_ids": [
                _identifier(value, "candidate_id") for value in self.candidate_ids
            ],
            "field_ids": [_identifier(value, "field_id") for value in self.field_ids],
            "metrics": {
                _identifier(key, "metric_name"): int(value)
                for key, value in self.metrics
                if 0 <= int(value) <= 1_000_000
            },
            "selected_outcome": _identifier(
                self.selected_outcome, "selected_outcome"
            ),
            "reason_code": _identifier(self.reason_code, "reason_code"),
            "confidence_band": _identifier(self.confidence_band, "confidence_band"),
            "calibrated_score": score,
            "fallback": self.fallback,
            "escalation": self.escalation,
            "human_review_required": self.human_review_required,
        }


@dataclass(frozen=True)
class OrchestrationTraceEnvelope:
    event_id: str
    session_id: str
    correlation_id: str
    stage: str
    actor: DecisionActor
    event_type: str
    status: TraceStatus
    decision: DecisionRecord
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    workflow_run_id: str = ""
    case_id: str = ""
    turn_id: str = ""
    question_id: str = ""
    answer_id: str = ""
    orchestrator_version: str = ""
    graph_version: str = ""
    flow_version: str = ""
    provider_id: str = ""
    model_id: str = ""
    model_audit_id: str = ""
    execution_event_id: str = ""
    evidence: tuple[EvidenceReference, ...] = ()
    privacy: TracePrivacyMetadata = field(default_factory=TracePrivacyMetadata)
    schema_version: int = TRACE_SCHEMA_VERSION

    def safe_dict(self) -> dict[str, object]:
        if self.schema_version != TRACE_SCHEMA_VERSION:
            raise DecisionTraceValidationError("unsupported decision trace schema version")
        if self.actor not in {"system", "model", "orchestrator"}:
            raise DecisionTraceValidationError("actor is not allowlisted")
        if self.status not in {
            "running", "completed", "passed", "failed", "blocked", "cancelled",
            "timed_out", "human_review_required", "waiting_for_user",
        }:
            raise DecisionTraceValidationError("status is not allowlisted")
        if len(self.evidence) > MAX_EVIDENCE:
            raise DecisionTraceValidationError("evidence exceeds the allowlisted maximum")
        return {
            "schema_version": self.schema_version,
            "event_id": _identifier(self.event_id, "event_id"),
            "created_at": _timestamp(self.created_at),
            "session_id": _identifier(self.session_id, "session_id"),
            "correlation_id": _identifier(self.correlation_id, "correlation_id"),
            "workflow_run_id": _identifier(
                self.workflow_run_id, "workflow_run_id", required=False
            ),
            "case_id": _identifier(self.case_id, "case_id", required=False),
            "turn_id": _identifier(self.turn_id, "turn_id", required=False),
            "question_id": _identifier(self.question_id, "question_id", required=False),
            "answer_id": _identifier(self.answer_id, "answer_id", required=False),
            "orchestrator_version": _identifier(
                self.orchestrator_version, "orchestrator_version", required=False
            ),
            "graph_version": _identifier(
                self.graph_version, "graph_version", required=False
            ),
            "flow_version": _identifier(
                self.flow_version, "flow_version", required=False
            ),
            "stage": _identifier(self.stage, "stage"),
            "actor": self.actor,
            "event_type": _identifier(self.event_type, "event_type"),
            "status": _identifier(self.status, "status"),
            "decision": self.decision.safe_dict(),
            "evidence": [item.safe_dict() for item in self.evidence],
            "privacy": self.privacy.safe_dict(),
            "provider_id": _identifier(
                self.provider_id, "provider_id", required=False
            ),
            "model_id": _identifier(self.model_id, "model_id", required=False),
            "model_audit_id": _identifier(
                self.model_audit_id, "model_audit_id", required=False
            ),
            "execution_event_id": _identifier(
                self.execution_event_id, "execution_event_id", required=False
            ),
        }


@dataclass(frozen=True)
class OpaqueDecisionTrace:
    """Readable migration marker for an unsupported historic trace version."""

    schema_version: int
    event_id: str
    session_id: str
    event_type: str


class DecisionTraceSink(Protocol):
    def record_decision(self, trace: OrchestrationTraceEnvelope) -> None: ...


class RequiredDecisionTraceSinkError(RuntimeError):
    """A mandatory legal-risk audit sink could not record a valid decision."""


@dataclass(frozen=True)
class DecisionTraceSinkBinding:
    sink: DecisionTraceSink
    required: bool = False


class CompositeDecisionTraceSink:
    """Fan out safely: optional sinks degrade, mandatory audit sinks fail closed."""

    def __init__(self, bindings: Sequence[DecisionTraceSinkBinding]) -> None:
        self._bindings = tuple(bindings)

    def record_decision(self, trace: OrchestrationTraceEnvelope) -> None:
        serialize_decision_trace(trace)
        for binding in self._bindings:
            try:
                binding.sink.record_decision(trace)
            except Exception as exc:
                if binding.required:
                    raise RequiredDecisionTraceSinkError(
                        "mandatory decision trace sink failed"
                    ) from exc


def serialize_decision_trace(trace: OrchestrationTraceEnvelope) -> dict[str, object]:
    """Apply the single allowlist used before local, durable, and telemetry sinks."""

    return trace.safe_dict()


def decision_trace_telemetry_attributes(
    trace: OrchestrationTraceEnvelope,
) -> dict[str, str | int]:
    """Return low-cardinality OpenTelemetry attributes with no subject identifiers."""

    payload = serialize_decision_trace(trace)
    decision = payload["decision"]
    if not isinstance(decision, dict):
        raise DecisionTraceValidationError("serialized decision is invalid")
    return {
        "decision_trace.schema_version": trace.schema_version,
        "decision_trace.stage": str(payload["stage"]),
        "decision_trace.actor": str(payload["actor"]),
        "decision_trace.event_type": str(payload["event_type"]),
        "decision_trace.status": str(payload["status"]),
        "decision_trace.decision_type": str(decision["decision_type"]),
        "decision_trace.reason_code": str(decision["reason_code"]),
    }


def read_decision_trace(payload: Mapping[str, Any]) -> OrchestrationTraceEnvelope | OpaqueDecisionTrace:
    """Read v1 records and retain bounded metadata for unknown historic versions."""

    version = int(payload.get("schema_version", 0))
    if version != TRACE_SCHEMA_VERSION:
        return OpaqueDecisionTrace(
            schema_version=version,
            event_id=_identifier(str(payload.get("event_id", "unknown")), "event_id"),
            session_id=_identifier(str(payload.get("session_id", "unknown")), "session_id"),
            event_type=_identifier(str(payload.get("event_type", "unknown")), "event_type"),
        )
    decision = payload.get("decision", {})
    privacy = payload.get("privacy", {})
    evidence = payload.get("evidence", [])
    if not isinstance(decision, Mapping) or not isinstance(privacy, Mapping):
        raise DecisionTraceValidationError("decision and privacy objects are required")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise DecisionTraceValidationError("evidence must be a list")
    _reject_unknown(
        payload, set(OrchestrationTraceEnvelope.__dataclass_fields__), "trace"
    )
    _reject_unknown(decision, set(DecisionRecord.__dataclass_fields__), "decision")
    _reject_unknown(privacy, set(TracePrivacyMetadata.__dataclass_fields__), "privacy")
    for item in evidence:
        if isinstance(item, Mapping):
            _reject_unknown(item, set(EvidenceReference.__dataclass_fields__), "evidence")
    trace = OrchestrationTraceEnvelope(
        schema_version=version,
        event_id=str(payload["event_id"]),
        created_at=str(payload["created_at"]),
        session_id=str(payload["session_id"]),
        correlation_id=str(payload["correlation_id"]),
        workflow_run_id=str(payload.get("workflow_run_id", "")),
        case_id=str(payload.get("case_id", "")),
        turn_id=str(payload.get("turn_id", "")),
        question_id=str(payload.get("question_id", "")),
        answer_id=str(payload.get("answer_id", "")),
        orchestrator_version=str(payload.get("orchestrator_version", "")),
        graph_version=str(payload.get("graph_version", "")),
        flow_version=str(payload.get("flow_version", "")),
        stage=str(payload["stage"]),
        actor=str(payload["actor"]),  # type: ignore[arg-type]
        event_type=str(payload["event_type"]),
        status=str(payload["status"]),  # type: ignore[arg-type]
        decision=DecisionRecord(
            decision_type=str(decision["decision_type"]),
            policy_id=str(decision["policy_id"]),
            policy_version=str(decision["policy_version"]),
            candidate_ids=tuple(str(item) for item in decision.get("candidate_ids", [])),
            field_ids=tuple(str(item) for item in decision.get("field_ids", [])),
            metrics=tuple(
                (str(key), int(value))
                for key, value in dict(decision.get("metrics", {})).items()
            ),
            selected_outcome=str(decision["selected_outcome"]),
            reason_code=str(decision["reason_code"]),
            confidence_band=str(decision.get("confidence_band", "unknown")),
            calibrated_score=(
                float(decision["calibrated_score"])
                if decision.get("calibrated_score") is not None
                else None
            ),
            fallback=bool(decision.get("fallback", False)),
            escalation=bool(decision.get("escalation", False)),
            human_review_required=bool(decision.get("human_review_required", False)),
        ),
        evidence=tuple(
            EvidenceReference(
                evidence_type=str(item["evidence_type"]),
                reference_id=str(item["reference_id"]),
                content_hash=str(item.get("content_hash", "")),
                version=str(item.get("version", "")),
                verification_status=str(item.get("verification_status", "unverified")),
            )
            for item in evidence
            if isinstance(item, Mapping)
        ),
        privacy=TracePrivacyMetadata(**dict(privacy)),
        provider_id=str(payload.get("provider_id", "")),
        model_id=str(payload.get("model_id", "")),
        model_audit_id=str(payload.get("model_audit_id", "")),
        execution_event_id=str(payload.get("execution_event_id", "")),
    )
    trace.safe_dict()
    return trace


def workflow_event_to_decision_trace(
    state: Mapping[str, Any], event: Mapping[str, Any]
) -> OrchestrationTraceEnvelope:
    """Convert a loose historic workflow event into the shared safe contract."""

    event_type = str(event.get("event_type", "workflow_event"))
    details = event.get("details", {})
    safe_details = details if isinstance(details, Mapping) else {}
    decision_type, actor = _workflow_decision_class(event_type)
    selected = str(
        safe_details.get("final_status")
        or safe_details.get("decision")
        or safe_details.get("status")
        or event.get("status", "running")
    )
    reason = str(safe_details.get("reason") or event_type)
    evidence_items = [
        EvidenceReference(
            evidence_type="legal_source",
            reference_id=str(source_id),
            verification_status="verified",
        )
        for source_id in state.get("legal_source_ids", [])[:MAX_EVIDENCE]
        if _SAFE_IDENTIFIER.fullmatch(str(source_id))
    ]
    for collection, evidence_type, id_key in (
        (state.get("tool_consents", []), "tool_consent", "consent_event_id"),
        (state.get("tool_results", []), "tool_result", "execution_event_id"),
        (state.get("artifacts", []), "artifact", "artifact_id"),
    ):
        for item in collection if isinstance(collection, Sequence) else ():
            reference_id = str(item.get(id_key, "")) if isinstance(item, Mapping) else ""
            if _SAFE_IDENTIFIER.fullmatch(reference_id):
                evidence_items.append(
                    EvidenceReference(
                        evidence_type=evidence_type,
                        reference_id=reference_id,
                        verification_status="recorded",
                    )
                )
    evidence = tuple(evidence_items[:MAX_EVIDENCE])
    score = state.get("routing_confidence") if decision_type == "workflow_routing" else None
    field_ids = {
        str(item)
        for item in (*state.get("verified_facts", {}).keys(), *state.get("missing_facts", []))
        if _SAFE_IDENTIFIER.fullmatch(str(item))
    }
    provided_field = str(safe_details.get("provided_field", ""))
    if _SAFE_IDENTIFIER.fullmatch(provided_field):
        field_ids.add(provided_field)
    metrics = tuple(
        (str(key), int(value))
        for key, value in safe_details.items()
        if str(key).endswith("_count")
        and _SAFE_IDENTIFIER.fullmatch(str(key))
        and isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= 1_000_000
    )
    provenance = state.get("tool_selection", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    provider_id = str(provenance.get("provider", ""))
    model_id = str(provenance.get("model", ""))
    provider_id = provider_id if _SAFE_IDENTIFIER.fullmatch(provider_id) else ""
    model_id = model_id if _SAFE_IDENTIFIER.fullmatch(model_id) else ""
    status = str(event.get("status", "running"))
    if status not in {
        "running", "completed", "passed", "failed", "blocked", "cancelled",
        "timed_out", "human_review_required", "waiting_for_user",
    }:
        status = "completed"
    return OrchestrationTraceEnvelope(
        event_id=str(event["event_id"]),
        created_at=str(event["created_at"]),
        session_id=str(state["session_id"]),
        correlation_id=str(state["correlation_id"]),
        workflow_run_id=str(state["workflow_run_id"]),
        case_id=str(state.get("case_id", "")),
        orchestrator_version="langgraph-case-workflow",
        graph_version=str(state.get("graph_version", "")),
        flow_version=str(state.get("flow_version", "")),
        stage=str(event.get("stage", "unknown")),
        actor=actor,
        event_type=event_type,
        status=status,  # type: ignore[arg-type]
        decision=DecisionRecord(
            decision_type=decision_type,
            policy_id=str(state.get("flow_key", "case-workflow")),
            policy_version=str(state.get("flow_version", "1")),
            candidate_ids=tuple(
                str(item) for item in state.get("routing_evidence", [])[:MAX_CANDIDATES]
                if _SAFE_IDENTIFIER.fullmatch(str(item))
            ),
            field_ids=tuple(sorted(field_ids))[:MAX_CANDIDATES],
            metrics=metrics[:MAX_CANDIDATES],
            selected_outcome=selected,
            reason_code=reason,
            confidence_band=_confidence_band(score),
            calibrated_score=float(score) if isinstance(score, (int, float)) else None,
            fallback="fallback" in event_type or "retry" in event_type,
            escalation="escalat" in event_type,
            human_review_required=(
                status == "human_review_required" or "human_review" in event_type
            ),
        ),
        evidence=evidence,
        provider_id=provider_id,
        model_id=model_id,
    )


def _workflow_decision_class(event_type: str) -> tuple[str, DecisionActor]:
    if event_type in {"workflow_routed", "workflow_assignment_pinned", "langgraph_run_started"}:
        return "workflow_routing", "orchestrator"
    if "retrieval" in event_type or "requirements_retrieved" in event_type:
        return "legal_retrieval", "system"
    if "tool" in event_type or "verification_offered" in event_type:
        return "tool_execution", "orchestrator"
    if "validation" in event_type or "review" in event_type:
        return "output_verification", "system"
    if "conflict" in event_type:
        return "fact_validation", "system"
    if "interrupt" in event_type or "resume" in event_type:
        return "workflow_control", "orchestrator"
    return "final_disposition", "orchestrator"


def _confidence_band(score: object) -> str:
    if not isinstance(score, (int, float)):
        return "unknown"
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"
