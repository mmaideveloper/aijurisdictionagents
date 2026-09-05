"""Run the deterministic LangGraph payment-confirmation reference workflow."""

import sys
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    DeterministicCaseWorkflowServices,
    build_initial_case_workflow_state,
)
from aijurisdictionagents.observability_decision_trace import (
    serialize_decision_trace,
    workflow_event_to_decision_trace,
)
from aijurisdictionagents.tools import build_default_tool_registry


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_id = str(uuid4())
    runtime = CaseWorkflowRuntime(
        services=DeterministicCaseWorkflowServices(
            legal_requirements=({"content": "Synthetic § 569 requirement"},),
            legal_source_ids=("synthetic-law-569",),
            tool_definitions=build_default_tool_registry().list_definitions(),
        ),
        checkpointer=InMemorySaver(),
    )
    outcome = runtime.start(
        build_initial_case_workflow_state(
            workflow_run_id=run_id,
            correlation_id=str(uuid4()),
            case_id="demo-case",
            session_id="demo-session",
            user_id="demo-user",
            jurisdiction="SK",
            language="sk-SK",
            request_text="Priprav potvrdenie o zaplatení pôžičky.",
            case_type_key="sk.civil.payment_confirmation",
            routing_confidence=1.0,
            routing_evidence=["demo exact match"],
            graph_key="legal_document_workflow",
            graph_version=3,
            flow_key="sk.civil.payment_confirmation",
            flow_version=4,
            flow_definition={
                "required_facts": ["payer", "recipient", "amount"],
                "conditional_facts": [],
                "mcp_retrieval": {
                    "schema_version": 1,
                    "policy_id": "demo.payment.requirements.v1",
                    "required": True,
                    "case_type_keys": ["sk.civil.payment_confirmation"],
                    "jurisdictions": ["SK"],
                    "query_keys": ["payment_confirmation_legal_requirements"],
                    "default_query": "potvrdenie",
                },
                "tool_policy": {
                    "schema_version": 1,
                    "policy_id": "demo.payment.tools.v1",
                    "tools": [
                        {
                            "name": "registeradries_address_validate",
                            "purpose": "Map the recipient address for this demo run.",
                            "provider": "registeradries.sk mapping",
                            "consent_scope": "demo.address.once",
                            "consent_text_version": "workflow-tool-consent-v1",
                            "required_fact_keys": ["recipient"],
                            "input_mapping": {"address_text": "recipient"},
                            "permitted_data_fields": ["recipient"],
                            "jurisdictions": ["SK"],
                            "timeout_seconds": 5,
                        }
                    ],
                },
            },
        )
    )
    for value in ("Platiteľ A", "Príjemca B", "100 EUR"):
        assert outcome.is_waiting
        print(f"interrupt => {outcome.interrupts[0]['field']}")
        outcome = runtime.resume(
            graph_key="legal_document_workflow",
            graph_version=3,
            workflow_run_id=run_id,
            value=value,
        )
    assert outcome.interrupts[0]["type"] == "tool_consent"
    print(f"interrupt => consent for {outcome.interrupts[0]['tool_name']}")
    outcome = runtime.resume(
        graph_key="legal_document_workflow",
        graph_version=3,
        workflow_run_id=run_id,
        value="Súhlasím",
    )
    print(f"status => {outcome.state['status']}")
    print(outcome.state["final_answer"])
    print("events => " + ", ".join(event["event_type"] for event in outcome.state["events"]))
    decision_trace = serialize_decision_trace(
        workflow_event_to_decision_trace(outcome.state, outcome.state["events"][-1])
    )
    assert decision_trace["session_id"] == "demo-session"
    assert "request_text" not in decision_trace
    assert "facts" not in decision_trace
    decision = decision_trace["decision"]
    assert isinstance(decision, dict)
    print(
        "decision trace => "
        f"v{decision_trace['schema_version']} "
        f"{decision_trace['event_type']} reason={decision['reason_code']}"
    )


if __name__ == "__main__":
    main()
