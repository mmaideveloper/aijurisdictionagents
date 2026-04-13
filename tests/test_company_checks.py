from __future__ import annotations

from aijurisdictionagents.tools.company_checks import answer_slovak_company_seat_question
from aijurisdictionagents.tools.obchodnyregister import ObchodnyRegisterTool
from aijurisdictionagents.tools.registry import ToolRegistry


def _registry_with_payload(payload: str) -> ToolRegistry:
    tool = ObchodnyRegisterTool(requester=lambda _url: (200, "application/json", payload))
    return ToolRegistry(_tools={"obchodny_register_company_check": tool})


def test_answer_slovak_company_seat_question_recognizes_user_text_and_answers_match() -> None:
    payload = (
        '{"filteredCount":1,"data":[{"corporateBodyFullName":"Esolution SK s.r.o.",'
        '"registrationNumber":"55544433",'
        '"physicalAddressLine1":"Námestie sv. Egídia 42",'
        '"physicalAddressLine2":"058 01 Poprad"}]}'
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
        '{"filteredCount":1,"data":[{"corporateBodyFullName":"Esolution SK s.r.o.",'
        '"registrationNumber":"55544433",'
        '"physicalAddressLine1":"Námestie slobody 1",'
        '"physicalAddressLine2":"811 06 Bratislava"}]}'
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
