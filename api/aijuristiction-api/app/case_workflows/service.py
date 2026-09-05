from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from typing import Any, Sequence, cast
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from app.case_types.models import CaseTypeCreateRequest, CaseTypeUpdateRequest
from app.case_workflows.models import (
    WorkflowAssignmentRequest,
    WorkflowAssignmentResponse,
    WorkflowRunResponse,
    WorkflowStartRequest,
)
from app.case_workflows.registry import (
    LEGAL_DOCUMENT_GRAPH_VERSION,
    PRESENTATION_GRAPH_VERSION,
    REGISTERED_GRAPHS,
    VERIFIED_RETRIEVAL_GRAPH_VERSION,
    get_registered_graph,
)
from app.case_workflows.store import CaseWorkflowStore, WorkflowAssignmentNotFoundError
from app.chat.mcp_law_context import build_mcp_law_context
from app.document_templates.store import (
    CaseTypeNotFoundError,
    DocumentTemplateNotFoundError,
    DocumentTemplateStore,
    get_document_template_store,
)
from app.document_templates.catalog import render_template
from app.document_templates.models import (
    DocumentTemplateCreateRequest,
    DocumentTemplateDefinition,
    TemplateSourceReference,
)
from app.flow_packs.store import FlowPackNotFoundError, FlowPackStore
from aijurisdictionagents.agents import (
    AICaseTypeDetectionAgent,
    CaseTypeCandidate,
    create_lawyer_agent,
)
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.correlation import record_debug_event
from aijurisdictionagents.llm.routing import get_routed_llm_client
from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    CaseWorkflowState,
    ReviewDisposition,
    build_initial_case_workflow_state,
)
from aijurisdictionagents.orchestration.primary_router import (
    PrimaryClassification,
    PrimaryLangGraphRouter,
    PrimaryRouteCandidate,
    PrimaryRouteDecision,
)
from aijurisdictionagents.orchestration.presentation import presentation_result_shape
from aijurisdictionagents.orchestration.presentation import (
    PresentationPolicyError,
    validate_presentation_policy,
)
from aijurisdictionagents.orchestration.retrieval_policy import (
    McpRetrievalPolicyError,
    build_mcp_retrieval_request,
    validate_mcp_retrieval_policy,
)
from aijurisdictionagents.orchestration.tool_policy import (
    ToolPolicyError,
    build_tool_inputs,
    get_tool_policy,
    validate_tool_policy,
)
from aijurisdictionagents.schemas import Document, Message
from aijurisdictionagents.tools import ToolRegistry, build_default_tool_registry
from aijurisdictionagents.tools.base import ToolDefinition


class WorkflowConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PrimaryChatRouteResult:
    decision: PrimaryRouteDecision
    workflow_run: WorkflowRunResponse | None = None


class ProductionCaseWorkflowServices:
    def __init__(
        self,
        *,
        api_store: ApiDatabaseStore,
        workflow_store: CaseWorkflowStore,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._api_store = api_store
        self._workflow_store = workflow_store
        self._tool_registry = tool_registry or build_default_tool_registry()

    def available_tool_definitions(self) -> Sequence[ToolDefinition]:
        return cast(Sequence[ToolDefinition], self._tool_registry.list_definitions())

    def propose_optional_tools(
        self, state: CaseWorkflowState, eligible_tools: Sequence[dict[str, Any]]
    ) -> tuple[list[str], dict[str, str]]:
        if not eligible_tools:
            return [], {"status": "no_eligible_tools", "provider": "", "model": ""}
        try:
            route = get_routed_llm_client(
                store=self._api_store,
                user_id=state.get("user_id", ""),
                task_type="tool_selection",
                external_acknowledged=bool(
                    state.get("external_provider_acknowledged", False)
                ),
            )
            raw = route.client.complete(
                "AIToolSelectionAgent",
                (
                    "Select the narrowest useful optional verification tool for the user's request. "
                    "Use only the supplied eligible definitions. A proposal is not authorization. "
                    "Return JSON only: {\"selected_tools\": [\"tool_name\"]} or an empty list. "
                    "Select at most one tool and do not infer or reproduce personal data."
                ),
                [
                    Message(
                        role="user",
                        agent_name="User",
                        content=state.get("request_text", ""),
                    )
                ],
                [
                    Document(
                        doc_id="eligible-workflow-tools",
                        path="eligible-workflow-tools.json",
                        content=json.dumps(list(eligible_tools), ensure_ascii=False),
                    )
                ],
            )
            payload = json.loads(_extract_json_object(raw))
            raw_selected = payload.get("selected_tools", [])
            selected = (
                [str(item).strip() for item in raw_selected if str(item).strip()]
                if isinstance(raw_selected, list)
                else []
            )
            return selected[:1], {
                "status": "model_proposed",
                "provider": route.provider,
                "model": route.model,
                "route_type": route.route_type,
            }
        except Exception:
            return [], {
                "status": "selector_unavailable_fail_closed",
                "provider": "",
                "model": "",
            }

    def propose_presentation_tool(
        self, state: CaseWorkflowState, eligible_renderers: Sequence[dict[str, Any]]
    ) -> tuple[str | None, dict[str, str]]:
        if not eligible_renderers:
            return None, {"status": "no_eligible_renderers", "provider": "", "model": ""}
        result_shape = presentation_result_shape(
            final_answer=state.get("final_answer", ""),
            tool_results=[
                item for item in state.get("tool_results", []) if isinstance(item, Mapping)
            ],
            artifacts=[
                item for item in state.get("artifacts", []) if isinstance(item, Mapping)
            ],
            status=state.get("status", "running"),
        )
        try:
            route = get_routed_llm_client(
                store=self._api_store,
                user_id=state.get("user_id", ""),
                task_type="tool_selection",
                external_acknowledged=bool(
                    state.get("external_provider_acknowledged", False)
                ),
            )
            raw = route.client.complete(
                "AIPresentationSelectionAgent",
                (
                    "Select one presentation renderer from the supplied flow-assigned definitions. "
                    "You receive only the result shape, never result values. Return JSON only: "
                    "{\"renderer_id\": \"assigned_renderer\"}. Do not add data or markup."
                ),
                [
                    Message(
                        role="user",
                        agent_name="User",
                        content=(
                            f"Flow: {state.get('flow_key', '')}; result shape: {result_shape}. "
                            "Choose the clearest assigned renderer."
                        ),
                    )
                ],
                [
                    Document(
                        doc_id="eligible-presentation-tools",
                        path="eligible-presentation-tools.json",
                        content=json.dumps(list(eligible_renderers), ensure_ascii=False),
                    )
                ],
            )
            payload = json.loads(_extract_json_object(raw))
            proposed = str(payload.get("renderer_id", "")).strip() or None
            return proposed, {
                "status": "model_proposed",
                "provider": route.provider,
                "model": route.model,
                "route_type": route.route_type,
            }
        except Exception:
            return None, {
                "status": "selector_unavailable_flow_default",
                "provider": "",
                "model": "",
            }

    def record_tool_consent(
        self,
        state: CaseWorkflowState,
        *,
        tool_name: str,
        granted: bool,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        return self._workflow_store.record_tool_consent(
            state=state,
            tool_name=tool_name,
            granted=granted,
            policy=policy,
        )

    def retrieve_legal_requirements(
        self, state: CaseWorkflowState
    ) -> tuple[list[dict[str, Any]], list[str]]:
        request = build_mcp_retrieval_request(
            policy=state.get("flow_definition", {}).get("mcp_retrieval"),
            case_type_key=state["case_type_key"],
            jurisdiction=state.get("jurisdiction", ""),
            verified_facts=state.get("verified_facts", {}),
            strict=state.get("graph_version", 1) >= VERIFIED_RETRIEVAL_GRAPH_VERSION,
        )
        context = build_mcp_law_context(
            query=request.query,
            country=state.get("jurisdiction", "SK"),
            language=state.get("language", "sk-SK"),
            search_limit=request.search_limit,
            text_limit=request.text_limit,
            force=True,
        )
        if context is None or context.document is None:
            return [], []
        details = context.processing_event.get("details", {})
        citations = details.get("citations", []) if isinstance(details, dict) else []
        source_ids = [
            str(item.get("source_id") or item.get("document_id") or "")
            for item in citations
            if isinstance(item, dict) and (item.get("source_id") or item.get("document_id"))
        ]
        if not source_ids and isinstance(details, dict):
            source_ids = [str(item) for item in details.get("document_ids", []) if str(item)]
        return [
            {
                "source_id": context.document.doc_id,
                "content": context.document.content,
                "retrieval_tool": "JurisDigta MCP",
            }
        ], source_ids

    def execute_consented_tools(
        self, state: CaseWorkflowState, tool_names: Sequence[str]
    ) -> list[dict[str, Any]]:
        policies = validate_tool_policy(
            state.get("flow_definition", {}).get("tool_policy"),
            registry_definitions=self.available_tool_definitions(),
            jurisdiction=state.get("jurisdiction", ""),
            strict=True,
        )
        consent_by_tool = {
            str(item.get("tool_name", "")): item
            for item in state.get("tool_consents", [])
            if isinstance(item, dict)
        }
        results: list[dict[str, Any]] = []
        for tool_name in tool_names:
            policy = get_tool_policy(policies, tool_name)
            consent = consent_by_tool.get(tool_name, {})
            consent_event_id = str(consent.get("consent_event_id", ""))
            ledger = self._workflow_store.get_tool_consent(
                consent_event_id=consent_event_id,
                workflow_run_id=state["workflow_run_id"],
                user_id=state.get("user_id", ""),
            )
            if (
                policy is None
                or ledger is None
                or str(ledger.get("decision")) != "granted"
                or str(ledger.get("tool_name")) != tool_name
                or str(ledger.get("consent_scope")) != policy.consent_scope
                or str(ledger.get("consent_text_version")) != policy.consent_text_version
            ):
                results.append(
                    {
                        "tool_name": tool_name,
                        "status": "blocked_missing_policy_bound_consent",
                        "verified": False,
                    }
                )
                continue
            idempotency_key = f"{state['workflow_run_id']}:{tool_name}:{consent_event_id}"
            existing = self._workflow_store.get_tool_execution(
                idempotency_key=idempotency_key
            )
            if existing is not None:
                results.append(existing)
                continue
            inputs = build_tool_inputs(policy, state.get("verified_facts", {}))
            execution = _run_tool_with_timeout(
                registry=self._tool_registry,
                tool_name=tool_name,
                inputs=inputs,
                timeout_seconds=policy.timeout_seconds,
            )
            summary = {
                "tool_name": tool_name,
                "status": execution["status"],
                "verified": execution["verified"],
                "record_count": execution["record_count"],
                "provider": policy.provider,
                "purpose": policy.purpose,
                "consent_event_id": consent_event_id,
                "consent_text_version": policy.consent_text_version,
                "policy_provenance": f"{state['flow_key']}@{state['flow_version']}",
            }
            results.append(
                self._workflow_store.record_tool_execution(
                    state=state,
                    tool_name=tool_name,
                    consent_event_id=consent_event_id,
                    result_summary=summary,
                )
            )
        return results

    def draft_documents(
        self, state: CaseWorkflowState
    ) -> tuple[str, list[dict[str, Any]]]:
        template_first_draft = _render_template_first_employment_draft(state)
        if template_first_draft is not None:
            answer, template = template_first_draft
            return answer, [_template_draft_artifact(state=state, template=template)]
        route = get_routed_llm_client(
            store=self._api_store,
            user_id=state.get("user_id", ""),
            task_type="document_drafting",
            external_acknowledged=bool(state.get("external_provider_acknowledged", False)),
        )
        lawyer = create_lawyer_agent(route.client, state.get("jurisdiction", "SK"))
        facts = state.get("verified_facts", {})
        fact_text = "\n".join(f"{key}: {value}" for key, value in sorted(facts.items()))
        legal_text = "\n\n".join(
            str(item.get("content", "")) for item in state.get("legal_requirements", [])
        )
        prompt = (
            "Prepare only the requested Slovak legal-document draft from verified facts and the "
            "provided JurisDigta MCP legal requirements. Never invent a missing fact, never expose "
            "hidden reasoning, and clearly mark the result as AI-assisted and subject to human review."
        )
        answer = lawyer.respond(
            conversation=[
                Message(
                    role="user",
                    agent_name="User",
                    content=f"{state['request_text']}\n\nVERIFIED FACTS:\n{fact_text}",
                )
            ],
            documents=[
                Document(
                    doc_id="workflow-mcp-requirements",
                    path="workflow-mcp-requirements.txt",
                    content=legal_text,
                )
            ],
            sources=[],
            system_prompt_override=prompt,
        ).content
        answer = _normalize_generated_draft(answer, verified_facts=facts)
        return answer, [
            {
                "artifact_id": f"{state['workflow_run_id']}:draft",
                "artifact_type": "legal_document_draft",
                "status": "draft",
                "provider": route.provider,
                "model": route.model,
                "route_type": route.route_type,
            }
        ]

    def review_output(self, state: CaseWorkflowState) -> tuple[bool, str]:
        output = state.get("final_answer", "").strip()
        if not output:
            return False, "empty_document_draft"
        if "[" in output or "]" in output:
            return False, "unresolved_placeholder"
        missing_values = [
            key for key, value in state.get("verified_facts", {}).items() if value not in output
        ]
        if missing_values:
            return False, "verified_fact_missing_from_output"
        return True, "verified_facts_preserved"

    def review_safety_and_gdpr(self, state: CaseWorkflowState) -> tuple[bool, str]:
        executed = {str(item.get("tool_name", "")) for item in state.get("tool_results", [])}
        if executed - set(state.get("consented_checks", [])):
            return False, "tool_executed_without_consent"
        if not state.get("legal_source_ids"):
            return False, "legal_provenance_missing"
        return True, "privacy_and_provenance_passed"

    def review_case(self, state: CaseWorkflowState) -> tuple[ReviewDisposition, str]:
        decisions = state.get("review_decisions", {})
        if decisions.get("output") != "passed" or decisions.get("safety_gdpr") != "passed":
            return "human_review_required", "required_review_failed"
        return "approved", "all_required_reviews_passed"


class CaseWorkflowApplicationService:
    def __init__(
        self,
        *,
        store: CaseWorkflowStore,
        flow_store: FlowPackStore,
        template_store: DocumentTemplateStore,
        runtime: CaseWorkflowRuntime,
    ) -> None:
        self.store = store
        self.flow_store = flow_store
        self.template_store = template_store
        self.runtime = runtime

    def validate_assignment(self, payload: WorkflowAssignmentRequest) -> tuple[str, str]:
        graph = get_registered_graph(payload.graph_key, payload.graph_version)
        if graph is None:
            raise WorkflowConfigurationError(
                f"Graph {payload.graph_key}@{payload.graph_version} is not registered"
            )
        try:
            case_type = self.template_store.get_case_type(
                case_type_key=payload.case_type_key,
                jurisdiction=payload.jurisdiction,
            )
        except CaseTypeNotFoundError as exc:
            raise WorkflowConfigurationError(str(exc)) from exc
        if not case_type.is_enabled or case_type.is_deleted:
            raise WorkflowConfigurationError("Case type is not enabled")
        try:
            flow = self.flow_store.get(
                flow_key=payload.flow_key,
                version=payload.flow_version,
                jurisdiction=payload.jurisdiction,
            )
        except FlowPackNotFoundError as exc:
            raise WorkflowConfigurationError(str(exc)) from exc
        if not flow.is_enabled or flow.is_deleted or flow.lifecycle_state != "published":
            raise WorkflowConfigurationError("Flow-pack version is not executable")
        if payload.graph_key == "legal_document_workflow":
            required_facts = flow.definition.get("required_facts")
            if not isinstance(required_facts, list):
                raise WorkflowConfigurationError("Flow pack has no valid required_facts list")
            try:
                validate_mcp_retrieval_policy(
                    flow.definition.get("mcp_retrieval"),
                    case_type_key=payload.case_type_key,
                    jurisdiction=payload.jurisdiction,
                    strict=payload.graph_version >= VERIFIED_RETRIEVAL_GRAPH_VERSION,
                )
            except McpRetrievalPolicyError as exc:
                raise WorkflowConfigurationError(str(exc)) from exc
            try:
                validate_tool_policy(
                    flow.definition.get("tool_policy"),
                    registry_definitions=self.runtime.available_tool_definitions(),
                    jurisdiction=payload.jurisdiction,
                    strict=payload.graph_version >= LEGAL_DOCUMENT_GRAPH_VERSION,
                )
            except ToolPolicyError as exc:
                raise WorkflowConfigurationError(str(exc)) from exc
            try:
                validate_presentation_policy(
                    flow.definition.get("presentation_policy"),
                    strict=payload.graph_version >= PRESENTATION_GRAPH_VERSION,
                )
            except PresentationPolicyError as exc:
                raise WorkflowConfigurationError(str(exc)) from exc
        if payload.graph_key == "unsupported_or_human_review" and bool(
            flow.definition.get("automated_finalization", True)
        ):
            raise WorkflowConfigurationError("Safe fallback flow cannot enable finalization")
        return "valid", "Graph, case type, and immutable flow version are compatible"

    def list_primary_route_candidates(
        self, *, jurisdiction: str
    ) -> tuple[PrimaryRouteCandidate, ...]:
        """Expose only executable dedicated flows to the primary LangGraph router."""
        normalized_jurisdiction = jurisdiction.strip().upper()
        candidates: list[PrimaryRouteCandidate] = []
        for assignment in self.store.list_assignments(jurisdiction=normalized_jurisdiction):
            if (
                not assignment.is_active
                or assignment.validation_status != "valid"
                or assignment.graph_key == "unsupported_or_human_review"
            ):
                continue
            try:
                case_type = self.template_store.get_case_type(
                    case_type_key=assignment.case_type_key,
                    jurisdiction=normalized_jurisdiction,
                )
                flow = self.flow_store.get(
                    flow_key=assignment.flow_key,
                    version=assignment.flow_version,
                    jurisdiction=normalized_jurisdiction,
                )
            except (CaseTypeNotFoundError, FlowPackNotFoundError):
                continue
            if (
                not case_type.is_enabled
                or case_type.is_deleted
                or not flow.is_enabled
                or flow.is_deleted
                or flow.lifecycle_state != "published"
            ):
                continue
            intent = flow.definition.get("intent", {})
            raw_keywords = intent.get("keywords", []) if isinstance(intent, dict) else []
            flow_keywords = (
                tuple(str(item).strip() for item in raw_keywords if str(item).strip())
                if isinstance(raw_keywords, list)
                else ()
            )
            candidates.append(
                PrimaryRouteCandidate(
                    case_type_key=case_type.case_type_key,
                    case_type_name=case_type.name,
                    description=case_type.description or flow.description,
                    keywords=tuple(dict.fromkeys((*case_type.keywords, *flow_keywords))),
                    graph_key=assignment.graph_key,
                    graph_version=assignment.graph_version,
                    flow_key=assignment.flow_key,
                    flow_version=assignment.flow_version,
                )
            )
        return tuple(sorted(candidates, key=lambda item: item.case_type_key))

    def assign(
        self, payload: WorkflowAssignmentRequest, *, actor: str
    ) -> WorkflowAssignmentResponse:
        try:
            existing = self.store.get_active_assignment(
                case_type_key=payload.case_type_key,
                jurisdiction=payload.jurisdiction,
            )
        except WorkflowAssignmentNotFoundError:
            existing = None
        if existing is not None and not payload.confirmation:
            raise WorkflowConfigurationError(
                "Replacing the active assignment requires explicit confirmation"
            )
        status, message = self.validate_assignment(payload)
        return self.store.assign(
            case_type_key=payload.case_type_key,
            jurisdiction=payload.jurisdiction,
            graph_key=payload.graph_key,
            graph_version=payload.graph_version,
            flow_key=payload.flow_key,
            flow_version=payload.flow_version,
            created_by=actor,
            validation_status=status,
            validation_message=message,
        )

    def start(self, payload: WorkflowStartRequest) -> WorkflowRunResponse:
        assignment = self.store.get_active_assignment(
            case_type_key=payload.case_type_key,
            jurisdiction=payload.jurisdiction,
        )
        flow = self.flow_store.get(
            flow_key=assignment.flow_key,
            version=assignment.flow_version,
            jurisdiction=assignment.jurisdiction,
        )
        state = build_initial_case_workflow_state(
            workflow_run_id=str(uuid4()),
            correlation_id=payload.correlation_id.strip() or str(uuid4()),
            case_id=payload.case_id,
            session_id=payload.session_id,
            user_id=payload.user_id,
            jurisdiction=payload.jurisdiction,
            language=payload.language,
            request_text=payload.request_text,
            case_type_key=payload.case_type_key,
            routing_confidence=payload.routing_confidence,
            routing_evidence=payload.routing_evidence,
            graph_key=assignment.graph_key,
            graph_version=assignment.graph_version,
            flow_key=assignment.flow_key,
            flow_version=assignment.flow_version,
            flow_definition=flow.definition,
            facts=payload.facts,
            consented_checks=payload.consented_checks,
            external_provider_acknowledged=payload.external_provider_acknowledged,
            execution_deadline_at=(
                payload.execution_deadline_at.isoformat() if payload.execution_deadline_at else None
            ),
            session_expires_at=(
                payload.session_expires_at.isoformat() if payload.session_expires_at else None
            ),
        )
        outcome = self.runtime.start(state)
        return self.store.save_run(assignment_id=assignment.assignment_id, outcome=outcome)

    def resume(self, workflow_run_id: str, *, user_id: str, value: Any) -> WorkflowRunResponse:
        prior = self.store.get_run_state(workflow_run_id, user_id=user_id)
        outcome = self.runtime.resume(
            graph_key=prior["graph_key"],
            graph_version=prior["graph_version"],
            workflow_run_id=workflow_run_id,
            value=value,
            state=prior,
        )
        run = self.store.get_run(workflow_run_id, user_id=user_id)
        return self.store.save_run(
            assignment_id=run.assignment_id,
            outcome=outcome,
            created_at=run.created_at.isoformat(),
        )

    def cancel(self, workflow_run_id: str, *, user_id: str) -> WorkflowRunResponse:
        prior = self.store.get_run_state(workflow_run_id, user_id=user_id)
        run = self.store.get_run(workflow_run_id, user_id=user_id)
        outcome = self.runtime.terminate(prior, reason="user_cancelled", stage="cancelled")
        return self.store.save_run(
            assignment_id=run.assignment_id,
            outcome=outcome,
            created_at=run.created_at.isoformat(),
        )

    def ensure_default_assignments(self) -> None:
        self._ensure_payment_confirmation_template()
        self._ensure_payment_confirmation_case_type()
        for case_type in self.template_store.list_case_types(
            include_deleted=False, jurisdiction="SK"
        ):
            if not case_type.is_enabled:
                continue
            try:
                existing = self.store.get_active_assignment(
                    case_type_key=case_type.case_type_key,
                    jurisdiction=case_type.jurisdiction,
                )
            except WorkflowAssignmentNotFoundError:
                existing = None
            linked_flow_keys = [
                key for template in case_type.templates for key in template.flow_keys
            ]
            chosen = self._latest_enabled_flow(
                linked_flow_keys, case_type.jurisdiction
            )
            graph_key = "legal_document_workflow" if chosen else "unsupported_or_human_review"
            graph_version = (
                PRESENTATION_GRAPH_VERSION
                if chosen and case_type.case_type_key == "sk.civil.payment_confirmation"
                else 1
            )
            flow_key, flow_version = chosen or ("sk.system.unsupported_or_human_review", 1)
            if existing is not None:
                desired = (
                    existing.graph_key == graph_key
                    and existing.graph_version == graph_version
                    and existing.flow_key == flow_key
                    and existing.flow_version == flow_version
                )
                if desired:
                    continue
                may_upgrade_seed = (
                    case_type.case_type_key == "sk.civil.payment_confirmation"
                    and existing.created_by in {"system_seed", "system_seed_upgrade"}
                )
                if not may_upgrade_seed:
                    continue
            self.assign(
                WorkflowAssignmentRequest(
                    case_type_key=case_type.case_type_key,
                    jurisdiction=case_type.jurisdiction,
                    graph_key=graph_key,
                    graph_version=graph_version,
                    flow_key=flow_key,
                    flow_version=flow_version,
                    confirmation=True,
                ),
                actor="system_seed_upgrade" if existing is not None else "system_seed",
            )

    def _ensure_payment_confirmation_case_type(self) -> None:
        try:
            existing = self.template_store.get_case_type(
                case_type_key="sk.civil.payment_confirmation", jurisdiction="SK"
            )
            if not any(
                item.template_key == "sk.civil.payment_confirmation"
                for item in existing.templates
            ):
                self.template_store.update_case_type(
                    case_type_key=existing.case_type_key,
                    jurisdiction=existing.jurisdiction,
                    payload=CaseTypeUpdateRequest(
                        template_keys=["sk.civil.payment_confirmation"],
                        prompt_text=(
                            existing.prompt.prompt_text
                            if existing.prompt is not None
                            else (
                                "Získaj iba povinné údaje platiteľa, príjemcu, sumy, dátumu "
                                "a účelu platby; zachovaj zdroje a vyžiadaj ľudskú kontrolu."
                            )
                        ),
                    ),
                )
        except CaseTypeNotFoundError:
            self.template_store.create_case_type(
                CaseTypeCreateRequest(
                    case_type_key="sk.civil.payment_confirmation",
                    jurisdiction="SK",
                    language="sk-SK",
                    name="Potvrdenie o zaplatení pôžičky",
                    description="Riadená príprava potvrdenia o zaplatení alebo prijatí platby.",
                    keywords=["potvrdenie o zaplatení", "splatenie pôžičky", "prijatie platby"],
                    prompt_text=(
                        "Získaj iba povinné údaje platiteľa, príjemcu, sumy, dátumu a účelu "
                        "platby. Pred finalizáciou zachovaj zdroje, over údaje a vyžiadaj "
                        "ľudskú kontrolu pri rozpore."
                    ),
                    template_keys=["sk.civil.payment_confirmation"],
                )
            )

    def _ensure_payment_confirmation_template(self) -> None:
        try:
            self.template_store.get(
                template_key="sk.civil.payment_confirmation",
                jurisdiction="SK",
            )
            return
        except KeyError:
            pass
        self.template_store.create(
            DocumentTemplateCreateRequest(
                template_key="sk.civil.payment_confirmation",
                jurisdiction="SK",
                language="sk-SK",
                category="civil",
                title="Potvrdenie o zaplatení pôžičky",
                template_kind="confirmation",
                description=(
                    "Riadená šablóna potvrdenia o prijatí platby; vyžaduje doplnenie "
                    "a overenie všetkých povinných údajov."
                ),
                source_format="HTML",
                source_url="https://static.slov-lex.sk/static/SK/ZZ/1964/40/20240701.html",
                body=(
                    "POTVRDENIE O PRIJATÍ PLATBY\n\n"
                    "Príjemca potvrdzuje, že od platiteľa prijal uvedenú sumu v uvedený "
                    "deň na uvedený účel. Dokument musí obsahovať identifikáciu oboch strán, "
                    "sumu, dátum, účel platby a miesto na podpis príjemcu."
                ),
                keywords=["potvrdenie o zaplatení", "pôžička", "prijatie platby"],
                flow_keys=["sk.civil.payment_confirmation"],
                placeholders=[],
                source_refs=[
                    TemplateSourceReference(
                        label="Občiansky zákonník",
                        url="https://static.slov-lex.sk/static/SK/ZZ/1964/40/20240701.html",
                        publisher="Slov-Lex",
                        source_kind="law",
                        notes="Právne požiadavky sa pri vykonaní obnovujú cez JurisDigta MCP.",
                    )
                ],
                disclaimer_title="Právne upozornenie",
                disclaimer_text=(
                    "Dokument bol pripravený s podporou AI a pred podpisom vyžaduje ľudskú kontrolu."
                ),
                disclaimer_footer="AI-assisted draft – skontrolujte pred použitím.",
            )
        )

    def _latest_enabled_flow(
        self, keys: Sequence[str], jurisdiction: str
    ) -> tuple[str, int] | None:
        for key in keys:
            versions = self.flow_store.list_versions(
                flow_key=key, jurisdiction=jurisdiction, include_deleted=False
            )
            enabled = next((item for item in versions if item.is_enabled), None)
            if enabled is not None and isinstance(enabled.definition.get("mcp_retrieval"), dict):
                return enabled.flow_key, enabled.version
        return None


@lru_cache(maxsize=1)
def get_case_workflow_service() -> CaseWorkflowApplicationService:
    from app.flow_packs.api import get_flow_pack_store

    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    api_store = ApiDatabaseStore.from_env()
    if api_store.uses_postgres:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        pool: Any = ConnectionPool(
            api_store.db_cloud,
            min_size=1,
            max_size=8,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        )
        pool.open(wait=True)
        checkpointer: Any = PostgresSaver(pool)
        checkpointer.setup()
    else:
        checkpointer = InMemorySaver()
    workflow_store = CaseWorkflowStore.from_env()
    runtime = CaseWorkflowRuntime(
        services=ProductionCaseWorkflowServices(
            api_store=api_store,
            workflow_store=workflow_store,
        ),
        checkpointer=cast(Any, checkpointer),
    )
    service = CaseWorkflowApplicationService(
        store=workflow_store,
        flow_store=get_flow_pack_store(),
        template_store=get_document_template_store(),
        runtime=runtime,
    )
    service.ensure_default_assignments()
    return service


def registered_graphs() -> tuple[Any, ...]:
    return REGISTERED_GRAPHS


def handle_chat_workflow_turn(
    *,
    session_id: str,
    case_id: str,
    user_id: str,
    jurisdiction: str,
    language: str,
    case_type_key: str,
    routing_confidence: float,
    request_text: str,
    routing_evidence: Sequence[str] = ("existing_case_catalog_selection",),
    external_provider_acknowledged: bool = False,
    correlation_id: str = "",
) -> WorkflowRunResponse | None:
    mode = os.getenv("AI_CASE_ORCHESTRATION_MODE", "legacy").strip().lower()
    if mode != "active":
        return None
    service = get_case_workflow_service()
    candidates = service.list_primary_route_candidates(jurisdiction=jurisdiction)
    if case_type_key not in {item.case_type_key for item in candidates}:
        return None
    prior = service.store.get_latest_run_for_session(session_id=session_id, user_id=user_id)
    if prior is None and case_id:
        prior = service.store.get_latest_run_for_case(case_id=case_id, user_id=user_id)
    if prior is not None and prior.status == "waiting_for_user":
        return service.resume(prior.workflow_run_id, user_id=user_id, value=request_text)
    if prior is not None and prior.status == "running":
        return prior
    return service.start(
        WorkflowStartRequest(
            case_id=case_id or f"session:{session_id}",
            session_id=session_id,
            user_id=user_id,
            jurisdiction=jurisdiction,
            language=language,
            case_type_key=case_type_key,
            request_text=request_text,
            routing_confidence=routing_confidence,
            routing_evidence=[str(item)[:200] for item in routing_evidence][:10],
            external_provider_acknowledged=external_provider_acknowledged,
            correlation_id=correlation_id,
        )
    )


def route_primary_chat_workflow_turn(
    *,
    session_id: str,
    case_id: str,
    user_id: str,
    jurisdiction: str,
    language: str,
    request_text: str,
    llm_client: Any,
    verified_facts: Mapping[str, str] | None = None,
    external_provider_acknowledged: bool = False,
    correlation_id: str = "",
) -> PrimaryChatRouteResult | None:
    """Run the default chat route through a constrained LangGraph router."""
    if os.getenv("AI_CASE_ORCHESTRATION_MODE", "legacy").strip().lower() != "active":
        return None
    service = get_case_workflow_service()
    prior = service.store.get_latest_run_for_session(session_id=session_id, user_id=user_id)
    if prior is None and case_id:
        prior = service.store.get_latest_run_for_case(case_id=case_id, user_id=user_id)
    if prior is not None and prior.status in {"waiting_for_user", "running"}:
        active_run = handle_chat_workflow_turn(
            session_id=session_id,
            case_id=case_id,
            user_id=user_id,
            jurisdiction=jurisdiction,
            language=language,
            case_type_key=prior.case_type_key,
            routing_confidence=1.0,
            request_text=request_text,
            routing_evidence=("primary_langgraph_router", "active_workflow_resume"),
            external_provider_acknowledged=external_provider_acknowledged,
            correlation_id=correlation_id,
        )
        return PrimaryChatRouteResult(
            decision=PrimaryRouteDecision(
                route="dedicated_flow",
                selected_case_type_key=prior.case_type_key,
                confidence=1.0,
                confidence_gap=1.0,
                clarification_question="",
                evidence=("primary_langgraph_router", "active_workflow_resume"),
            ),
            workflow_run=active_run,
        )

    candidates = service.list_primary_route_candidates(jurisdiction=jurisdiction)
    route_facts = dict(verified_facts or {})
    if not route_facts and prior is not None and prior.case_id == case_id:
        prior_state = service.store.get_run_state(prior.workflow_run_id, user_id=user_id)
        raw_verified = prior_state.get("verified_facts", {})
        if isinstance(raw_verified, dict):
            route_facts = {
                str(key): str(value)
                for key, value in raw_verified.items()
                if str(key).strip() and str(value).strip()
            }

    def classify(
        question: str,
        minimized_facts: Mapping[str, str],
        available: Sequence[PrimaryRouteCandidate],
    ) -> PrimaryClassification:
        result = AICaseTypeDetectionAgent(llm_client).detect(
            request_text=question,
            country=jurisdiction,
            candidates=[
                CaseTypeCandidate(
                    case_type_id=item.case_type_key,
                    case_type_key=item.case_type_key,
                    name=item.case_type_name,
                    description=item.description,
                    keywords=item.keywords,
                    has_prompt=True,
                    template_titles=(item.flow_key,),
                )
                for item in available
            ],
            verified_facts=minimized_facts,
        )
        return PrimaryClassification(
            status=cast(Any, result.status),
            selected_case_type_key=result.selected_case_type_key,
            confidence=result.confidence,
            second_case_type_key=result.second_case_type_key,
            second_confidence=result.second_confidence,
            clarification_question=result.clarification_question,
            rationale=result.rationale,
        )

    decision = PrimaryLangGraphRouter(classifier=classify).route(
        question=request_text,
        verified_facts=route_facts,
        candidates=candidates,
    )
    record_debug_event(
        "langgraph", "primary_router", "completed",
        {
            "route": decision.route,
            "selected_case_type_key": decision.selected_case_type_key,
            "confidence": decision.confidence,
            "confidence_gap": decision.confidence_gap,
            "evidence": list(decision.evidence),
        },
    )
    selected_run: WorkflowRunResponse | None = None
    if decision.route == "dedicated_flow" and decision.selected_case_type_key:
        selected_run = handle_chat_workflow_turn(
            session_id=session_id,
            case_id=case_id,
            user_id=user_id,
            jurisdiction=jurisdiction,
            language=language,
            case_type_key=decision.selected_case_type_key,
            routing_confidence=decision.confidence,
            request_text=request_text,
            routing_evidence=decision.evidence,
            external_provider_acknowledged=external_provider_acknowledged,
            correlation_id=correlation_id,
        )
        if selected_run is None:
            decision = PrimaryRouteDecision(
                route="generic",
                selected_case_type_key=None,
                confidence=decision.confidence,
                confidence_gap=decision.confidence_gap,
                clarification_question="",
                evidence=("primary_langgraph_router", "dedicated_flow_unavailable_fail_closed"),
            )
    if decision.route == "clarification" and not decision.clarification_question:
        decision = PrimaryRouteDecision(
            route="clarification",
            selected_case_type_key=None,
            confidence=decision.confidence,
            confidence_gap=decision.confidence_gap,
            clarification_question=(
                "Prosím, spresnite, aký právny výsledok alebo dokument chcete pripraviť."
                if not language.lower().startswith(("en", "de"))
                else "Please clarify which legal outcome or document you want to prepare."
            ),
            evidence=decision.evidence,
        )
    return PrimaryChatRouteResult(decision=decision, workflow_run=selected_run)


def handle_active_chat_workflow_turn(
    *,
    session_id: str,
    case_id: str,
    user_id: str,
    jurisdiction: str,
    language: str,
    request_text: str,
    external_provider_acknowledged: bool = False,
) -> WorkflowRunResponse | None:
    """Backward-compatible active-run resume; new routing uses the primary graph."""
    mode = os.getenv("AI_CASE_ORCHESTRATION_MODE", "legacy").strip().lower()
    if mode != "active":
        return None
    service = get_case_workflow_service()
    prior = service.store.get_latest_run_for_session(session_id=session_id, user_id=user_id)
    if prior is None and case_id:
        prior = service.store.get_latest_run_for_case(case_id=case_id, user_id=user_id)
    if prior is not None and prior.status in {"waiting_for_user", "running"}:
        return handle_chat_workflow_turn(
            session_id=session_id,
            case_id=case_id,
            user_id=user_id,
            jurisdiction=jurisdiction,
            language=language,
            case_type_key=prior.case_type_key,
            routing_confidence=1.0,
            request_text=request_text,
            external_provider_acknowledged=external_provider_acknowledged,
        )
    return None


def _extract_json_object(value: str) -> str:
    content = value.strip()
    start = content.find("{")
    end = content.rfind("}")
    return content[start : end + 1] if start >= 0 and end > start else "{}"


def _run_tool_with_timeout(
    *,
    registry: ToolRegistry,
    tool_name: str,
    inputs: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="workflow-tool")
    future = executor.submit(registry.run, tool_name, **inputs)
    try:
        result = future.result(timeout=timeout_seconds)
        return {
            "status": "succeeded" if result.ok else "failed",
            "verified": bool(result.ok and result.records),
            "record_count": len(result.records),
        }
    except FutureTimeoutError:
        future.cancel()
        return {"status": "timed_out", "verified": False, "record_count": 0}
    except Exception:
        return {"status": "failed", "verified": False, "record_count": 0}
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _normalize_generated_draft(value: str, *, verified_facts: dict[str, str]) -> str:
    """Remove placeholders and preserve every user-verified fact without inference."""
    lines = [line for line in value.splitlines() if "[" not in line and "]" not in line]
    normalized = "\n".join(lines).replace("**", "").replace("__", "").strip()
    missing_facts = [
        (key, fact_value)
        for key, fact_value in sorted(verified_facts.items())
        if fact_value not in normalized
    ]
    if missing_facts:
        labels = {
            "amount": "Suma",
            "payer_identification": "Platiteľ",
            "payment_date": "Dátum platby",
            "payment_purpose": "Účel platby",
            "recipient_identification": "Príjemca",
        }
        verified_section = "\n".join(
            f"- {labels.get(key, key)}: {fact_value}" for key, fact_value in missing_facts
        )
        normalized = (
            f"{normalized}\n\nOverené údaje použité v návrhu:\n{verified_section}"
        ).strip()
    disclosure = "Návrh bol pripravený s podporou AI a pred použitím vyžaduje ľudskú kontrolu."
    if "ľudskú kontrolu" not in normalized.casefold():
        normalized = f"{normalized}\n\n{disclosure}".strip()
    return normalized


def _render_template_first_employment_draft(
    state: CaseWorkflowState,
) -> tuple[str, Any] | None:
    jurisdiction = str(state.get("jurisdiction", "SK")).strip().upper() or "SK"
    language = str(state.get("language", "sk-SK")).strip() or "sk-SK"
    case_type_key = str(state.get("case_type_key", "")).strip()
    request_text = str(state.get("request_text", "")).strip()
    if not _is_template_first_employment_request(
        case_type_key=case_type_key,
        request_text=request_text,
        jurisdiction=jurisdiction,
    ):
        return None
    try:
        template = get_document_template_store().get(
            template_key="sk.employment.employment_contract",
            jurisdiction=jurisdiction,
        )
    except DocumentTemplateNotFoundError:
        return None
    rendered = render_template(
        template=template,
        facts={
            key: str(value).strip()
            for key, value in dict(state.get("verified_facts", {})).items()
            if str(value).strip()
        },
        country=jurisdiction,
        language=language,
    )
    if not rendered.lines or rendered.missing_required_fields:
        return None
    return "\n".join(rendered.lines).strip(), template


def _template_draft_artifact(
    *, state: CaseWorkflowState, template: DocumentTemplateDefinition
) -> dict[str, Any]:
    """Capture a stable, fact-free source snapshot with the final template artifact."""
    return {
        "artifact_id": f"{state['workflow_run_id']}:draft",
        "artifact_type": "legal_document_draft",
        "status": "draft",
        "provider": "managed_template",
        "model": "",
        "route_type": "template_first",
        "template_key": template.template_key,
        "template_version": template.version,
        "template_id": template.template_id,
        "template_lineage_key": template.lineage_key,
        "template_title": template.title,
        "template_source_url": template.source_url,
        "template_source_references": [
            source.model_dump(mode="json") for source in template.source_refs
        ],
        "human_review_required": True,
        "human_review_disclosure": {
            "title": template.disclaimer_title,
            "text": template.disclaimer_text,
            "footer": template.disclaimer_footer,
        },
    }


def _is_template_first_employment_request(
    *,
    case_type_key: str,
    request_text: str,
    jurisdiction: str,
) -> bool:
    if case_type_key == "sk.employment.employment_contract":
        return True
    score, template = get_document_template_store().find_best_match(
        request_text=request_text,
        country=jurisdiction,
        template_kind="employment_contract",
    )
    return bool(score > 0 and template is not None and template.template_key == "sk.employment.employment_contract")


def workflow_user_reply(run: WorkflowRunResponse, *, language: str) -> str:
    sk = not language.lower().startswith(("en", "de"))
    if run.status == "waiting_for_user":
        if run.pending_action.get("type") == "tool_consent":
            provider = str(run.pending_action.get("provider", "external provider"))
            purpose = str(run.pending_action.get("purpose", "optional verification"))
            fields = ", ".join(
                str(item) for item in run.pending_action.get("permitted_data_fields", [])
            )
            return (
                f"LangGraph navrhol voliteľnú kontrolu cez {provider}. Účel: {purpose} "
                f"Údaje: {fields}. Súhlas platí iba pre tento beh. "
                "Odpovedzte presne „Súhlasím“ alebo „Nesúhlasím“."
                if sk
                else (
                    f"LangGraph proposed an optional check through {provider}. Purpose: {purpose} "
                    f"Data: {fields}. Consent applies to this run only. "
                    "Reply exactly 'Yes' or 'No'."
                )
            )
        field = str(run.pending_action.get("field", "required fact"))
        return (
            f"Workflow LangGraph potrebuje doplniť povinný údaj: {field}."
            if sk
            else f"The LangGraph workflow needs the required fact: {field}."
        )
    if run.status == "completed":
        completed_tools = [
            f"{item.get('tool_name')} ({item.get('status')})"
            for item in run.tool_results
            if item.get("tool_name")
        ]
        tool_disclosure = (
            ("\n\nLangGraph vykonal nástroj: " + ", ".join(completed_tools) + ".")
            if completed_tools and sk
            else (
                "\n\nLangGraph executed tool: " + ", ".join(completed_tools) + "."
                if completed_tools
                else ""
            )
        )
        disclosure = (
            "\n\nNávrh bol pripravený s podporou AI, overený nakonfigurovanými kontrolami "
            "a pred právnym použitím vyžaduje ľudskú kontrolu."
            if sk
            else "\n\nThis AI-assisted draft passed the configured checks and requires human review before legal use."
        )
        return f"{run.final_answer}{tool_disclosure}{disclosure}".strip()
    return (
        "Automatizovaný workflow bol bezpečne zastavený a vyžaduje ľudskú kontrolu."
        if sk
        else "The automated workflow stopped safely and requires human review."
    )
