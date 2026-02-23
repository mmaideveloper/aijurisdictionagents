from __future__ import annotations

from pathlib import Path

from aijurisdictionagents.agents import AIAgentsValidator, ValidatorInputs


def test_validator_evaluates_payload() -> None:
    payload = {
        "qaPairs": [
            {
                "question": "What is the termination notice period under Slovak labor law?",
                "answer": "Typically two months depending on service length.",
            },
            {
                "question": "Should the employee consult a lawyer?",
                "answer": "Yes, because deadlines and risk depend on exact facts.",
            },
        ]
    }

    validator = AIAgentsValidator()
    report = validator.evaluate(
        communication_payload=payload,
        inputs=ValidatorInputs(
            country="SK",
            question="Can my employer terminate me immediately?",
            expected_points=("notice period", "termination grounds", "deadlines"),
        ),
        final_result="Termination usually requires legal grounds and notice period. Consult a lawyer due to deadlines.",
    )

    assert 0 <= report.weighted_accuracy <= 100
    assert report.scores
    assert "Strongest axis" in report.summary


def test_validator_reads_payload_from_file(tmp_path: Path) -> None:
    fixture = tmp_path / "communication.json"
    fixture.write_text('{"messages":[{"role":"assistant","content":"Provide the contract date."}]}', encoding="utf-8")

    validator = AIAgentsValidator()
    report = validator.evaluate_from_file(
        communication_path=fixture,
        inputs=ValidatorInputs(
            country="DE",
            question="Is my rental increase valid?",
            expected_points=("contract", "date"),
        ),
        final_result="Please verify the contract and date.",
    )

    assert report.weighted_accuracy >= 0
