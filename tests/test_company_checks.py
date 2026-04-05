from __future__ import annotations

from aijurisdictionagents.tools.company_checks import answer_slovak_company_seat_question
from aijurisdictionagents.tools.obchodnyregister import ObchodnyRegisterTool
from aijurisdictionagents.tools.registry import ToolRegistry


def _registry_with_payload(payload: str) -> ToolRegistry:
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "application/json", payload))
    return ToolRegistry(_tools={"obchodny_register_company_check": tool})


def test_answer_slovak_company_seat_question_recognizes_user_text_and_answers_match() -> None:
    payload = (
        '{"items":[{"CorporateBodyFullName":"Esolution SK s.r.o.",'
        '"RegistrationNumber":"55544433",'
        '"RegisteredSeat":"Námestie sv. Egídia 42, Poprad",'
        '"Status":"Active"}]}'
    )
    registry = _registry_with_payload(payload)

    answer = answer_slovak_company_seat_question(
        "Zisti mi ci spolocnost Esolution SK s.r.o. sidli v Poprade?",
        registry=registry,
    )

    assert answer is not None
    assert answer.startswith("Áno")
    assert "Poprad" in answer
    assert "Esolution SK s.r.o." in answer


def test_answer_slovak_company_seat_question_reports_mismatch_city() -> None:
    payload = (
        '{"items":[{"CorporateBodyFullName":"Esolution SK s.r.o.",'
        '"RegistrationNumber":"55544433",'
        '"RegisteredSeat":"Bratislava",'
        '"Status":"Active"}]}'
    )
    registry = _registry_with_payload(payload)

    answer = answer_slovak_company_seat_question(
        "Zisti mi ci spolocnost Esolution SK s.r.o. sidli v Poprade?",
        registry=registry,
    )

    assert answer is not None
    assert answer.startswith("Nie")
    assert "Bratislava" in answer


def test_answer_slovak_company_seat_question_returns_none_for_unrelated_message() -> None:
    answer = answer_slovak_company_seat_question("Priprav mi najomnu zmluvu na byt.")

    assert answer is None
