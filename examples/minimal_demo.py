"""Minimal runnable demo for repository workflows and contract simulations.

Run:
    python examples/minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aijurisdictionagents.e2e_workflows import (
    outcome_to_json,
    simulate_contract_summary_case,
    simulate_slovak_lease_review,
)
from aijurisdictionagents.agents import AIAddressValidatorAgent
from aijurisdictionagents.workflows import WorkflowEngine, WorkflowRouter, create_default_registry


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    output_root = Path("runs") / "minimal_demo"
    contract_outcome = simulate_contract_summary_case(output_root / "contract_summary_case")
    lease_outcome = simulate_slovak_lease_review(output_root / "slovak_lease_case")

    workflow_engine = WorkflowEngine(WorkflowRouter(create_default_registry()))
    workflow_result = workflow_engine.plan_case(
        question="Chcem pridat noveho spolocnika do s.r.o. a pripravit dokumenty.",
        country="SK",
        inputs={
            "company_id": "12345678",
            "current_owner_name": "Peter Novak",
            "new_co_owner_name": "Jan Novak",
            "ownership_share_percent": "25",
            "effective_date": "2026-04-30",
        },
        law_required_documents=("beneficial_owner_declaration",),
        external_facts={"current_owner_name": "Martin Novak"},
        model_suggested_screening=True,
    )

    print("=== Contract summary scenario ===")
    print(outcome_to_json(contract_outcome))
    print()
    print("=== Slovak lease review scenario ===")
    print(outcome_to_json(lease_outcome))
    print()
    print("=== Workflow routing scenario ===")
    print(f"Mode: {workflow_result.mode}")
    print(f"Confidence: {workflow_result.confidence:.2f}")
    print(f"Workflow: {workflow_result.workflow.workflow_id if workflow_result.workflow else 'N/A'}")
    if workflow_result.workflow:
        print(f"Workflow steps: {[step.step_id for step in workflow_result.workflow.steps]}")
    print(f"Global steps: {list(workflow_result.global_steps)}")
    print(f"Screening consent prompt: {workflow_result.screening_consent_prompt}")
    print(f"Screening task prompt: {workflow_result.screening_task_prompt}")
    print(f"Required documents: {list(workflow_result.required_documents)}")
    print(f"Missing inputs: {list(workflow_result.missing_inputs)}")
    print(f"Fact conflicts: {[{'field': c.field, 'user': c.user_value, 'registry': c.system_value} for c in workflow_result.fact_conflicts]}")
    if workflow_result.fact_conflicts:
        print(f"Confirmation question: {workflow_result.fact_conflicts[0].confirmation_question}")
    print(f"Validation issues: {[issue.message for issue in workflow_result.validation_issues]}")
    print()
    print("=== PDF export UX note ===")
    print(
        "For Slovakia-focused document exports, the API PDF builder now uses "
        "a Jurisdicta corporate document template (header + contact panel + centered title) "
        "for court/third-party facing documents, "
        "a Slovak legal header profile where needed, and Central-European font preferences. "
        "Rental packages with visible sections such as Nájomná zmluva, Inventárny zoznam, "
        "and Protokol o odovzdaní a prevzatí bytu export as a ZIP package. "
        "Document templates can also be previewed as PDFs from the chat simulator."
    )
    print()
    print("=== Address validation mapping demo ===")
    address_result = AIAddressValidatorAgent().validate_from_text(
        "Námestie slobody 1, 811 06 Bratislava",
    )
    print(address_result)
