from __future__ import annotations

import pytest

from app.chat.api import _enforce_single_question_turn, _user_visible_text
from app.chat.mcp_law_context import _should_use_mcp_law_context
from app.mcp_law_retrieval import build_legal_query_profile


@pytest.mark.parametrize("prefix", ["USER-FACING (Slovak):", "**USER-FACING:**", "USER-FACING:"])
def test_explanation_keeps_headings_answers_and_sources(prefix: str) -> None:
    answer = (
        "**Prehľad**\n\n### Môže ísť do práce?\n"
        "Záleží na povolenom režime.\n\n### Do obchodu?\n"
        "Treba overiť podmienky.\n\n[Zdroj](https://example.org/law)"
    )
    raw = prefix + "\n" + answer + '\nCASE_UPDATE_JSON:\n{"case":{"open_questions":[]}}'
    assert _user_visible_text(_enforce_single_question_turn(raw)) == answer


@pytest.mark.parametrize("query", [
    "Vysvetli možnosti pre odsúdeného s náramkom, podmienky, môže ísť do práce? Do obchodu?",
    "Aké sú možnosti nosenia náramku pre odsúdeného, môže ísť do práce, do obchodu?",
    "Výkon trestu",
    "Ako funguje elektronický monitoring?",
    "Dostal som výpoveď z práce, čo môžem robiť?",
    "Ako funguje rozvod a výživné?",
])
def test_everyday_legal_questions_request_sources(query: str) -> None:
    assert _should_use_mcp_law_context(query=query, country="SK", language="sk")


@pytest.mark.parametrize("query", ["Ahoj", "Chcem elektronický náramok na behanie", "Do obchodu?", "Koľko je hodín?"])
def test_nonlegal_questions_do_not_activate_new_legal_markers(query: str) -> None:
    assert not _should_use_mcp_law_context(query=query, country="SK", language="sk")


def test_bracelet_query_expands_to_legal_monitoring_terms() -> None:
    profile = build_legal_query_profile("odsúdený s náramkom")
    assert "electronic_monitoring" in profile.concepts
    assert {"elektronick", "monitor", "probacn", "trest"} <= set(profile.expanded_roots)


def test_noncase_technical_envelope_is_not_lost_by_question_policy() -> None:
    content = '### Otázka?\nOdpoveď.\n```json\n{"diagnostic": "synthetic"}\n```'
    assert _enforce_single_question_turn(content) == content
