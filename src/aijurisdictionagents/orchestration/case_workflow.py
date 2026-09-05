from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Literal, Protocol, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Interrupt, interrupt

from aijurisdictionagents.tools.base import ToolDefinition

from .retrieval_policy import (
    McpRetrievalPolicyError,
    build_mcp_retrieval_request,
    validate_mcp_retrieval_policy,
)
from .tool_policy import (
    ToolPolicyError,
    eligible_tool_definitions,
    get_tool_policy,
    validate_tool_policy,
)


WorkflowStatus = Literal[
    "running",
    "waiting_for_user",
    "completed",
    "human_review_required",
    "blocked",
]
ReviewDisposition = Literal["approved", "revisions_required", "human_review_required"]
TerminationReason = Literal[
    "quality_approved",
    "human_review_required",
    "revision_budget_exhausted",
    "input_attempts_exhausted",
    "no_progress",
    "privacy_blocked",
    "provenance_missing",
    "user_cancelled",
    "session_expired",
    "deadline_exceeded",
    "operational_failure",
]

TERMINAL_STATUSES = frozenset({"completed", "human_review_required", "blocked"})
DEFAULT_INPUT_ATTEMPT_LIMIT = 3
DEFAULT_QUALITY_REVISION_LIMIT = 3
DEFAULT_TECHNICAL_RETRY_LIMIT = 3
DEFAULT_NO_PROGRESS_LIMIT = 2
DEFAULT_RECURSION_LIMIT = 48
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 900


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
    tool_consents: list[dict[str, Any]]
    tool_selection: dict[str, Any]
    tool_results: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    review_decisions: dict[str, str]
    stage: str
    status: WorkflowStatus
    pending_action: dict[str, Any]
    final_answer: str
    escalation_reason: str
    termination_reason: TerminationReason | Literal[""]
    started_at: str
    execution_deadline_at: str
    session_expires_at: str
    termination_policy: dict[str, int]
    input_attempt_count: int
    quality_revision_count: int
    technical_retry_count: int
    consecutive_no_progress_count: int
    last_failure_category: str
    last_output_fingerprint: str
    retry_count: int
    events: list[WorkflowEvent]


class CaseWorkflowServices(Protocol):
    def available_tool_definitions(self) -> Sequence[ToolDefinition]: ...

    def propose_optional_tools(
        self, state: CaseWorkflowState, eligible_tools: Sequence[dict[str, Any]]
    ) -> tuple[list[str], dict[str, str]]: ...

    def record_tool_consent(
        self,
        state: CaseWorkflowState,
        *,
        tool_name: str,
        granted: bool,
        policy: dict[str, Any],
    ) -> dict[str, Any]: ...

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
    tool_definitions: tuple[ToolDefinition, ...] = ()

    def available_tool_definitions(self) -> Sequence[ToolDefinition]:
        return self.tool_definitions

    def propose_optional_tools(
        self, state: CaseWorkflowState, eligible_tools: Sequence[dict[str, Any]]
    ) -> tuple[list[str], dict[str, str]]:
        del state
        selected = [str(eligible_tools[0]["name"])] if eligible_tools else []
        return selected, {"provider": "deterministic", "model": "deterministic"}

    def record_tool_consent(
        self,
        state: CaseWorkflowState,
        *,
        tool_name: str,
        granted: bool,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "consent_event_id": f"{state['workflow_run_id']}:{tool_name}:consent",
            "tool_name": tool_name,
            "decision": "granted" if granted else "denied",
            "consent_scope": str(policy["consent_scope"]),
            "consent_text_version": str(policy["consent_text_version"]),
        }

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
            ("legal_document_workflow", 3): self._build_legal_document_graph(
                checkpointer,
                verify_before_retrieval=True,
                consented_tool_execution=True,
            ),
            ("unsupported_or_human_review", 1): self._build_unsupported_graph(checkpointer),
        }

    def registered_graphs(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._graphs))

    def available_tool_definitions(self) -> Sequence[ToolDefinition]:
        return self._services.available_tool_definitions()

    def start(self, state: CaseWorkflowState) -> CaseWorkflowOutcome:
        _validate_initial_state(state)
        graph = self._graph(state["graph_key"], state["graph_version"])
        deadline_reason = _deadline_termination_reason(state)
        if deadline_reason:
            return CaseWorkflowOutcome(
                state=_terminate(state, reason=deadline_reason, stage="preflight"), interrupts=()
            )
        config = self._invoke_config(state)
        try:
            result = graph.invoke(state, config=config)
        except GraphRecursionError:
            return self._recursion_failure(graph=graph, config=config, fallback=state)
        return _outcome(result)

    def resume(
        self,
        *,
        graph_key: str,
        graph_version: int,
        workflow_run_id: str,
        value: str | Mapping[str, str],
        state: CaseWorkflowState | None = None,
    ) -> CaseWorkflowOutcome:
        graph = self._graph(graph_key, graph_version)
        if state is None:
            snapshot = graph.get_state({"configurable": {"thread_id": workflow_run_id}})
            state = cast(CaseWorkflowState, dict(snapshot.values))
        if _is_terminal(state):
            return CaseWorkflowOutcome(state=state, interrupts=())
        deadline_reason = _deadline_termination_reason(state)
        if deadline_reason:
            return CaseWorkflowOutcome(
                state=_terminate(state, reason=deadline_reason, stage="resume_preflight"),
                interrupts=(),
            )
        config = self._invoke_config(state)
        try:
            result = graph.invoke(
                Command(resume=dict(value) if isinstance(value, Mapping) else value),
                config=config,
            )
        except GraphRecursionError:
            return self._recursion_failure(graph=graph, config=config, fallback=state)
        return _outcome(result)

    @staticmethod
    def terminate(
        state: CaseWorkflowState, *, reason: TerminationReason, stage: str = "external_control"
    ) -> CaseWorkflowOutcome:
        return CaseWorkflowOutcome(state=_terminate(state, reason=reason, stage=stage), interrupts=())

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

    @staticmethod
    def _invoke_config(state: CaseWorkflowState) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": state["workflow_run_id"]},
            "recursion_limit": _policy_value(
                state, "recursion_limit", DEFAULT_RECURSION_LIMIT, minimum=4, maximum=500
            ),
        }

    @staticmethod
    def _recursion_failure(
        *, graph: Any, config: Mapping[str, Any], fallback: CaseWorkflowState
    ) -> CaseWorkflowOutcome:
        state = fallback
        try:
            snapshot = graph.get_state(config)
            if snapshot.values:
                state = cast(CaseWorkflowState, {**fallback, **dict(snapshot.values)})
        except Exception:  # pragma: no cover - preserve the original controlled failure
            pass
        return CaseWorkflowOutcome(
            state=_terminate(state, reason="operational_failure", stage="recursion_limit"),
            interrupts=(),
        )

    def _build_legal_document_graph(
        self,
        checkpointer: BaseCheckpointSaver[Any],
        *,
        verify_before_retrieval: bool,
        consented_tool_execution: bool = False,
    ) -> Any:
        builder = StateGraph(CaseWorkflowState)
        builder.add_node("route_case_type", self._route_case_type)
        builder.add_node("load_flow_pack", self._load_flow_pack)
        builder.add_node("retrieve_legal_requirements", self._retrieve_legal_requirements)
        builder.add_node("verify_input", self._verify_input)
        builder.add_node("collect_missing_facts", self._collect_missing_facts)
        offer_node = (
            self._offer_consented_tool_verification
            if consented_tool_execution
            else self._offer_optional_verification
        )
        builder.add_node("offer_optional_verification", offer_node)
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
        builder.add_conditional_edges(
            "collect_missing_facts",
            self._after_missing_fact_collection,
            {"verify": "verify_input", "finalize": "finalize_or_escalate"},
        )
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
        try:
            validate_tool_policy(
                definition.get("tool_policy"),
                registry_definitions=self._services.available_tool_definitions(),
                jurisdiction=state.get("jurisdiction", ""),
                strict=state.get("graph_version", 1) >= 3,
            )
        except ToolPolicyError as exc:
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
                termination_reason="provenance_missing",
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
        attempts = state.get("input_attempt_count", 0) + int(not value)
        failure_category = f"missing_fact:{field_name}" if not value else ""
        no_progress = (
            state.get("consecutive_no_progress_count", 0) + 1
            if failure_category and state.get("last_failure_category") == failure_category
            else int(bool(failure_category))
        )
        changes: dict[str, Any] = {
            "facts": facts,
            "input_attempt_count": attempts,
            "consecutive_no_progress_count": no_progress,
            "last_failure_category": failure_category,
        }
        updated_state = cast(CaseWorkflowState, {**state, **changes})
        if attempts >= _policy_value(
            state, "input_attempt_limit", DEFAULT_INPUT_ATTEMPT_LIMIT, minimum=1, maximum=20
        ):
            return _terminate(
                updated_state,
                reason="input_attempts_exhausted",
                stage="collect_missing_facts",
            )
        if no_progress >= _policy_value(
            state, "no_progress_limit", DEFAULT_NO_PROGRESS_LIMIT, minimum=2, maximum=20
        ):
            return _terminate(
                updated_state,
                reason="no_progress",
                stage="collect_missing_facts",
            )
        return _update(
            state,
            stage="collect_missing_facts",
            status="running",
            **changes,
            event_type="workflow_resumed",
            details={"provided_field": field_name, "value_recorded": bool(value)},
        )

    @staticmethod
    def _after_missing_fact_collection(state: CaseWorkflowState) -> str:
        return "finalize" if _is_terminal(state) else "verify"

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

    def _offer_consented_tool_verification(self, state: CaseWorkflowState) -> CaseWorkflowState:
        policies = validate_tool_policy(
            state.get("flow_definition", {}).get("tool_policy"),
            registry_definitions=self._services.available_tool_definitions(),
            jurisdiction=state.get("jurisdiction", ""),
            strict=True,
        )
        eligible = eligible_tool_definitions(
            policies,
            registry_definitions=self._services.available_tool_definitions(),
            verified_facts=state.get("verified_facts", {}),
        )
        selected, selection_metadata = self._services.propose_optional_tools(state, eligible)
        eligible_names = {str(item["name"]) for item in eligible}
        selected_names = [name for name in selected if name in eligible_names][:1]
        if not selected_names:
            return _update(
                state,
                stage="offer_optional_verification",
                status="running",
                offered_checks=[],
                consented_checks=[],
                tool_consents=[],
                tool_selection=selection_metadata,
                event_type="optional_verification_not_selected",
                details={"eligible_count": len(eligible)},
            )

        tool_name = selected_names[0]
        policy = get_tool_policy(policies, tool_name)
        if policy is None:  # defensive: selected_names was constrained above
            raise ToolPolicyError("selected_tool_policy_missing")
        response = interrupt(
            {
                "type": "tool_consent",
                "workflow_run_id": state["workflow_run_id"],
                "tool_name": tool_name,
                "purpose": policy.purpose,
                "provider": policy.provider,
                "permitted_data_fields": list(policy.permitted_data_fields),
                "consent_scope": policy.consent_scope,
                "consent_text_version": policy.consent_text_version,
                "message": (
                    f"Allow {policy.provider} to process the listed verified data for "
                    f"this workflow run only? Reply 'Súhlasím' or 'Nesúhlasím'."
                ),
            }
        )
        granted = _explicit_tool_consent(response, tool_name=tool_name, policy=policy)
        policy_payload = {
            "purpose": policy.purpose,
            "provider": policy.provider,
            "consent_scope": policy.consent_scope,
            "consent_text_version": policy.consent_text_version,
            "permitted_data_fields": list(policy.permitted_data_fields),
        }
        consent = self._services.record_tool_consent(
            state,
            tool_name=tool_name,
            granted=granted,
            policy=policy_payload,
        )
        return _update(
            state,
            stage="offer_optional_verification",
            status="running",
            offered_checks=selected_names,
            consented_checks=selected_names if granted else [],
            tool_consents=[consent],
            tool_selection=selection_metadata,
            event_type="tool_consent_recorded",
            details={
                "tool_name": tool_name,
                "decision": "granted" if granted else "denied",
                "consent_text_version": policy.consent_text_version,
            },
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
            termination_reason="" if passed else "privacy_blocked",
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
        reason = cast(TerminationReason | Literal[""], state.get("termination_reason", ""))
        if not reason:
            if final_status == "completed":
                reason = "quality_approved"
            elif state.get("escalation_reason") == "required_legal_evidence_unavailable":
                reason = "provenance_missing"
            elif final_status == "blocked":
                reason = "operational_failure"
            else:
                reason = "human_review_required"
        return _terminate(state, reason=reason, stage="finalize_or_escalate")

    def _require_human_review(self, state: CaseWorkflowState) -> CaseWorkflowState:
        return _terminate(
            cast(CaseWorkflowState, {**state, "escalation_reason": "case_type_not_automated"}),
            reason="human_review_required",
            stage="require_human_review",
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
    execution_deadline_at: str | None = None,
    session_expires_at: str | None = None,
) -> CaseWorkflowState:
    started_at = datetime.now(timezone.utc)
    policy = _normalized_termination_policy(flow_definition.get("termination_policy"))
    deadline = execution_deadline_at or (
        started_at + timedelta(seconds=policy["execution_timeout_seconds"])
    ).isoformat()
    return CaseWorkflowState(
        schema_version=2,
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
        tool_consents=[],
        tool_selection={},
        artifacts=[],
        review_decisions={},
        stage="created",
        status="running",
        pending_action={},
        final_answer="",
        escalation_reason="",
        termination_reason="",
        started_at=started_at.isoformat(),
        execution_deadline_at=deadline,
        session_expires_at=session_expires_at or "",
        termination_policy=policy,
        input_attempt_count=0,
        quality_revision_count=0,
        technical_retry_count=0,
        consecutive_no_progress_count=0,
        last_failure_category="",
        last_output_fingerprint="",
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


def record_quality_revision_failure(
    state: CaseWorkflowState, *, failure_category: str, output: str
) -> CaseWorkflowState:
    """Apply the reusable bounded/no-progress contract for a reflection failure."""

    category = failure_category.strip()[:100] or "unspecified_quality_failure"
    fingerprint = sha256(output.encode("utf-8")).hexdigest()
    revision_count = state.get("quality_revision_count", 0) + 1
    no_progress = (
        state.get("consecutive_no_progress_count", 0) + 1
        if state.get("last_failure_category") == category
        and state.get("last_output_fingerprint") == fingerprint
        else 1
    )
    updated = cast(
        CaseWorkflowState,
        {
            **state,
            "quality_revision_count": revision_count,
            "consecutive_no_progress_count": no_progress,
            "last_failure_category": category,
            "last_output_fingerprint": fingerprint,
        },
    )
    if category in {"privacy", "consent", "legal_risk", "privacy_or_consent"}:
        return _terminate(updated, reason="privacy_blocked", stage="reflection")
    if category in {"provenance", "provenance_missing"}:
        return _terminate(updated, reason="provenance_missing", stage="reflection")
    if revision_count >= _policy_value(
        state,
        "quality_revision_limit",
        DEFAULT_QUALITY_REVISION_LIMIT,
        minimum=1,
        maximum=20,
    ):
        return _terminate(updated, reason="revision_budget_exhausted", stage="reflection")
    if no_progress >= _policy_value(
        state, "no_progress_limit", DEFAULT_NO_PROGRESS_LIMIT, minimum=2, maximum=20
    ):
        return _terminate(updated, reason="no_progress", stage="reflection")
    delta = _update(
        updated,
        stage="reflection",
        status="running",
        event_type="quality_revision_requested",
        details={"failure_category": category, "quality_revision_count": revision_count},
    )
    return cast(CaseWorkflowState, {**updated, **delta})


def record_technical_retry_failure(
    state: CaseWorkflowState, *, failure_category: str
) -> CaseWorkflowState:
    """Count infrastructure retries separately from quality revisions."""

    category = failure_category.strip()[:100] or "unspecified_operational_failure"
    retry_count = state.get("technical_retry_count", 0) + 1
    updated = cast(
        CaseWorkflowState,
        {
            **state,
            "technical_retry_count": retry_count,
            "retry_count": retry_count,
            "last_failure_category": category,
        },
    )
    if retry_count >= _policy_value(
        state, "technical_retry_limit", DEFAULT_TECHNICAL_RETRY_LIMIT, minimum=0, maximum=20
    ):
        return _terminate(updated, reason="operational_failure", stage="technical_retry")
    delta = _update(
        updated,
        stage="technical_retry",
        status="running",
        event_type="technical_retry_scheduled",
        details={"failure_category": category, "technical_retry_count": retry_count},
    )
    return cast(CaseWorkflowState, {**updated, **delta})


def _normalized_termination_policy(raw: Any) -> dict[str, int]:
    source = raw if isinstance(raw, Mapping) else {}
    defaults = {
        "input_attempt_limit": DEFAULT_INPUT_ATTEMPT_LIMIT,
        "quality_revision_limit": DEFAULT_QUALITY_REVISION_LIMIT,
        "technical_retry_limit": DEFAULT_TECHNICAL_RETRY_LIMIT,
        "no_progress_limit": DEFAULT_NO_PROGRESS_LIMIT,
        "recursion_limit": DEFAULT_RECURSION_LIMIT,
        "execution_timeout_seconds": DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    }
    limits = {
        "input_attempt_limit": (1, 20),
        "quality_revision_limit": (1, 20),
        "technical_retry_limit": (0, 20),
        "no_progress_limit": (2, 20),
        "recursion_limit": (4, 500),
        "execution_timeout_seconds": (1, 86_400),
    }
    normalized: dict[str, int] = {}
    for key, default in defaults.items():
        value = source.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            value = default
        minimum, maximum = limits[key]
        normalized[key] = max(minimum, min(maximum, value))
    return normalized


def _policy_value(
    state: CaseWorkflowState,
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = state.get("termination_policy", {}).get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        value = default
    return max(minimum, min(maximum, value))


def _deadline_termination_reason(state: CaseWorkflowState) -> TerminationReason | None:
    now = datetime.now(timezone.utc)
    for key, reason in (
        ("session_expires_at", "session_expired"),
        ("execution_deadline_at", "deadline_exceeded"),
    ):
        raw = str(state.get(key, "")).strip()
        if not raw:
            continue
        try:
            timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            return "operational_failure"
        if now >= timestamp:
            return cast(TerminationReason, reason)
    return None


def _is_terminal(state: CaseWorkflowState) -> bool:
    return bool(state.get("termination_reason")) and state.get("status") in TERMINAL_STATUSES


def _terminate(
    state: CaseWorkflowState, *, reason: TerminationReason, stage: str
) -> CaseWorkflowState:
    if any(event["event_type"] == "workflow_terminated" for event in state.get("events", [])):
        return state
    if reason == "quality_approved":
        status: WorkflowStatus = "completed"
    elif reason in {"privacy_blocked", "user_cancelled", "session_expired", "deadline_exceeded"}:
        status = "blocked"
    else:
        status = "human_review_required"
    events = list(state.get("events", []))
    events.append(
        WorkflowEvent(
            event_id=f"{state['workflow_run_id']}:999:workflow_terminated",
            event_type="workflow_terminated",
            stage=stage,
            status=status,
            created_at=datetime.now(timezone.utc).isoformat(),
            details={
                "termination_reason": reason,
                "input_attempt_count": state.get("input_attempt_count", 0),
                "quality_revision_count": state.get("quality_revision_count", 0),
                "technical_retry_count": state.get("technical_retry_count", 0),
            },
        )
    )
    return cast(
        CaseWorkflowState,
        {
            **state,
            "stage": stage,
            "status": status,
            "termination_reason": reason,
            "escalation_reason": "" if reason == "quality_approved" else state.get(
                "escalation_reason", ""
            )
            or reason,
            "pending_action": {},
            "events": events,
        },
    )


def _validate_initial_state(state: CaseWorkflowState) -> None:
    required = (
        "workflow_run_id",
        "correlation_id",
        "session_id",
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
    sequence = _next_event_sequence(
        events,
        resuming=event_type in {"workflow_resumed", "tool_consent_recorded"},
    )
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
    completed_interrupts = sum(
        event["event_type"] in {"workflow_resumed", "tool_consent_recorded"}
        for event in events
    )
    return len(events) + 1 + completed_interrupts + int(resuming)


def _explicit_tool_consent(
    response: Any, *, tool_name: str, policy: Any
) -> bool:
    """Accept only an unambiguous, policy-bound affirmative for this run."""

    if isinstance(response, Mapping):
        if str(response.get("tool_name", "")).strip() != tool_name:
            return False
        if (
            str(response.get("consent_text_version", "")).strip()
            != policy.consent_text_version
        ):
            return False
        value = str(response.get("decision", "")).strip().casefold()
    else:
        value = str(response).strip().casefold()
    return value in {"grant", "granted", "consent", "súhlasím", "suhlasim", "yes"}
