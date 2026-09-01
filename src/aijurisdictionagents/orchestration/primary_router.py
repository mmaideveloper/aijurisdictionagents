from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph


PrimaryRoute = Literal["dedicated_flow", "clarification", "generic"]


@dataclass(frozen=True)
class PrimaryRouteCandidate:
    """An executable case flow exposed to the constrained primary router."""

    case_type_key: str
    case_type_name: str
    description: str
    keywords: tuple[str, ...]
    graph_key: str
    graph_version: int
    flow_key: str
    flow_version: int


@dataclass(frozen=True)
class PrimaryClassification:
    status: Literal["matched", "ambiguous", "no_match"]
    selected_case_type_key: str | None = None
    confidence: float = 0.0
    second_case_type_key: str | None = None
    second_confidence: float = 0.0
    clarification_question: str = ""
    rationale: str = ""


@dataclass(frozen=True)
class PrimaryRouteDecision:
    route: PrimaryRoute
    selected_case_type_key: str | None
    confidence: float
    confidence_gap: float
    clarification_question: str
    evidence: tuple[str, ...]


PrimaryClassifier = Callable[
    [str, Mapping[str, str], Sequence[PrimaryRouteCandidate]], PrimaryClassification
]


class _PrimaryRouterState(TypedDict, total=False):
    question: str
    verified_facts: dict[str, str]
    candidates: tuple[PrimaryRouteCandidate, ...]
    classification: PrimaryClassification
    route: PrimaryRoute
    selected_case_type_key: str | None
    confidence: float
    confidence_gap: float
    clarification_question: str
    evidence: tuple[str, ...]


class PrimaryLangGraphRouter:
    """Route every question through LangGraph without inventing case workflows."""

    def __init__(
        self,
        *,
        classifier: PrimaryClassifier,
        confidence_threshold: float = 0.72,
        confidence_margin: float = 0.15,
    ) -> None:
        self._classifier = classifier
        self._confidence_threshold = _confidence(confidence_threshold)
        self._confidence_margin = _confidence(confidence_margin)
        builder = StateGraph(_PrimaryRouterState)
        builder.add_node("minimize_verified_context", self._minimize_verified_context)
        builder.add_node("classify_registered_flows", self._classify_registered_flows)
        builder.add_node("route_dedicated_flow", self._route_dedicated_flow)
        builder.add_node("ask_clarification", self._ask_clarification)
        builder.add_node("route_generic", self._route_generic)
        builder.add_edge(START, "minimize_verified_context")
        builder.add_edge("minimize_verified_context", "classify_registered_flows")
        builder.add_conditional_edges(
            "classify_registered_flows",
            self._route_after_classification,
            {
                "dedicated_flow": "route_dedicated_flow",
                "clarification": "ask_clarification",
                "generic": "route_generic",
            },
        )
        builder.add_edge("route_dedicated_flow", END)
        builder.add_edge("ask_clarification", END)
        builder.add_edge("route_generic", END)
        self._graph = builder.compile()

    def route(
        self,
        *,
        question: str,
        verified_facts: Mapping[str, str],
        candidates: Sequence[PrimaryRouteCandidate],
    ) -> PrimaryRouteDecision:
        state = cast(
            _PrimaryRouterState,
            self._graph.invoke(
                {
                    "question": question,
                    "verified_facts": dict(verified_facts),
                    "candidates": tuple(candidates),
                }
            ),
        )
        return PrimaryRouteDecision(
            route=state.get("route", "generic"),
            selected_case_type_key=state.get("selected_case_type_key"),
            confidence=_confidence(state.get("confidence", 0.0)),
            confidence_gap=_confidence(state.get("confidence_gap", 0.0)),
            clarification_question=str(state.get("clarification_question", "")).strip(),
            evidence=tuple(state.get("evidence", ())),
        )

    @staticmethod
    def _minimize_verified_context(state: _PrimaryRouterState) -> _PrimaryRouterState:
        question = " ".join(str(state.get("question", "")).split())[:12000]
        verified_facts = {
            str(key).strip()[:100]: " ".join(str(value).split())[:500]
            for key, value in sorted(state.get("verified_facts", {}).items())[:50]
            if str(key).strip() and str(value).strip()
        }
        return {**state, "question": question, "verified_facts": verified_facts}

    def _classify_registered_flows(self, state: _PrimaryRouterState) -> _PrimaryRouterState:
        candidates = tuple(state.get("candidates", ()))
        if not candidates:
            classification = PrimaryClassification(status="no_match")
        else:
            try:
                classification = self._classifier(
                    state.get("question", ""),
                    state.get("verified_facts", {}),
                    candidates,
                )
            except Exception:
                classification = PrimaryClassification(
                    status="no_match",
                    rationale="classifier_unavailable_fail_closed",
                )
        allowed_keys = {item.case_type_key for item in candidates}
        selected = classification.selected_case_type_key
        if selected not in allowed_keys:
            selected = None
        second = classification.second_case_type_key
        if second not in allowed_keys:
            second = None
        normalized = PrimaryClassification(
            status=classification.status,
            selected_case_type_key=selected,
            confidence=_confidence(classification.confidence),
            second_case_type_key=second,
            second_confidence=_confidence(classification.second_confidence),
            clarification_question=classification.clarification_question.strip()[:500],
            rationale=classification.rationale.strip()[:500],
        )
        return {**state, "classification": normalized}

    def _route_after_classification(self, state: _PrimaryRouterState) -> PrimaryRoute:
        result = state.get("classification", PrimaryClassification(status="no_match"))
        if result.status == "no_match" or result.selected_case_type_key is None:
            return "generic"
        gap = max(0.0, result.confidence - result.second_confidence)
        if (
            result.status == "ambiguous"
            or result.confidence < self._confidence_threshold
            or gap < self._confidence_margin
        ):
            return "clarification"
        return "dedicated_flow"

    @staticmethod
    def _route_dedicated_flow(state: _PrimaryRouterState) -> _PrimaryRouterState:
        result = state["classification"]
        gap = max(0.0, result.confidence - result.second_confidence)
        return {
            **state,
            "route": "dedicated_flow",
            "selected_case_type_key": result.selected_case_type_key,
            "confidence": result.confidence,
            "confidence_gap": gap,
            "clarification_question": "",
            "evidence": (
                "primary_langgraph_router",
                "registered_published_flow_match",
                "current_question_and_verified_facts_only",
            ),
        }

    @staticmethod
    def _ask_clarification(state: _PrimaryRouterState) -> _PrimaryRouterState:
        result = state["classification"]
        gap = max(0.0, result.confidence - result.second_confidence)
        question = result.clarification_question or (
            "Please clarify which legal outcome or document you want to prepare."
        )
        return {
            **state,
            "route": "clarification",
            "selected_case_type_key": None,
            "confidence": result.confidence,
            "confidence_gap": gap,
            "clarification_question": question,
            "evidence": (
                "primary_langgraph_router",
                "low_confidence_or_ambiguous",
                "no_case_flow_guessed",
            ),
        }

    @staticmethod
    def _route_generic(state: _PrimaryRouterState) -> _PrimaryRouterState:
        result = state.get("classification", PrimaryClassification(status="no_match"))
        return {
            **state,
            "route": "generic",
            "selected_case_type_key": None,
            "confidence": result.confidence,
            "confidence_gap": max(0.0, result.confidence - result.second_confidence),
            "clarification_question": "",
            "evidence": (
                "primary_langgraph_router",
                "no_registered_dedicated_flow_match",
                "generic_langgraph_route",
            ),
        }


def _confidence(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(parsed, 1.0))
