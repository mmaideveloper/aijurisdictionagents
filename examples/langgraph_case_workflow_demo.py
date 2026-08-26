"""Run the deterministic LangGraph payment-confirmation reference workflow."""

import sys
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    DeterministicCaseWorkflowServices,
    build_initial_case_workflow_state,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_id = str(uuid4())
    runtime = CaseWorkflowRuntime(
        services=DeterministicCaseWorkflowServices(
            legal_requirements=({"content": "Synthetic § 569 requirement"},),
            legal_source_ids=("synthetic-law-569",),
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
            graph_version=1,
            flow_key="sk.civil.payment_confirmation",
            flow_version=1,
            flow_definition={
                "required_facts": ["payer", "recipient", "amount"],
                "conditional_facts": [],
                "mcp_retrieval": {"required": True},
                "optional_tools": [],
            },
        )
    )
    for value in ("Platiteľ A", "Príjemca B", "100 EUR"):
        assert outcome.is_waiting
        print(f"interrupt => {outcome.interrupts[0]['field']}")
        outcome = runtime.resume(
            graph_key="legal_document_workflow",
            graph_version=1,
            workflow_run_id=run_id,
            value=value,
        )
    print(f"status => {outcome.state['status']}")
    print(outcome.state["final_answer"])
    print("events => " + ", ".join(event["event_type"] for event in outcome.state["events"]))


if __name__ == "__main__":
    main()
