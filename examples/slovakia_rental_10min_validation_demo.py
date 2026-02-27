"""Simulate a 10+ minute Slovak rental-lawyer chat and validate it.

Run:
    python examples/slovakia_rental_10min_validation_demo.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aijurisdictionagents.agents import (  # noqa: E402
    AIAgentsValidator,
    AIUserSimulatorAgent,
    ValidatorInputs,
    create_lawyer_agent,
)
from aijurisdictionagents.llm.mock import MockLLMClient  # noqa: E402
from aijurisdictionagents.schemas import Message  # noqa: E402


def main() -> None:
    llm = MockLLMClient()
    lawyer = create_lawyer_agent(llm, "SK")
    user = AIUserSimulatorAgent(llm=llm, language="sk")

    conversation: list[Message] = []
    qa_pairs: list[dict[str, str]] = []

    kickoff = (
        "Prosím priprav nájomnú zmluvu pre Slovensko. Prenajímateľ je fyzická osoba, "
        "nájomca manželský pár. Byt je v Bratislave, prenájom na 1 rok, výpovedná lehota 1 mesiac, "
        "nájomné 850 EUR, splatné do 5. dňa a dve mesačné nájomné vopred."
    )
    conversation.append(Message(role="user", agent_name="EndUser", content=kickoff))

    step_seconds = 65
    start_time = datetime(2026, 4, 1, 9, 0, 0)

    for turn_index in range(10):
        lawyer_text = lawyer.respond(conversation=conversation, documents=[], sources=[]).content
        conversation.append(Message(role="assistant", agent_name=lawyer.name, content=lawyer_text))

        user_text = user.prepare_random_answer(
            question=lawyer_text,
            conversation=conversation,
            documents=[],
        )
        conversation.append(Message(role="user", agent_name="EndUser", content=user_text))

        qa_pairs.append(
            {
                "minute": (start_time + timedelta(seconds=turn_index * step_seconds)).isoformat(),
                "question": lawyer_text,
                "answer": user_text,
            }
        )

    conversation.append(Message(role="user", agent_name="EndUser", content="Prosím priprav teraz kompletný návrh nájomnej zmluvy."))
    final_contract = lawyer.respond(conversation=conversation, documents=[], sources=[]).content

    payload = {"qaPairs": qa_pairs}
    reference_contract = (REPO_ROOT / "data" / "case_prenajom" / "sk_public_najomna_zmluva_template.txt").read_text(
        encoding="utf-8"
    )
    validator = AIAgentsValidator()

    report = validator.evaluate(
        communication_payload=payload,
        inputs=ValidatorInputs(
            country="SK",
            question="Ako pripraviť nájomnú zmluvu pre byt v Bratislave?",
            expected_points=(
                "zmluvne strany",
                "predmet najmu",
                "doba najmu",
                "najomne splatne",
                "platba vopred",
                "kaucia",
                "ukoncenie",
                "vypovedna lehota",
                "zaverecne ustanovenia",
            ),
        ),
        final_result=final_contract,
        final_contract=final_contract,
        reference_contracts=(reference_contract,),
    )

    result = {
        "simulated_duration_minutes": round((len(qa_pairs) * step_seconds) / 60, 2),
        "weighted_accuracy": report.weighted_accuracy,
        "human_likeness": report.human_likeness,
        "contract_similarity": report.contract_similarity,
        "summary": report.summary,
        "score_breakdown": [s.__dict__ for s in report.scores],
        "final_contract": final_contract,
    }

    output_path = REPO_ROOT / "data" / "case_prenajom" / "slovakia_rental_validation_report.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved report to: {output_path}")


if __name__ == "__main__":
    main()
