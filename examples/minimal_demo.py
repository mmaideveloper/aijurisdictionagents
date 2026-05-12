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
from aijurisdictionagents.agents import AIAddressValidatorAgent, AIPropertyValidatorAgent
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
        "a JurisDicta professional document template (branded header/contact layout, "
        "formal body, score-aware disclaimer handling for low or unknown scores, footer logo, and QR traceability metadata "
        "including the document score plus session/user IDs when available, with titles inferred from the legal document type) "
        "for court/client/third-party documents, "
        "and fills missing party details from the signed-in user's profile when available, "
        "a Slovak legal header profile where needed, and Central-European font preferences. "
        "Rental packages with visible sections such as Nájomná zmluva, Inventárny zoznam, "
        "and Protokol o odovzdaní a prevzatí bytu export as a ZIP package. "
        "Assistant technical JSON/XML payloads are hidden from user-facing chat and saved as "
        "case documents with a view URL when the session is attached to a case. "
        "Generated session documents can be queued as email attachments after the user confirms "
        "the profile email recipient or a corrected email address given in chat. "
        "User-facing document processing messages hide internal session filenames while logs retain them. "
        "Lawyer output is validated so profile-backed name/address data is not repeated as missing, "
        "and incomplete profiles are called out for next-time defaults. "
        "Existing case chats refresh prior question/answer memory so answered rental-property address and party-role "
        "questions are not repeated after a document was prepared, and repeated answered questions are filtered "
        "from follow-up replies generally. Missing-information intros are normalized so a concrete follow-up "
        "question is always shown to the client. "
        "Document templates can also be previewed as PDFs from the chat simulator or batch-tested with "
        ".\\skills\\testdocument\\scripts\\test_document_templates.ps1."
    )
    print()
    print("=== Address validation mapping demo ===")
    address_result = AIAddressValidatorAgent().validate_from_text(
        "Námestie slobody 1, 811 06 Bratislava",
    )
    print(address_result)

    print()
    print("=== Property LV validation mapping demo ===")
    lv_result = AIPropertyValidatorAgent().build_lv_lookup_plan(
        person_name="Ján Novák",
    )
    print(lv_result)
    print()
    print("=== Registration email OTP API demo (request examples) ===")
    print("POST /v1/users/sign-up/send-code  {\"email\": \"user@example.com\"}")
    print(
        "POST /v1/users/sign-up/complete  "
        "{\"phone_number\":\"+421900123456\",\"email\":\"user@example.com\",\"password\":\"secret\",\"verification_code\":\"123456\"}"
    )
    print(
        "POST /v1/users/sign-in/send-code  "
        "{\"phone_number\":\"+421900123456\",\"device_id\":\"test-web-device\"}"
    )
    print(
        "POST /v1/users/sign-in/verify-code  "
        "{\"phone_number\":\"+421900123456\",\"device_id\":\"test-web-device\",\"verification_code\":\"123456\"}"
    )
    print()
    print("=== Email delivery setup demo ===")
    print("Public contact email: info@jurisdigta.eu")
    print("SMTP sender: no-reply@jurisdigta.eu")
    print("SMTP server: mail.webhouse.sk:587 with STARTTLS")
    print("SMTP password env: EMAIL_SMTP_PASSWORD")
    print("Chat simulator email test page: http://127.0.0.1:8090/email-tests")



def mobile_chat_fixes_summary() -> dict[str, str]:
    """Minimal runnable summary for mobile chat fixes."""
    return {
        "composer_alignment": "top-left with keyboard-aware height",
        "agent_label": "localized assistant label",
        "document_ready": "fallback enabled when generated draft is detected",
    }


if __name__ == "__main__":
    print(mobile_chat_fixes_summary())


def prepare_task_skill_summary() -> dict[str, object]:
    """Minimal runnable summary for the prepare-task skill contract."""
    return {
        "skill": "prepare-task",
        "source_modes": [
            "chat idea intake",
            "idea text",
            "existing GitHub issue/task description",
        ],
        "readiness_checks": [
            "repository context reviewed",
            "GDPR and EU AI Act risks evaluated",
            "acceptance criteria and test plan drafted",
            "docs and minimal runnable example identified",
        ],
        "github_task_creation": "ask for explicit confirmation before creating or updating",
        "default_minimal_example": "python examples/minimal_demo.py",
    }


if __name__ == "__main__":
    print(prepare_task_skill_summary())
