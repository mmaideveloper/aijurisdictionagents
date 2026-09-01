from __future__ import annotations

from collections.abc import Mapping, Sequence

from aijurisdictionagents.orchestration.primary_router import (
    PrimaryClassification,
    PrimaryLangGraphRouter,
    PrimaryRouteCandidate,
)


def _candidate(key: str = "sk.civil.payment_confirmation") -> PrimaryRouteCandidate:
    return PrimaryRouteCandidate(
        case_type_key=key,
        case_type_name="Potvrdenie o prijatí platby",
        description="Príprava potvrdenia o platbe.",
        keywords=("potvrdenie o platbe",),
        graph_key="legal_document_workflow",
        graph_version=4,
        flow_key=key,
        flow_version=2,
    )


def test_primary_router_selects_only_registered_high_confidence_flow() -> None:
    captured: dict[str, object] = {}

    def classify(
        question: str,
        verified_facts: Mapping[str, str],
        candidates: Sequence[PrimaryRouteCandidate],
    ) -> PrimaryClassification:
        captured.update(
            question=question,
            verified_facts=dict(verified_facts),
            candidate_keys=[item.case_type_key for item in candidates],
        )
        return PrimaryClassification(
            status="matched",
            selected_case_type_key="sk.civil.payment_confirmation",
            confidence=0.91,
            second_confidence=0.2,
        )

    decision = PrimaryLangGraphRouter(classifier=classify).route(
        question="  Priprav potvrdenie   o platbe. ",
        verified_facts={" amount ": " 100 EUR ", "empty": ""},
        candidates=[_candidate()],
    )

    assert decision.route == "dedicated_flow"
    assert decision.selected_case_type_key == "sk.civil.payment_confirmation"
    assert decision.evidence == (
        "primary_langgraph_router",
        "registered_published_flow_match",
        "current_question_and_verified_facts_only",
    )
    assert captured == {
        "question": "Priprav potvrdenie o platbe.",
        "verified_facts": {"amount": "100 EUR"},
        "candidate_keys": ["sk.civil.payment_confirmation"],
    }


def test_primary_router_asks_for_clarification_below_confidence_threshold() -> None:
    router = PrimaryLangGraphRouter(
        classifier=lambda *_args: PrimaryClassification(
            status="matched",
            selected_case_type_key="sk.civil.payment_confirmation",
            confidence=0.61,
            second_confidence=0.52,
            clarification_question="Chcete potvrdenie o platbe alebo inú listinu?",
        )
    )

    decision = router.route(question="Potrebujem potvrdenie", verified_facts={}, candidates=[_candidate()])

    assert decision.route == "clarification"
    assert decision.selected_case_type_key is None
    assert decision.clarification_question == "Chcete potvrdenie o platbe alebo inú listinu?"
    assert "no_case_flow_guessed" in decision.evidence


def test_primary_router_uses_generic_path_for_no_match_and_rejects_invented_key() -> None:
    no_match = PrimaryLangGraphRouter(
        classifier=lambda *_args: PrimaryClassification(status="no_match")
    ).route(question="Aké máte otváracie hodiny?", verified_facts={}, candidates=[_candidate()])
    invented = PrimaryLangGraphRouter(
        classifier=lambda *_args: PrimaryClassification(
            status="matched",
            selected_case_type_key="invented.flow",
            confidence=0.99,
        )
    ).route(question="Neznámy prípad", verified_facts={}, candidates=[_candidate()])

    assert no_match.route == "generic"
    assert invented.route == "generic"
    assert no_match.selected_case_type_key is None
    assert "generic_langgraph_route" in no_match.evidence


def test_primary_router_fails_closed_to_generic_when_classifier_is_unavailable() -> None:
    def unavailable(*_args: object) -> PrimaryClassification:
        raise RuntimeError("provider unavailable")

    decision = PrimaryLangGraphRouter(classifier=unavailable).route(
        question="Priprav potvrdenie",
        verified_facts={},
        candidates=[_candidate()],
    )

    assert decision.route == "generic"
    assert decision.selected_case_type_key is None
