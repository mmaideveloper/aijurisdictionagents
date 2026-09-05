from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph

from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    DeterministicCaseWorkflowServices,
    build_initial_case_workflow_state,
    record_quality_revision_failure,
    record_technical_retry_failure,
)


def _runtime() -> CaseWorkflowRuntime:
    return CaseWorkflowRuntime(
        services=DeterministicCaseWorkflowServices(
            legal_requirements=({"requirement": "Payment must be identified."},),
            legal_source_ids=("synthetic-law-1",),
        ),
        checkpointer=InMemorySaver(),
    )


def _state(
    *,
    facts: dict[str, str] | None = None,
    graph_key: str = "legal_document_workflow",
    graph_version: int = 1,
):
    flow_key = (
        "sk.civil.payment_confirmation"
        if graph_key == "legal_document_workflow"
        else "sk.system.unsupported_or_human_review"
    )
    return build_initial_case_workflow_state(
        workflow_run_id="workflow-test-1",
        correlation_id="correlation-test-1",
        case_id="synthetic-case-1",
        session_id="synthetic-session-1",
        user_id="synthetic-user-1",
        jurisdiction="SK",
        language="sk-SK",
        request_text="Priprav potvrdenie o zaplatení.",
        case_type_key="sk.civil.payment_confirmation",
        routing_confidence=0.99,
        routing_evidence=("synthetic deterministic match",),
        graph_key=graph_key,
        graph_version=graph_version,
        flow_key=flow_key,
        flow_version={1: 1, 2: 3, 3: 4, 4: 5}.get(graph_version, 1),
        flow_definition={
            "required_facts": ["payer", "recipient", "amount"],
            "mcp_retrieval": (
                {
                    "schema_version": 1,
                    "policy_id": "test.payment.requirements.v1",
                    "required": True,
                    "case_type_keys": ["sk.civil.payment_confirmation"],
                    "jurisdictions": ["SK"],
                    "query_keys": ["payment_confirmation_legal_requirements"],
                    "default_query": "potvrdenie",
                }
                if graph_version >= 2
                else {
                    "required": True,
                    "query_keys": ["payment_confirmation_legal_requirements"],
                }
            ),
            "optional_tools": ["company_check"],
            "tool_policy": (
                {
                    "schema_version": 1,
                    "tools": [],
                }
                if graph_version >= 3
                else None
            ),
            "presentation_policy": (
                {
                    "schema_version": 1,
                    "policy_id": "test.presentation.v1",
                    "default_renderer": "document_preview",
                    "renderers": [
                        {"renderer_id": "document_preview", "version": 1},
                        {"renderer_id": "sanitized_json", "version": 1},
                        {"renderer_id": "text", "version": 1},
                    ],
                    "user_overrides": ["document_preview", "sanitized_json", "text"],
                }
                if graph_version >= 4
                else None
            ),
        },
        facts=facts,
    )


def test_case_workflow_completes_and_records_ordered_review_events() -> None:
    outcome = _runtime().start(
        _state(facts={"payer": "A", "recipient": "B", "amount": "100 EUR"})
    )

    assert outcome.is_waiting is False
    assert outcome.state["status"] == "completed"
    assert outcome.state["review_decisions"] == {
        "output": "passed",
        "safety_gdpr": "passed",
        "case": "approved",
    }
    event_types = [event["event_type"] for event in outcome.state["events"]]
    assert event_types[:4] == [
        "langgraph_run_started",
        "workflow_routed",
        "workflow_assignment_pinned",
        "legal_requirements_retrieved",
    ]
    assert event_types[-4:] == [
        "output_validation_completed",
        "privacy_safety_validation_completed",
        "case_review_completed",
        "workflow_terminated",
    ]
    assert outcome.state["termination_reason"] == "quality_approved"


def test_case_workflow_interrupts_and_resumes_without_losing_pinned_versions() -> None:
    runtime = _runtime()
    first = runtime.start(_state(facts={"payer": "A", "recipient": "B"}))

    assert first.is_waiting is True
    assert first.state["status"] == "waiting_for_user"
    assert first.interrupts[0]["field"] == "amount"

    resumed = runtime.resume(
        graph_key="legal_document_workflow",
        graph_version=1,
        workflow_run_id="workflow-test-1",
        value={"amount": "100 EUR"},
    )

    assert resumed.is_waiting is False
    assert resumed.state["status"] == "completed"
    assert resumed.state["facts"]["amount"] == "100 EUR"
    assert resumed.state["graph_version"] == 1
    assert resumed.state["flow_version"] == 1
    assert [event["event_type"] for event in resumed.state["events"]].count(
        "workflow_assignment_pinned"
    ) == 1


def test_v2_verifies_facts_before_policy_driven_legal_retrieval() -> None:
    outcome = _runtime().start(
        _state(
            graph_version=2,
            facts={"payer": "A", "recipient": "B", "amount": "100 EUR"},
        )
    )

    event_types = [event["event_type"] for event in outcome.state["events"]]
    assert outcome.state["status"] == "completed"
    assert event_types.index("input_validation_completed") < event_types.index(
        "legal_requirements_retrieved"
    )
    retrieval_event = next(
        event for event in outcome.state["events"] if event["event_type"] == "legal_requirements_retrieved"
    )
    assert retrieval_event["details"]["retrieval_policy_id"] == "test.payment.requirements.v1"
    assert outcome.state["graph_version"] == 2
    assert outcome.state["flow_version"] == 3


def test_v4_selects_flow_assigned_presentation_without_exposing_case_data_to_trace() -> None:
    state = _state(
        graph_version=4,
        facts={"payer": "Synthetic A", "recipient": "Synthetic B", "amount": "100 EUR"},
    )
    state["request_text"] = "Priprav potvrdenie a zobraz výsledok ako JSON."

    outcome = _runtime().start(state)

    assert outcome.state["status"] == "completed"
    assert outcome.state["presentation"]["renderer_id"] == "sanitized_json"
    assert outcome.state["presentation"]["selection"]["reason_code"] == "explicit_user_format"
    event = next(
        item for item in outcome.state["events"] if item["event_type"] == "presentation_selected"
    )
    assert event["details"]["renderer_id"] == "sanitized_json"
    assert "Synthetic A" not in str(event)


def test_unsupported_case_type_fails_safe_to_human_review() -> None:
    outcome = _runtime().start(_state(graph_key="unsupported_or_human_review"))

    assert outcome.state["status"] == "human_review_required"
    assert outcome.state["escalation_reason"] == "case_type_not_automated"
    assert outcome.state["final_answer"] == ""
    assert outcome.state["termination_reason"] == "human_review_required"


def test_repeated_invalid_input_stops_at_configured_attempt_limit() -> None:
    runtime = _runtime()
    state = _state(facts={"payer": "A", "recipient": "B"})
    state["termination_policy"].update({"input_attempt_limit": 2, "no_progress_limit": 5})
    first = runtime.start(state)

    second = runtime.resume(
        graph_key="legal_document_workflow",
        graph_version=1,
        workflow_run_id=state["workflow_run_id"],
        value="",
        state=first.state,
    )
    final = runtime.resume(
        graph_key="legal_document_workflow",
        graph_version=1,
        workflow_run_id=state["workflow_run_id"],
        value="",
        state=second.state,
    )

    assert final.state["status"] == "human_review_required"
    assert final.state["termination_reason"] == "input_attempts_exhausted"
    assert final.state["input_attempt_count"] == 2
    assert [event["event_type"] for event in final.state["events"]].count(
        "workflow_terminated"
    ) == 1


def test_identical_missing_fact_failures_stop_for_no_progress() -> None:
    runtime = _runtime()
    state = _state(facts={"payer": "A", "recipient": "B"})
    state["termination_policy"].update({"input_attempt_limit": 5, "no_progress_limit": 2})
    first = runtime.start(state)
    second = runtime.resume(
        graph_key="legal_document_workflow",
        graph_version=1,
        workflow_run_id=state["workflow_run_id"],
        value="",
        state=first.state,
    )
    final = runtime.resume(
        graph_key="legal_document_workflow",
        graph_version=1,
        workflow_run_id=state["workflow_run_id"],
        value="",
        state=second.state,
    )

    assert final.state["termination_reason"] == "no_progress"


def test_reflection_policy_separates_quality_and_technical_retries() -> None:
    state = _state(facts={"payer": "A"})
    first = record_quality_revision_failure(
        state, failure_category="incomplete_output", output="unchanged"
    )
    final = record_quality_revision_failure(
        first, failure_category="incomplete_output", output="unchanged"
    )

    assert final["termination_reason"] == "no_progress"
    assert final["quality_revision_count"] == 2
    assert final["technical_retry_count"] == 0

    technical = record_technical_retry_failure(state, failure_category="provider_timeout")
    assert technical["technical_retry_count"] == 1
    assert technical["quality_revision_count"] == 0


def test_privacy_and_provenance_failures_bypass_reflection_retries() -> None:
    privacy = record_quality_revision_failure(
        _state(), failure_category="privacy", output="sensitive-output-not-persisted"
    )
    provenance = record_quality_revision_failure(
        _state(), failure_category="provenance_missing", output="draft"
    )

    assert privacy["termination_reason"] == "privacy_blocked"
    assert privacy["status"] == "blocked"
    assert provenance["termination_reason"] == "provenance_missing"
    assert provenance["status"] == "human_review_required"
    assert "sensitive-output-not-persisted" not in str(privacy["events"])


def test_deadline_and_cancellation_are_idempotent_terminal_outcomes() -> None:
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    state = _state()
    state["execution_deadline_at"] = past

    expired = _runtime().start(state)
    assert expired.state["termination_reason"] == "deadline_exceeded"
    assert expired.state["status"] == "blocked"

    session_state = _state()
    session_state["session_expires_at"] = past
    session_expired = _runtime().start(session_state)
    assert session_expired.state["termination_reason"] == "session_expired"

    runtime = _runtime()
    cancelled = runtime.terminate(_state(), reason="user_cancelled", stage="cancelled")
    repeated = runtime.terminate(cancelled.state, reason="user_cancelled", stage="cancelled")
    assert repeated.state["termination_reason"] == "user_cancelled"
    assert [event["event_type"] for event in repeated.state["events"]].count(
        "workflow_terminated"
    ) == 1


def test_graph_recursion_error_becomes_controlled_operational_failure() -> None:
    runtime = _runtime()
    builder = StateGraph(dict)
    builder.add_node("loop", lambda state: state)
    builder.add_edge(START, "loop")
    builder.add_edge("loop", "loop")
    runtime._graphs[("cyclic_test", 1)] = builder.compile(checkpointer=InMemorySaver())
    state = _state(graph_key="unsupported_or_human_review")
    state["graph_key"] = "cyclic_test"
    state["termination_policy"]["recursion_limit"] = 4

    outcome = runtime.start(state)

    assert outcome.state["termination_reason"] == "operational_failure"
    assert outcome.state["status"] == "human_review_required"
    assert outcome.state["stage"] == "recursion_limit"
