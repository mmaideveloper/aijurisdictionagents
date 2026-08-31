from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Interrupt, interrupt

from .retrieval_policy import (
    McpRetrievalPolicyError,
    build_mcp_retrieval_request,
    validate_mcp_retrieval_policy,
)


WorkflowStatus = Literal[
    "running",
    "waiting_for_user",
    "completed",
    "human_review_required",
    "blocked",
]
ReviewDisposition = Literal["approved", "revisions_required", "human_review_required"]


class WorkflowEvent(TypedDict):
    event_id: str
    event_type: str
    stage: str
    status: str
    created_at: str
    details: dict[str, str | int | float | bool | None]


class CaseWorkflowState(TypedDict, total=False):
    schema_version: int
    workflow_run_id: str
    correlation_id: str
    case_id: str
    session_id: str
    user_id: str
    jurisdiction: str
    language: str
    request_text: str
    external_provider_acknowledged: bool
    case_type_key: str
    routing_confidence: float
    routing_evidence: list[str]
    graph_key: str
    graph_version: int
    flow_key: str
    flow_version: int
    flow_definition: dict[str, Any]
    required_facts: list[str]
    conditional_facts: list[dict[str, Any]]
    facts: dict[str, str]
    verified_facts: dict[str, str]
    missing_facts: list[str]
    unresolved_conflicts: list[str]
    legal_requirements: list[dict[str, Any]]
    legal_source_ids: list[str]
    offered_checks: list[str]
    consented_checks: list[str]
    tool_results: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    review_decisions: dict[str, str]
    stage: str
    status: WorkflowStatus
    pending_action: dict[str, Any]
    final_answer: str
    escalation_reason: str
    retry_count: int
    events: list[WorkflowEvent]


class CaseWorkflowServices(Protocol):
    def retrieve_legal_requirements(
        self, state: CaseWorkflowState
    ) -> tuple[list[dict[str, Any]], list[str]]: ...

    def execute_consented_tools(
        self, state: CaseWorkflowState, tool_names: Sequence[str]
    ) -> list[dict[str, Any]]: ...

    def draft_documents(
        self, state: CaseWorkflowState
    ) -> tuple[str, list[dict[str, Any]]]: ...

    def review_output(self, state: CaseWorkflowState) -> tuple[bool, str]: ...

    def review_safety_and_gdpr(self, state: CaseWorkflowState) -> tuple[bool, str]: ...

    def review_case(self, state: CaseWorkflowState) -> tuple[ReviewDisposition, str]: ...


@dataclass(frozen=True)
class DeterministicCaseWorkflowServices:
    """Safe reference services for tests and the minimal runnable example."""

    legal_requirements: tuple[dict[str, Any], ...] = ()
    legal_source_ids: tuple[str, ...] = ()

    def retrieve_legal_requirements(
        self, state: CaseWorkflowState
    ) -> tuple[list[dict[str, Any]], list[str]]:
        del state
        return [dict(item) for item in self.legal_requirements], list(self.legal_source_ids)

    def execute_consented_tools(
        self, state: CaseWorkflowState, tool_names: Sequence[str]
    ) -> list[dict[str, Any]]:
        del state
        return [
            {"tool_name": name, "status": "not_configured", "verified": False}
            for name in tool_names
        ]

    def draft_documents(
        self, state: CaseWorkflowState
    ) -> tuple[str, list[dict[str, Any]]]:
        facts = state.get("verified_facts", {})
        fact_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(facts.items()))
        answer = f"Workflow {state['flow_key']} prepared a reviewed draft.\n{fact_lines}".strip()
        return answer, [
            {
                "artifact_id": f"{state['workflow_run_id']}:draft",
                "artifact_type": "legal_document_draft",
                "status": "draft",
            }
        ]

    def review_output(self, state: CaseWorkflowState) -> tuple[bool, str]:
        answer = state.get("final_answer", "")
        if "[" in answer or "]" in answer:
            return False, "unresolved_placeholder"
        return bool(answer.strip()), "output_present" if answer.strip() else "output_missing"

    def review_safety_and_gdpr(self, state: CaseWorkflowState) -> tuple[bool, str]:
        unauthorized = set(state.get("offered_checks", ())) - set(state.get("consented_checks", ()))
        executed = {str(item.get("tool_name", "")) for item in state.get("tool_results", ())}
        if unauthorized & executed:
            return False, "tool_executed_without_consent"
        return True, "privacy_policy_passed"

    def review_case(self, state: CaseWorkflowState) -> tuple[ReviewDisposition, str]:
        decisions = state.get("review_decisions", {})
        if decisions.get("output") != "passed" or decisions.get("safety_gdpr") != "passed":
            return "human_review_required", "required_review_failed"
        return "approved", "all_required_reviews_passed"


@dataclass(frozen=True)
class CaseWorkflowOutcome:
    state: CaseWorkflowState
    interrupts: tuple[dict[str, Any], ...]

    @property
    def is_waiting(self) -> bool:
        return bool(self.interrupts)


class CaseWorkflowRuntime:
    def __init__(
        self,
        *,
        services: CaseWorkflowServices,
        checkpointer: BaseCheckpointSaver[Any],
    ) -> None:
        self._services = services
        self._graphs = {
            ("legal_document_workflow", 1): self._build_legal_document_graph(
                checkpointer, verify_before_retrieval=False
            ),
            ("legal_document_workflow", 2): self._build_legal_document_graph(
                checkpointer, verify_before_retrieval=True
            ),
            ("unsupported_or_human_review", 1): self._build_unsupported_graph(checkpointer),
        }

    def registered_graphs(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._graphs))

    def start(self, state: CaseWorkflowState) -> CaseWorkflowOutcome:
        _validate_initial_state(state)
        graph = self._graph(state["graph_key"], state["graph_version"])
        result = graph.invoke(
            state,
            config={"configurable": {"thread_id": state["workflow_run_id"]}},
        )
        return _outcome(result)

    def resume(
        self,
        *,
        graph_key: str,
        graph_version: int,
        workflow_run_id: str,
        value: str | Mapping[str, str],
    ) -> CaseWorkflowOutcome:
        graph = self._graph(graph_key, graph_version)
        result = graph.invoke(
            Command(resume=dict(value) if isinstance(value, Mapping) else value),
            config={"configurable": {"thread_id": workflow_run_id}},
        )
        return _outcome(result)

    def get_state(
        self, *, graph_key: str, graph_version: int, workflow_run_id: str
    ) -> CaseWorkflowState:
        graph = self._graph(graph_key, graph_version)
        snapshot = graph.get_state({"configurable": {"thread_id": workflow_run_id}})
        return cast(CaseWorkflowState, dict(snapshot.values))

    def _graph(self, graph_key: str, graph_version: int) -> Any:
        try:
            return self._graphs[(graph_key, graph_version)]
        except KeyError as exc:
            raise ValueError(f"Unregistered graph: {graph_key}@{graph_version}") from exc

    def _build_legal_document_graph(
        self,
        checkpointer: BaseCheckpointSaver[Any],
        *,
        verify_before_retrieval: bool,
    ) -> Any:
        builder = StateGraph(CaseWorkflowState)
        builder.add_node("route_case_type", self._route_case_type)
        builder.add_node("load_flow_pack", self._load_flow_pack)
        builder.add_node("retrieve_legal_requirements", self._retrieve_legal_requirements)
        builder.add_node("verify_input", self._verify_input)
        builder.add_node("collect_missing_facts", self._collect_missing_facts)
        builder.add_node("offer_optional_verification", self._offer_optional_verification)
        builder.add_node("execute_consented_tools", self._execute_consented_tools)
        builder.add_node("resolve_conflicts", self._resolve_conflicts)
        builder.add_node("draft_documents", self._draft_documents)
        builder.add_node("verify_output", self._verify_output)
        builder.add_node("verify_safety_and_gdpr", self._verify_safety_and_gdpr)
        builder.add_node("review_case", self._review_case)
        builder.add_node("finalize_or_escalate", self._finalize_or_escalate)
        builder.add_edge(START, "route_case_type")
        builder.add_edge("route_case_type", "load_flow_pack")
        if verify_before_retrieval:
            builder.add_conditional_edges(
                "load_flow_pack",
                self._after_flow_load_for_verified_retrieval,
                {"verify": "verify_input", "finalize": "finalize_or_escalate"},
            )
            builder.add_conditional_edges(
                "verify_input",
                self._after_input_verification_for_retrieval,
                {"collect": "collect_missing_facts", "retrieve": "retrieve_legal_requirements"},
            )
            builder.add_conditional_edges(
                "retrieve_legal_requirements",
                self._after_legal_retrieval_for_verified_retrieval,
                {"continue": "offer_optional_verification", "finalize": "finalize_or_escalate"},
            )
        else:
            builder.add_conditional_edges(
                "load_flow_pack",
                self._after_flow_load,
                {"retrieve": "retrieve_legal_requirements", "finalize": "finalize_or_escalate"},
            )
            builder.add_conditional_edges(
                "retrieve_legal_requirements",
                self._after_legal_retrieval,
                {"verify": "verify_input", "finalize": "finalize_or_escalate"},
            )
            builder.add_conditional_edges(
                "verify_input",
                self._after_input_verification,
                {"collect": "collect_missing_facts", "continue": "offer_optional_verification"},
            )
        builder.add_edge("collect_missing_facts", "verify_input")
        builder.add_edge("offer_optional_verification", "execute_consented_tools")
        builder.add_edge("execute_consented_tools", "resolve_conflicts")
        builder.add_conditional_edges(
            "resolve_conflicts",
            self._after_conflict_resolution,
            {"draft": "draft_documents", "finalize": "finalize_or_escalate"},
        )
        builder.add_edge("draft_documents", "verify_output")
        builder.add_edge("verify_output", "verify_safety_and_gdpr")
        builder.add_edge("verify_safety_and_gdpr", "review_case")
        builder.add_edge("review_case", "finalize_or_escalate")
        builder.add_edge("finalize_or_escalate", END)
        return builder.compile(checkpointer=checkpointer)

    def _build_unsupported_graph(self, checkpointer: BaseCheckpointSaver[Any]) -> Any:
        builder = StateGraph(CaseWorkflowState)
        builder.add_node("route_case_type", self._route_case_type)
        builder.add_node("require_human_review", self._require_human_review)
        builder.add_edge(START, "route_case_type")
        builder.add_edge("route_case_type", "require_human_review")
        builder.add_edge("require_human_review", END)
        return builder.compile(checkpointer=checkpointer)

    def _route_case_type(self, state: CaseWorkflowState) -> CaseWorkflowState:
        return _update(
            state,
            stage="route_case_type",
            status="running",
            event_type="workflow_routed",
            details={
                "case_type_key": state["case_type_key"],
                "routing_confidence": state.get("routing_confidence", 0.0),
            },
        )

    def _load_flow_pack(self, state: CaseWorkflowState) -> CaseWorkflowState:
        definition = state.get("flow_definition", {})
        required_facts = definition.get("required_facts", [])
        if not isinstance(required_facts, list) or not all(
            isinstance(item, str) and item.strip() for item in required_facts
        ):
            return _update(
                state,
                stage="load_flow_pack",
                status="blocked",
                escalation_reason="invalid_required_facts_schema",
                event_type="workflow_configuration_rejected",
                event_status="blocked",
                details={"reason": "invalid_required_facts_schema"},
            )
        try:
            validate_mcp_retrieval_policy(
                definition.get("mcp_retrieval"),
                case_type_key=state["case_type_key"],
                jurisdiction=state.get("jurisdiction", ""),
                strict=state.get("graph_version", 1) >= 2,
            )
        except McpRetrievalPolicyError as exc:
            return _update(
                state,
                stage="load_flow_pack",
                status="blocked",
                escalation_reason=str(exc),
                event_type="workflow_configuration_rejected",
                event_status="blocked",
                details={"reason": str(exc)},
            )
        return _update(
            state,
            stage="load_flow_pack",
            status="running",
            required_facts=[item.strip() for item in required_facts],
            conditional_facts=list(definition.get("conditional_facts", [])),
            event_type="workflow_assignment_pinned",
            details={
                "graph_key": state["graph_key"],
                "graph_version": state["graph_version"],
                "flow_key": state["flow_key"],
                "flow_version": state["flow_version"],
            },
        )

    @staticmethod
    def _after_flow_load(state: CaseWorkflowState) -> str:
        return "finalize" if state.get("status") == "blocked" else "retrieve"

    @staticmethod
    def _after_flow_load_for_verified_retrieval(state: CaseWorkflowState) -> str:
        return "finalize" if state.get("status") == "blocked" else "verify"

    def _retrieve_legal_requirements(self, state: CaseWorkflowState) -> CaseWorkflowState:
        request = build_mcp_retrieval_request(
            policy=state.get("flow_definition", {}).get("mcp_retrieval"),
            case_type_key=state["case_type_key"],
            jurisdiction=state.get("jurisdiction", ""),
            verified_facts=state.get("verified_facts", {}),
            strict=state.get("graph_version", 1) >= 2,
        )
        requirements, source_ids = self._services.retrieve_legal_requirements(state)
        policy = state.get("flow_definition", {}).get("mcp_retrieval", {})
        evidence_required = bool(policy.get("required", True))
        if evidence_required and not source_ids:
            return _update(
                state,
                stage="retrieve_legal_requirements",
                status="human_review_required",
                escalation_reason="required_legal_evidence_unavailable",
                legal_requirements=requirements,
                legal_source_ids=[],
                event_type="legal_retrieval_failed",
                event_status="human_review_required",
                details={
                    "reason": "required_legal_evidence_unavailable",
                    "retrieval_policy_id": request.policy_id,
                },
            )
        return _update(
            state,
            stage="retrieve_legal_requirements",
            status="running",
            legal_requirements=requirements,
            legal_source_ids=source_ids,
            event_type="legal_requirements_retrieved",
            details={
                "source_count": len(source_ids),
                "source_ids": ",".join(source_ids[:10]),
                "retrieval_policy_id": request.policy_id,
                "matched_fact_count": len(request.matched_fact_keys),
            },
        )

    @staticmethod
    def _after_legal_retrieval(state: CaseWorkflowState) -> str:
        return "finalize" if state.get("status") == "human_review_required" else "verify"

    @staticmethod
    def _after_legal_retrieval_for_verified_retrieval(state: CaseWorkflowState) -> str:
        return "finalize" if state.get("status") == "human_review_required" else "continue"

    def _verify_input(self, state: CaseWorkflowState) -> CaseWorkflowState:
        facts = {key: value.strip() for key, value in state.get("facts", {}).items() if value.strip()}
        missing = [key for key in state.get("required_facts", []) if not facts.get(key)]
        return _update(
            state,
            stage="verify_input",
            status="running",
            facts=facts,
            verified_facts=facts,
            missing_facts=missing,
            event_type="input_validation_completed",
            details={"missing_fact_count": len(missing)},
        )

    @staticmethod
    def _after_input_verification(state: CaseWorkflowState) -> str:
        return "collect" if state.get("missing_facts") else "continue"

    @staticmethod
    def _after_input_verification_for_retrieval(state: CaseWorkflowState) -> str:
        return "collect" if state.get("missing_facts") else "retrieve"

    def _collect_missing_facts(self, state: CaseWorkflowState) -> CaseWorkflowState:
        missing = state.get("missing_facts", [])
        if not missing:
            return state
        field_name = missing[0]
        response = interrupt(
            {
                "type": "missing_fact",
                "workflow_run_id": state["workflow_run_id"],
                "field": field_name,
                "remaining": len(missing),
                "message": f"Provide the required fact: {field_name}",
            }
        )
        value = response.get(field_name, "") if isinstance(response, Mapping) else str(response)
        value = str(value).strip()
        facts = dict(state.get("facts", {}))
        if value:
            facts[field_name] = value
        return _update(
            state,
            stage="collect_missing_facts",
            status="running",
            facts=facts,
            event_type="workflow_resumed",
            details={"provided_field": field_name, "value_recorded": bool(value)},
        )

    def _offer_optional_verification(self, state: CaseWorkflowState) -> CaseWorkflowState:
        optional_tools = state.get("flow_definition", {}).get("optional_tools", [])
        offered = [item for item in optional_tools if isinstance(item, str)]
        return _update(
            state,
            stage="offer_optional_verification",
            status="running",
            offered_checks=offered,
            event_type="optional_verification_offered",
            details={"check_count": len(offered)},
        )

    def _execute_consented_tools(self, state: CaseWorkflowState) -> CaseWorkflowState:
        offered = set(state.get("offered_checks", []))
        consented = [item for item in state.get("consented_checks", []) if item in offered]
        results = self._services.execute_consented_tools(state, consented)
        return _update(
            state,
            stage="execute_consented_tools",
            status="running",
            consented_checks=consented,
            tool_results=results,
            event_type="consented_tools_completed",
            details={"executed_count": len(results)},
        )

    def _resolve_conflicts(self, state: CaseWorkflowState) -> CaseWorkflowState:
        conflicts = state.get("unresolved_conflicts", [])
        if conflicts:
            return _update(
                state,
                stage="resolve_conflicts",
                status="human_review_required",
                escalation_reason="unresolved_fact_conflicts",
                event_type="workflow_conflict_blocked",
                event_status="human_review_required",
                details={"conflict_count": len(conflicts)},
            )
        return _update(
            state,
            stage="resolve_conflicts",
            status="running",
            event_type="workflow_conflicts_resolved",
            details={"conflict_count": 0},
        )

    @staticmethod
    def _after_conflict_resolution(state: CaseWorkflowState) -> str:
        return "finalize" if state.get("status") == "human_review_required" else "draft"

    def _draft_documents(self, state: CaseWorkflowState) -> CaseWorkflowState:
        answer, artifacts = self._services.draft_documents(state)
        return _update(
            state,
            stage="draft_documents",
            status="running",
            final_answer=answer,
            artifacts=artifacts,
            event_type="documents_drafted",
            details={"artifact_count": len(artifacts)},
        )

    def _verify_output(self, state: CaseWorkflowState) -> CaseWorkflowState:
        passed, reason = self._services.review_output(state)
        decisions = dict(state.get("review_decisions", {}))
        decisions["output"] = "passed" if passed else "failed"
        return _update(
            state,
            stage="verify_output",
            status="running" if passed else "human_review_required",
            escalation_reason="" if passed else reason,
            review_decisions=decisions,
            event_type="output_validation_completed",
            event_status="passed" if passed else "human_review_required",
            details={"passed": passed, "reason": reason},
        )

    def _verify_safety_and_gdpr(self, state: CaseWorkflowState) -> CaseWorkflowState:
        passed, reason = self._services.review_safety_and_gdpr(state)
        decisions = dict(state.get("review_decisions", {}))
        decisions["safety_gdpr"] = "passed" if passed else "failed"
        return _update(
            state,
            stage="verify_safety_and_gdpr",
            status="running" if passed else "blocked",
            escalation_reason=state.get("escalation_reason", "") if passed else reason,
            review_decisions=decisions,
            event_type="privacy_safety_validation_completed",
            event_status="passed" if passed else "blocked",
            details={"passed": passed, "reason": reason},
        )

    def _review_case(self, state: CaseWorkflowState) -> CaseWorkflowState:
        disposition, reason = self._services.review_case(state)
        decisions = dict(state.get("review_decisions", {}))
        decisions["case"] = disposition
        status: WorkflowStatus = "running" if disposition == "approved" else "human_review_required"
        return _update(
            state,
            stage="review_case",
            status=status,
            escalation_reason=(
                state.get("escalation_reason", "") if disposition == "approved" else reason
            ),
            review_decisions=decisions,
            event_type="case_review_completed",
            event_status=disposition,
            details={"disposition": disposition, "reason": reason},
        )

    def _finalize_or_escalate(self, state: CaseWorkflowState) -> CaseWorkflowState:
        final_status: WorkflowStatus
        if state.get("status") in {"blocked", "human_review_required"}:
            final_status = cast(WorkflowStatus, state["status"])
        elif state.get("review_decisions", {}).get("case") == "approved":
            final_status = "completed"
        else:
            final_status = "human_review_required"
        return _update(
            state,
            stage="finalize_or_escalate",
            status=final_status,
            event_type=(
                "langgraph_run_completed"
                if final_status == "completed"
                else "langgraph_run_escalated"
            ),
            event_status=final_status,
            details={"final_status": final_status},
        )

    def _require_human_review(self, state: CaseWorkflowState) -> CaseWorkflowState:
        return _update(
            state,
            stage="require_human_review",
            status="human_review_required",
            escalation_reason="case_type_not_automated",
            event_type="workflow_finalized",
            event_status="human_review_required",
            details={"reason": "case_type_not_automated"},
        )


def build_initial_case_workflow_state(
    *,
    workflow_run_id: str,
    correlation_id: str,
    case_id: str,
    session_id: str,
    user_id: str,
    jurisdiction: str,
    language: str,
    request_text: str,
    case_type_key: str,
    routing_confidence: float,
    routing_evidence: Sequence[str],
    graph_key: str,
    graph_version: int,
    flow_key: str,
    flow_version: int,
    flow_definition: Mapping[str, Any],
    facts: Mapping[str, str] | None = None,
    consented_checks: Sequence[str] = (),
    external_provider_acknowledged: bool = False,
) -> CaseWorkflowState:
    return CaseWorkflowState(
        schema_version=1,
        workflow_run_id=workflow_run_id,
        correlation_id=correlation_id,
        case_id=case_id,
        session_id=session_id,
        user_id=user_id,
        jurisdiction=jurisdiction,
        language=language,
        request_text=request_text,
        external_provider_acknowledged=external_provider_acknowledged,
        case_type_key=case_type_key,
        routing_confidence=max(0.0, min(1.0, routing_confidence)),
        routing_evidence=[item[:200] for item in routing_evidence[:10]],
        graph_key=graph_key,
        graph_version=graph_version,
        flow_key=flow_key,
        flow_version=flow_version,
        flow_definition=dict(flow_definition),
        facts=dict(facts or {}),
        verified_facts={},
        missing_facts=[],
        unresolved_conflicts=[],
        legal_requirements=[],
        legal_source_ids=[],
        offered_checks=[],
        consented_checks=list(consented_checks),
        tool_results=[],
        artifacts=[],
        review_decisions={},
        stage="created",
        status="running",
        pending_action={},
        final_answer="",
        escalation_reason="",
        retry_count=0,
        events=[
            WorkflowEvent(
                event_id=f"{workflow_run_id}:001:langgraph_run_started",
                event_type="langgraph_run_started",
                stage="created",
                status="running",
                created_at=datetime.now(timezone.utc).isoformat(),
                details={"thread_id": workflow_run_id},
            )
        ],
    )


def _validate_initial_state(state: CaseWorkflowState) -> None:
    required = (
        "workflow_run_id",
        "correlation_id",
        "case_type_key",
        "graph_key",
        "graph_version",
        "flow_key",
        "flow_version",
    )
    missing = [key for key in required if not state.get(key)]
    if missing:
        raise ValueError(f"Missing workflow state fields: {', '.join(missing)}")
    if len(state["workflow_run_id"]) > 255:
        raise ValueError("workflow_run_id must be at most 255 characters")


def _update(
    state: CaseWorkflowState,
    *,
    stage: str,
    status: WorkflowStatus,
    event_type: str,
    details: dict[str, str | int | float | bool | None],
    event_status: str | None = None,
    **changes: Any,
) -> CaseWorkflowState:
    events = list(state.get("events", []))
    sequence = _next_event_sequence(events, resuming=event_type == "workflow_resumed")
    event = WorkflowEvent(
        event_id=f"{state['workflow_run_id']}:{sequence:03d}:{event_type}",
        event_type=event_type,
        stage=stage,
        status=event_status or status,
        created_at=datetime.now(timezone.utc).isoformat(),
        details=details,
    )
    events.append(event)
    result = dict(changes)
    result.update({"stage": stage, "status": status, "events": events})
    return cast(CaseWorkflowState, result)


def _outcome(result: Mapping[str, Any]) -> CaseWorkflowOutcome:
    raw_interrupts = result.get("__interrupt__", ())
    interrupts: list[dict[str, Any]] = []
    for item in raw_interrupts if isinstance(raw_interrupts, Sequence) else ():
        value = item.value if isinstance(item, Interrupt) else item
        if isinstance(value, Mapping):
            interrupts.append(dict(value))
        else:
            interrupts.append({"type": "input_required", "message": str(value)})
    state = cast(
        CaseWorkflowState,
        {key: value for key, value in result.items() if key != "__interrupt__"},
    )
    if interrupts:
        events = list(state.get("events", []))
        if not events or events[-1]["event_type"] != "workflow_interrupted":
            sequence = _next_event_sequence(events)
            events.append(
                WorkflowEvent(
                    event_id=(
                        f"{state['workflow_run_id']}:{sequence:03d}:workflow_interrupted"
                    ),
                    event_type="workflow_interrupted",
                    stage=state.get("stage", "collect_missing_facts"),
                    status="waiting_for_user",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    details={
                        "action_type": str(interrupts[0].get("type", "input_required")),
                        "field": str(interrupts[0].get("field", "")),
                    },
                )
            )
        state = cast(
            CaseWorkflowState,
            {
                **state,
                "status": "waiting_for_user",
                "pending_action": interrupts[0],
                "events": events,
            },
        )
    return CaseWorkflowOutcome(state=state, interrupts=tuple(interrupts))


def _next_event_sequence(
    events: Sequence[WorkflowEvent], *, resuming: bool = False
) -> int:
    """Account for interrupt events emitted outside LangGraph checkpoint state."""
    completed_interrupts = sum(event["event_type"] == "workflow_resumed" for event in events)
    return len(events) + 1 + completed_interrupts + int(resuming)
