from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .agents import AIAgentsValidator, ValidatorInputs, create_lawyer
from .agents.validator import EvaluationCriterion
from .documents import load_documents
from .observability import TraceRecorder
from .orchestration import Orchestrator
from .schemas import Document, Message



E2E_VALIDATION_CRITERIA: tuple[EvaluationCriterion, ...] = (
    EvaluationCriterion(name="legal_accuracy", description="Expected legal/test anchors are present.", weight=0.4),
    EvaluationCriterion(name="coverage", description="Expected points are covered by the transcript.", weight=0.3),
    EvaluationCriterion(name="clarity", description="The final output is concise and understandable.", weight=0.15),
    EvaluationCriterion(name="risk_awareness", description="Recommendations include next-step or caution language.", weight=0.15),
)


@dataclass(frozen=True)
class ContractSummaryOutcome:
    instruction: str
    case_dir: Path
    uploaded_files: tuple[Path, ...]
    summary: str
    recommendation: str
    weighted_accuracy: float
    citations: tuple[str, ...]


@dataclass(frozen=True)
class SlovakLeaseReviewOutcome:
    case_dir: Path
    original_document: Path
    revised_document: Path
    diff_pdf: Path
    invalid_areas: tuple[str, ...]
    revised_summary: str
    weighted_accuracy: float


class E2EScenarioLLM:
    """Deterministic LLM used by repository end-to-end simulations."""

    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        prompt_key = agent_name.lower()
        instruction = _first_user_message(conversation)
        if "finalsummary" in prompt_key:
            if "look to contract and prepare summary" in instruction.lower():
                summary = _build_contract_summary(documents)
                recommendation = (
                    "Recommendation: Request signatures, confirm the payment schedule, "
                    "and keep the termination clause aligned with the reviewed draft."
                )
                return f"Recommendation: {summary} {recommendation.partition(':')[2].strip()}\nRationale: The uploaded contract pages consistently describe the same lease arrangement."
            if "najomna zmluva" in instruction.lower() or "prenajom" in instruction.lower():
                issues = _find_slovak_lease_gaps(_latest_uploaded_document(documents).content)
                issue_text = "; ".join(issues) or "No compliance gaps detected"
                return (
                    "Recommendation: The uploaded lease should be updated to the current prenajom checklist; "
                    f"fix the following areas: {issue_text}.\n"
                    "Rationale: The old draft omits items required by the simulated current-law validation profile."
                )
            return "Recommendation: End-to-end simulation completed.\nRationale: Deterministic test path."

        if "lawyer" in prompt_key:
            if "look to contract and prepare summary" in instruction.lower():
                return (
                    f"Short contract summary: {_build_contract_summary(documents)} "
                    "Recommendation: verify signatures, rent due dates, and termination notice handling. "
                    "Do you want the final result in PDF format?"
                )
            if "najomna zmluva" in instruction.lower() or "prenajom" in instruction.lower():
                issues = _find_slovak_lease_gaps(_latest_uploaded_document(documents).content)
                return (
                    "Review result: the 2000 lease is outdated for the current prenajom checklist. "
                    f"Invalid areas: {'; '.join(issues)}. "
                    "Recommendation: replace the outdated clauses and generate a redline export. "
                    "Do you want the final result in PDF format?"
                )
        return "Recommendation: End-to-end simulation completed.\nRationale: Deterministic test path."


def create_simulated_pdf(path: Path, lines: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines).strip() + "\n"
    path.write_bytes(text.encode("utf-8"))
    return path


def simulate_contract_summary_case(case_dir: Path) -> ContractSummaryOutcome:
    instruction = "Look to contract and prepare summary"
    pages = (
        create_simulated_pdf(
            case_dir / "uploads" / "contract_page_1.pdf",
            [
                "LEASE AGREEMENT PAGE 1",
                "Landlord: Jana Novotna. Tenant: Tomas Hlavaty.",
                "Property: Dunajska 12, Bratislava.",
            ],
        ),
        create_simulated_pdf(
            case_dir / "uploads" / "contract_page_2.pdf",
            [
                "LEASE AGREEMENT PAGE 2",
                "Monthly rent: 850 EUR due by the 5th day of each month.",
                "Security deposit: 1700 EUR.",
            ],
        ),
        create_simulated_pdf(
            case_dir / "uploads" / "contract_page_3.pdf",
            [
                "LEASE AGREEMENT PAGE 3",
                "Notice period: one month in writing.",
                "Utilities are reimbursed monthly against invoices.",
            ],
        ),
    )
    documents = load_documents(case_dir / "uploads", allow_pdf=True)
    result = _run_orchestration(instruction=instruction, documents=documents)
    payload = {"messages": [asdict(message) for message in result.messages]}
    validator = AIAgentsValidator(criteria=E2E_VALIDATION_CRITERIA)
    report = validator.evaluate(
        communication_payload=payload,
        inputs=ValidatorInputs(
            country="SK",
            question=instruction,
            expected_points=(
                "landlord",
                "tenant",
                "property",
                "rent",
                "deposit",
                "notice",
                "utilities",
                "recommendation",
            ),
        ),
        final_result=result.final_recommendation,
    )
    recommendation = f"Recommendation: {result.final_recommendation}"
    return ContractSummaryOutcome(
        instruction=instruction,
        case_dir=case_dir,
        uploaded_files=pages,
        summary=_first_sentence(result.final_recommendation),
        recommendation=recommendation,
        weighted_accuracy=report.weighted_accuracy,
        citations=tuple(source.filename for source in result.citations),
    )


def simulate_slovak_lease_review(case_dir: Path) -> SlovakLeaseReviewOutcome:
    case_dir.mkdir(parents=True, exist_ok=True)
    original_text = _old_najomna_zmluva_2000()
    original_document = create_simulated_pdf(case_dir / "uploads" / "najomna_zmluva_2000.pdf", [original_text])
    documents = load_documents(case_dir / "uploads", allow_pdf=True)
    issues = _find_slovak_lease_gaps(documents[0].content)
    revised_text = _apply_slovak_lease_fixes(documents[0].content)
    revised_document = case_dir / "outputs" / "najomna_zmluva_2026_revised.txt"
    revised_document.parent.mkdir(parents=True, exist_ok=True)
    revised_document.write_text(revised_text, encoding="utf-8")

    diff_lines = list(
        difflib.unified_diff(
            documents[0].content.splitlines(),
            revised_text.splitlines(),
            fromfile="najomna_zmluva_2000",
            tofile="najomna_zmluva_2026_revised",
            lineterm="",
        )
    )
    diff_pdf = case_dir / "outputs" / "najomna_zmluva_diff.pdf"
    create_simulated_pdf(diff_pdf, diff_lines or ["No changes detected."])

    validator = AIAgentsValidator(criteria=E2E_VALIDATION_CRITERIA)
    report = validator.evaluate(
        communication_payload={
            "messages": [
                {
                    "role": "assistant",
                    "content": "The uploaded lease was reviewed against the current prenajom checklist.",
                }
            ]
        },
        inputs=ValidatorInputs(
            country="SK",
            question="Review the old najomna zmluva and update it for current prenajom rules.",
            expected_points=(
                "identification",
                "parties",
                "rent",
                "deposit",
                "maintenance",
                "repairs",
                "termination",
                "notice",
            ),
        ),
        final_result=(
            "Recommendation: update party identification, rent, deposit, maintenance repairs, and written termination notice.\n"
            + revised_text
        ),
        final_contract=revised_text,
        reference_contracts=(
            "Prenajimatel a najomca su riadne identifikovani. Najomne a depozit su jasne uvedene. "
            "Zmluva obsahuje pravidla oprav a pisomnu vypoved.",
        ),
    )

    return SlovakLeaseReviewOutcome(
        case_dir=case_dir,
        original_document=original_document,
        revised_document=revised_document,
        diff_pdf=diff_pdf,
        invalid_areas=tuple(issues),
        revised_summary=(
            "Updated the legacy lease by adding complete party identification, current payment/deposit "
            "terms, repair duties, and written termination handling."
        ),
        weighted_accuracy=report.weighted_accuracy,
    )


def _run_orchestration(*, instruction: str, documents: Sequence[Document]):
    trace_dir = documents and Path(documents[0].path).parents[1] / "run" or Path("runs") / "e2e"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace = TraceRecorder(trace_dir)
    try:
        orchestrator = Orchestrator(
            lawyer=create_lawyer(E2EScenarioLLM()),
            judge=None,
            trace=trace,
        )
        return orchestrator.run(
            instruction,
            documents,
            country="SK",
            language="en-US",
            discussion_type="advice",
            question_timeout_seconds=60,
            user_response_provider=lambda prompt, _timeout: "finish" if "other questions" in prompt.lower() else "no",
        )
    finally:
        trace.close()


def _build_contract_summary(documents: Sequence[Document]) -> str:
    text = " ".join(document.content.replace("\n", " ") for document in documents)
    landlord = _search_group(text, r"Landlord:\s*([^\.]+)")
    tenant = _search_group(text, r"Tenant:\s*([^\.]+)")
    property_address = _search_group(text, r"Property:\s*([^\.]+)")
    rent = _search_group(text, r"Monthly rent:\s*([^\.]+)")
    notice = _search_group(text, r"Notice period:\s*([^\.]+)")
    return (
        f"Short contract summary: {landlord} leases {property_address} to {tenant}; "
        f"{rent}; {notice}."
    )


def _find_slovak_lease_gaps(text: str) -> list[str]:
    checks = {
        "missing full party identification": ("rodne cislo" in _normalize(text) or "datum narodenia" in _normalize(text)),
        "missing explicit rent due date and deposit handling": ("splatne" in _normalize(text) and "depozit" in _normalize(text)),
        "missing maintenance and repair allocation": ("opravy" in _normalize(text) or "udrzba" in _normalize(text)),
        "missing written termination notice clause": ("pisomn" in _normalize(text) and "vypoved" in _normalize(text)),
    }
    return [name for name, passed in checks.items() if not passed]


def _apply_slovak_lease_fixes(text: str) -> str:
    base = text.strip()
    additions = [
        "",
        "DOPLNENE USTANOVENIA PRE AKTUALNY PRENAJOM:",
        "1. Zmluvne strany doplnia uplne identifikacne udaje vratane datumu narodenia a adresy trvaleho pobytu.",
        "2. Najomne 850 EUR je splatne do 5. dna kazdeho mesiaca; penazny depozit je vo vyske 1700 EUR.",
        "3. Bezna udrzba a drobne opravy znasa najomca, vacsie opravy zabezpecuje prenajimatel.",
        "4. Vypoved zmluvy musi byt pisomna a obsahovat vypovednu lehotu jeden mesiac.",
    ]
    return "\n".join([base, *additions]).strip() + "\n"


def _old_najomna_zmluva_2000() -> str:
    return (
        "NAJOMNA ZMLUVA Z ROKU 2000\n"
        "Prenajimatel prenechava byt najomcovi na byvanie.\n"
        "Najomne je 850 EUR mesacne.\n"
        "Ostatne podmienky sa dohodnu ustne medzi stranami."
    )


def _latest_uploaded_document(documents: Sequence[Document]) -> Document:
    if not documents:
        raise ValueError("At least one uploaded document is required.")
    return documents[-1]


def _first_user_message(conversation: Sequence[Message]) -> str:
    for message in conversation:
        if message.role == "user":
            return message.content
    return ""


def _search_group(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else "unspecified"


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0] if parts else text.strip()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def outcome_to_json(outcome: ContractSummaryOutcome | SlovakLeaseReviewOutcome) -> str:
    payload = asdict(outcome)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value)
        elif isinstance(value, tuple):
            payload[key] = [str(item) if isinstance(item, Path) else item for item in value]
    return json.dumps(payload, ensure_ascii=False, indent=2)
