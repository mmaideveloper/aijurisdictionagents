"""Minimal runnable demo for AIAgentsValidator.

Run:
    python examples/validator_demo.py
"""

from __future__ import annotations

from aijurisdictionagents.agents import AIAgentsValidator, ValidatorInputs


if __name__ == "__main__":
    sample_payload = {
        "qaPairs": [
            {
                "question": "What is the notice period for ending a rental contract?",
                "answer": "Usually one to three months depending on contract terms and local law.",
            },
            {
                "question": "Do I need a written notice?",
                "answer": "Yes, written notice is recommended and deadline compliance matters.",
            },
        ]
    }

    inputs = ValidatorInputs(
        country="SK",
        question="Can I terminate my apartment rental contract early?",
        expected_points=(
            "written notice",
            "termination deadline",
            "contract terms",
        ),
    )

    report = AIAgentsValidator().evaluate(
        communication_payload=sample_payload,
        inputs=inputs,
        final_result=(
            "Early termination depends on contract terms and statute. "
            "Use written notice and verify deadlines with a lawyer."
        ),
    )

    print("Weighted accuracy:", report.weighted_accuracy)
    print("Summary:", report.summary)
    for item in report.scores:
        print(f"- {item.name}: {item.score} ({item.rationale})")
