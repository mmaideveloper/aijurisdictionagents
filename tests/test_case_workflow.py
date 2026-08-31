from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    DeterministicCaseWorkflowServices,
    build_initial_case_workflow_state,
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
        flow_version=3 if graph_version == 2 else 1,
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
                if graph_version == 2
                else {
                    "required": True,
                    "query_keys": ["payment_confirmation_legal_requirements"],
                }
            ),
            "optional_tools": ["company_check"],
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
        "langgraph_run_completed",
    ]


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


def test_unsupported_case_type_fails_safe_to_human_review() -> None:
    outcome = _runtime().start(_state(graph_key="unsupported_or_human_review"))

    assert outcome.state["status"] == "human_review_required"
    assert outcome.state["escalation_reason"] == "case_type_not_automated"
    assert outcome.state["final_answer"] == ""
