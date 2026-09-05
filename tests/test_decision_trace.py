from __future__ import annotations

import json
from pathlib import Path

import pytest

from aijurisdictionagents.observability import TraceRecorder
from aijurisdictionagents.observability_decision_trace import (
    CompositeDecisionTraceSink,
    DecisionRecord,
    DecisionTraceSinkBinding,
    DecisionTraceValidationError,
    OpaqueDecisionTrace,
    OrchestrationTraceEnvelope,
    RequiredDecisionTraceSinkError,
    decision_trace_telemetry_attributes,
    read_decision_trace,
    serialize_decision_trace,
    workflow_event_to_decision_trace,
)
from aijurisdictionagents.schemas import Message


def _trace(**changes: object) -> OrchestrationTraceEnvelope:
    values: dict[str, object] = {
        "event_id": "event-1",
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "stage": "route",
        "actor": "orchestrator",
        "event_type": "workflow_routed",
        "status": "completed",
        "decision": DecisionRecord(
            decision_type="workflow_routing",
            policy_id="routing-policy",
            policy_version="1",
            selected_outcome="dedicated_flow",
            reason_code="high_confidence_match",
            candidate_ids=("case-type-1",),
            calibrated_score=0.91,
            confidence_band="high",
        ),
    }
    values.update(changes)
    return OrchestrationTraceEnvelope(**values)  # type: ignore[arg-type]


def test_allowlist_serializes_only_contract_fields() -> None:
    payload = serialize_decision_trace(_trace())

    assert payload["schema_version"] == 1
    assert payload["session_id"] == "session-1"
    assert payload["decision"]["reason_code"] == "high_confidence_match"  # type: ignore[index]
    serialized = json.dumps(payload)
    assert "prompt" not in serialized
    assert "chain_of_thought" not in serialized


def test_allowlist_rejects_narrative_or_secret_values() -> None:
    with pytest.raises(DecisionTraceValidationError, match="selected_outcome"):
        serialize_decision_trace(
            _trace(
                decision=DecisionRecord(
                    decision_type="workflow_routing",
                    policy_id="routing-policy",
                    policy_version="1",
                    selected_outcome="Narrative prompt with sk-secret-value",
                    reason_code="unsafe",
                )
            )
        )


def test_unknown_schema_remains_readable_as_opaque_metadata() -> None:
    historic = read_decision_trace(
        {
            "schema_version": 99,
            "event_id": "historic-event",
            "session_id": "historic-session",
            "event_type": "future-event",
            "prompt": "must not be retained",
        }
    )

    assert isinstance(historic, OpaqueDecisionTrace)
    assert historic.schema_version == 99
    assert not hasattr(historic, "prompt")


def test_optional_sink_failure_degrades_but_mandatory_sink_fails_closed() -> None:
    class BrokenSink:
        def record_decision(self, trace: OrchestrationTraceEnvelope) -> None:
            del trace
            raise OSError("synthetic outage")

    CompositeDecisionTraceSink(
        [DecisionTraceSinkBinding(BrokenSink(), required=False)]
    ).record_decision(_trace())
    with pytest.raises(RequiredDecisionTraceSinkError):
        CompositeDecisionTraceSink(
            [DecisionTraceSinkBinding(BrokenSink(), required=True)]
        ).record_decision(_trace())


def test_telemetry_attributes_are_low_cardinality_and_subject_free() -> None:
    attributes = decision_trace_telemetry_attributes(_trace())

    assert attributes["decision_trace.reason_code"] == "high_confidence_match"
    assert all("session" not in key for key in attributes)
    assert "session-1" not in json.dumps(attributes)


def test_legacy_recorder_never_writes_message_or_result_content(tmp_path: Path) -> None:
    secret = "synthetic-secret-prompt-value"
    recorder = TraceRecorder(tmp_path, session_id="session-1")
    recorder.record_message(
        Message(role="user", agent_name="User", content=secret, sources=[])
    )
    recorder.record_event(
        "result",
        {
            "final_recommendation": secret,
            "judge_rationale": secret,
            "citations": [{"source_id": "source-1", "body": secret}],
        },
    )
    recorder.close()

    trace_text = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert secret not in trace_text
    assert "message_metadata" in trace_text
    assert "orchestration_decision" in trace_text


def test_langgraph_event_uses_same_versioned_contract_without_fact_values() -> None:
    secret = "synthetic-personal-fact"
    trace = workflow_event_to_decision_trace(
        {
            "workflow_run_id": "run-1",
            "correlation_id": "correlation-1",
            "case_id": "case-1",
            "session_id": "session-1",
            "flow_key": "flow-1",
            "flow_version": 2,
            "graph_version": 3,
            "routing_confidence": 0.93,
            "facts": {"name": secret},
            "verified_facts": {"claimant_name": secret},
            "missing_facts": ["claim_amount"],
            "legal_source_ids": ["source-1"],
        },
        {
            "event_id": "run-1:001:workflow_routed",
            "event_type": "workflow_routed",
            "stage": "route",
            "status": "completed",
            "created_at": "2026-09-05T00:00:00+00:00",
            "details": {"reason": "registered_flow_selected", "missing_fact_count": 1},
        },
    )

    payload = serialize_decision_trace(trace)
    assert payload["session_id"] == "session-1"
    assert secret not in json.dumps(payload)
    assert payload["evidence"][0]["reference_id"] == "source-1"  # type: ignore[index]
    decision = payload["decision"]
    assert isinstance(decision, dict)
    assert decision["field_ids"] == ["claim_amount", "claimant_name"]
    assert decision["metrics"] == {"missing_fact_count": 1}
