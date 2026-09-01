from __future__ import annotations

from functools import lru_cache
import os
from typing import Any, Sequence, cast
import unicodedata
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
    REGISTERED_GRAPHS,
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
from app.document_templates.models import DocumentTemplateCreateRequest, TemplateSourceReference
from app.flow_packs.store import FlowPackNotFoundError, FlowPackStore
from aijurisdictionagents.agents import create_lawyer_agent
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm.routing import get_routed_llm_client
from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    CaseWorkflowState,
    ReviewDisposition,
    build_initial_case_workflow_state,
)
from aijurisdictionagents.orchestration.retrieval_policy import (
    McpRetrievalPolicyError,
    build_mcp_retrieval_request,
    validate_mcp_retrieval_policy,
)
from aijurisdictionagents.schemas import Document, Message


class WorkflowConfigurationError(ValueError):
    pass


class ProductionCaseWorkflowServices:
    def __init__(self, *, api_store: ApiDatabaseStore) -> None:
        self._api_store = api_store

    def retrieve_legal_requirements(
        self, state: CaseWorkflowState
    ) -> tuple[list[dict[str, Any]], list[str]]:
        request = build_mcp_retrieval_request(
            policy=state.get("flow_definition", {}).get("mcp_retrieval"),
            case_type_key=state["case_type_key"],
            jurisdiction=state.get("jurisdiction", ""),
            verified_facts=state.get("verified_facts", {}),
            strict=state.get("graph_version", 1) >= LEGAL_DOCUMENT_GRAPH_VERSION,
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
        del state
        # Personal-data verification remains unavailable until task #389 consent policy is enforced.
        return [
            {"tool_name": name, "status": "disabled_pending_consent_governance", "verified": False}
            for name in tool_names
        ]

    def draft_documents(
        self, state: CaseWorkflowState
    ) -> tuple[str, list[dict[str, Any]]]:
        template_first_draft = _render_template_first_employment_draft(state)
        if template_first_draft is not None:
            answer, template = template_first_draft
            return answer, [
                {
                    "artifact_id": f"{state['workflow_run_id']}:draft",
                    "artifact_type": "legal_document_draft",
                    "status": "draft",
                    "provider": "managed_template",
                    "model": "",
                    "route_type": "template_first",
                    "template_key": template.template_key,
                    "template_version": template.version,
                    "template_title": template.title,
                }
            ]
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
        if not flow.is_enabled or flow.is_deleted:
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
                    strict=payload.graph_version >= LEGAL_DOCUMENT_GRAPH_VERSION,
                )
            except McpRetrievalPolicyError as exc:
                raise WorkflowConfigurationError(str(exc)) from exc
        if payload.graph_key == "unsupported_or_human_review" and bool(
            flow.definition.get("automated_finalization", True)
        ):
            raise WorkflowConfigurationError("Safe fallback flow cannot enable finalization")
        return "valid", "Graph, case type, and immutable flow version are compatible"

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
            correlation_id=str(uuid4()),
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
        )
        run = self.store.get_run(workflow_run_id, user_id=user_id)
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
                LEGAL_DOCUMENT_GRAPH_VERSION
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
    runtime = CaseWorkflowRuntime(
        services=ProductionCaseWorkflowServices(api_store=api_store),
        checkpointer=cast(Any, checkpointer),
    )
    service = CaseWorkflowApplicationService(
        store=CaseWorkflowStore.from_env(),
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
    external_provider_acknowledged: bool = False,
) -> WorkflowRunResponse | None:
    mode = os.getenv("AI_CASE_ORCHESTRATION_MODE", "legacy").strip().lower()
    enabled_case_types = {
        item.strip()
        for item in os.getenv(
            "AI_CASE_ORCHESTRATION_CASE_TYPES", "sk.civil.payment_confirmation"
        ).split(",")
        if item.strip()
    }
    if mode != "active" or case_type_key not in enabled_case_types:
        return None
    service = get_case_workflow_service()
    prior = service.store.get_latest_run_for_session(session_id=session_id, user_id=user_id)
    if prior is None and case_id:
        prior = service.store.get_latest_run_for_case(case_id=case_id, user_id=user_id)
    if prior is not None and prior.status == "waiting_for_user":
        return service.resume(prior.workflow_run_id, user_id=user_id, value=request_text)
    if prior is not None and prior.status in {"running", "completed"}:
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
            routing_evidence=["existing_case_catalog_selection"],
            external_provider_acknowledged=external_provider_acknowledged,
        )
    )


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
    """Resume an active run or deterministically route a new allowlisted chat request."""
    mode = os.getenv("AI_CASE_ORCHESTRATION_MODE", "legacy").strip().lower()
    if mode != "active":
        return None
    enabled_case_types = {
        item.strip()
        for item in os.getenv(
            "AI_CASE_ORCHESTRATION_CASE_TYPES", "sk.civil.payment_confirmation"
        ).split(",")
        if item.strip()
    }
    service = get_case_workflow_service()
    prior = service.store.get_latest_run_for_session(session_id=session_id, user_id=user_id)
    if prior is None and case_id:
        prior = service.store.get_latest_run_for_case(case_id=case_id, user_id=user_id)
    if prior is not None and prior.case_type_key in enabled_case_types:
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
    normalized_request = _canonical_route_text(request_text)
    candidates = [
        item
        for item in service.template_store.list_case_types(
            include_deleted=False, jurisdiction=jurisdiction
        )
        if item.is_enabled and item.case_type_key in enabled_case_types
    ]
    matches = [
        item
        for item in candidates
        if any(
            _canonical_route_text(term) in normalized_request
            for term in (*item.keywords, item.name)
            if _canonical_route_text(term)
        )
    ]
    if len(matches) != 1:
        return None
    case_type = matches[0]
    return handle_chat_workflow_turn(
        session_id=session_id,
        case_id=case_id,
        user_id=user_id,
        jurisdiction=jurisdiction,
        language=language,
        case_type_key=case_type.case_type_key,
        routing_confidence=1.0,
        request_text=request_text,
        external_provider_acknowledged=external_provider_acknowledged,
    )


def _canonical_route_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char)).split()
    )


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
        field = str(run.pending_action.get("field", "required fact"))
        return (
            f"Workflow LangGraph potrebuje doplniť povinný údaj: {field}."
            if sk
            else f"The LangGraph workflow needs the required fact: {field}."
        )
    if run.status == "completed":
        disclosure = (
            "\n\nNávrh bol pripravený s podporou AI, overený nakonfigurovanými kontrolami "
            "a pred právnym použitím vyžaduje ľudskú kontrolu."
            if sk
            else "\n\nThis AI-assisted draft passed the configured checks and requires human review before legal use."
        )
        return f"{run.final_answer}{disclosure}".strip()
    return (
        "Automatizovaný workflow bol bezpečne zastavený a vyžaduje ľudskú kontrolu."
        if sk
        else "The automated workflow stopped safely and requires human review."
    )
