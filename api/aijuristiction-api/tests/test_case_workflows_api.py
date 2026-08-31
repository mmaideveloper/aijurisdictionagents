from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any, cast

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pytest import MonkeyPatch
from pypdf import PdfReader

from app.ai_model_admin_api import AdminContext, require_ai_model_admin
from app.case_workflows.models import WorkflowAssignmentRequest, WorkflowAssignmentResponse
from app.case_workflows.service import (
    CaseWorkflowApplicationService,
    ProductionCaseWorkflowServices,
    _normalize_generated_draft,
    get_case_workflow_service,
)
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig
from app.flow_packs.store import FlowPackStore, FlowPackStoreConfig
from app.main import app
from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowRuntime,
    DeterministicCaseWorkflowServices,
)
from aijurisdictionagents.schemas import Document
from aijurisdictionagents.tools import ToolRegistry, build_default_tool_registry
from aijurisdictionagents.tools.base import ToolDefinition, ToolResult

AUTH_HEADERS = {"x-api-key": "aijuris"}
ADMIN_HEADERS = {**AUTH_HEADERS, "x-admin-api-key": "admin-secret"}


def test_generated_draft_preserves_only_missing_verified_facts() -> None:
    result = _normalize_generated_draft(
        "**Potvrdenie** pre Platiteľ A.\nVoliteľné: [doplňte poznámku]",
        verified_facts={
            "payer_identification": "Platiteľ A",
            "amount": "100 EUR",
        },
    )

    assert "[doplňte poznámku]" not in result
    assert "**" not in result
    assert result.count("Platiteľ A") == 1
    assert "- Suma: 100 EUR" in result
    assert "ľudskú kontrolu" in result


def _service(
    tmp_path: Path, *, flow_store: FlowPackStore | None = None
) -> CaseWorkflowApplicationService:
    flow_store = flow_store or FlowPackStore(
        FlowPackStoreConfig(
            db_option="local", db_cloud="", sqlite_path=tmp_path / "flows.sqlite3"
        )
    )
    template_store = DocumentTemplateStore(
        DocumentTemplateStoreConfig(
            db_option="local", db_cloud="", sqlite_path=tmp_path / "templates.sqlite3"
        )
    )
    service = CaseWorkflowApplicationService(
        store=CaseWorkflowStore(
            CaseWorkflowStoreConfig(
                db_option="local", db_cloud="", sqlite_path=tmp_path / "workflows.sqlite3"
            )
        ),
        flow_store=flow_store,
        template_store=template_store,
        runtime=CaseWorkflowRuntime(
            services=DeterministicCaseWorkflowServices(
                legal_requirements=({"content": "Synthetic legal requirement"},),
                legal_source_ids=("synthetic-law-1",),
                tool_definitions=build_default_tool_registry().list_definitions(),
            ),
            checkpointer=InMemorySaver(),
        ),
    )
    service.ensure_default_assignments()
    return service


def test_default_assignment_preserves_legacy_versions_and_selects_consented_tools_v4(
    tmp_path: Path,
) -> None:
    flow_path = tmp_path / "flows.sqlite3"
    config = FlowPackStoreConfig(db_option="local", db_cloud="", sqlite_path=flow_path)
    FlowPackStore(config)
    legacy_definition = {
        "required_facts": ["payer_identification", "recipient_identification", "amount"],
        "outputs": ["payment_confirmation"],
    }
    with sqlite3.connect(flow_path) as connection:
        connection.execute(
            "DELETE FROM flow_packs WHERE flow_key = ? AND version IN (?, ?) AND jurisdiction = ?",
            ("sk.civil.payment_confirmation", 2, 3, "SK"),
        )
        connection.execute(
            "UPDATE flow_packs SET definition_json = ? "
            "WHERE flow_key = ? AND version = ? AND jurisdiction = ?",
            (
                json.dumps(legacy_definition),
                "sk.civil.payment_confirmation",
                1,
                "SK",
            ),
        )

    upgraded_store = FlowPackStore(config)
    service = _service(tmp_path, flow_store=upgraded_store)
    assignment = service.store.get_active_assignment(
        case_type_key="sk.civil.payment_confirmation", jurisdiction="SK"
    )

    assert assignment.graph_version == 3
    assert assignment.flow_version == 4
    assert upgraded_store.get(
        flow_key="sk.civil.payment_confirmation", version=1, jurisdiction="SK"
    ).definition == legacy_definition
    assert isinstance(
        upgraded_store.get(
            flow_key="sk.civil.payment_confirmation", version=3, jurisdiction="SK"
        ).definition.get("mcp_retrieval"),
        dict,
    )


def test_production_retrieval_uses_policy_query_and_excludes_unmapped_identity(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_context(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            document=Document(
                doc_id="synthetic-mcp-law",
                path="synthetic-mcp-law.txt",
                content="Synthetic legal requirement",
            ),
            processing_event={"details": {"document_ids": ["synthetic-law-1"]}},
        )

    monkeypatch.setattr("app.case_workflows.service.build_mcp_law_context", fake_context)
    service = ProductionCaseWorkflowServices(
        api_store=cast(Any, object()), workflow_store=cast(Any, object())
    )
    requirements, source_ids = service.retrieve_legal_requirements(
        cast(
            Any,
            {
                "case_type_key": "sk.civil.payment_confirmation",
                "jurisdiction": "SK",
                "language": "sk-SK",
                "graph_version": 2,
                "verified_facts": {
                    "payment_purpose": "splatenie pôžičky",
                    "payer_identification": "Synthetic Person 12345",
                },
                "flow_definition": {
                    "mcp_retrieval": {
                        "schema_version": 1,
                        "policy_id": "test.payment.requirements.v1",
                        "case_type_keys": ["sk.civil.payment_confirmation"],
                        "jurisdictions": ["SK"],
                        "query_keys": ["payment_confirmation_legal_requirements"],
                        "default_query": "potvrdenie",
                        "fact_query_mappings": {
                            "payment_purpose": {
                                "pôžička": ["pôžička", "splatenie pôžičky"]
                            }
                        },
                        "search_limit": 4,
                        "text_limit": 2,
                    }
                },
            },
        )
    )

    assert captured["query"] == "pôžička"
    assert "Synthetic Person" not in str(captured["query"])
    assert captured["search_limit"] == 4
    assert captured["text_limit"] == 2
    assert requirements[0]["source_id"] == "synthetic-mcp-law"
    assert source_ids == ["synthetic-law-1"]


class _CountingAddressTool:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="registeradries_address_validate",
            purpose="Synthetic address validation",
            input_fields=("address_text",),
        )

    def run(self, **kwargs: Any) -> ToolResult:
        self.calls += 1
        assert kwargs == {"address_text": "Testovacia 1, 811 01 Bratislava"}
        return ToolResult(
            tool_name=self.definition.name,
            ok=True,
            records=({"raw_personal_data": kwargs["address_text"]},),
            message="Synthetic record mapped",
        )


def test_production_tool_execution_requires_ledger_sanitizes_and_is_idempotent(
    tmp_path: Path,
) -> None:
    workflow_store = CaseWorkflowStore(
        CaseWorkflowStoreConfig(
            db_option="local", db_cloud="", sqlite_path=tmp_path / "tool-ledger.sqlite3"
        )
    )
    tool = _CountingAddressTool()
    service = ProductionCaseWorkflowServices(
        api_store=cast(Any, object()),
        workflow_store=workflow_store,
        tool_registry=ToolRegistry(_tools={tool.definition.name: tool}),
    )
    policy = {
        "schema_version": 1,
        "policy_id": "test.address.v1",
        "tools": [
            {
                "name": tool.definition.name,
                "purpose": "Validate a synthetic address",
                "provider": "synthetic-register",
                "consent_scope": "test.address.once",
                "consent_text_version": "workflow-tool-consent-v1",
                "required_fact_keys": ["recipient_identification"],
                "input_mapping": {"address_text": "recipient_identification"},
                "permitted_data_fields": ["recipient_identification"],
                "jurisdictions": ["SK"],
                "timeout_seconds": 5,
            }
        ],
    }
    state = cast(
        Any,
        {
            "workflow_run_id": "synthetic-run-tool-1",
            "correlation_id": "synthetic-correlation-tool-1",
            "case_id": "synthetic-case-tool-1",
            "user_id": "synthetic-user-tool-1",
            "jurisdiction": "SK",
            "flow_key": "test.flow",
            "flow_version": 1,
            "verified_facts": {
                "recipient_identification": "Testovacia 1, 811 01 Bratislava"
            },
            "flow_definition": {"tool_policy": policy},
            "tool_consents": [],
        },
    )
    blocked = service.execute_consented_tools(state, [tool.definition.name])
    assert blocked[0]["status"] == "blocked_missing_policy_bound_consent"
    assert tool.calls == 0
    consent = workflow_store.record_tool_consent(
        state=state,
        tool_name=tool.definition.name,
        granted=True,
        policy={
            "provider": "synthetic-register",
            "purpose": "Validate a synthetic address",
            "consent_scope": "test.address.once",
            "consent_text_version": "workflow-tool-consent-v1",
            "permitted_data_fields": ["recipient_identification"],
        },
    )
    state["tool_consents"] = [consent]

    first = service.execute_consented_tools(state, [tool.definition.name])
    second = service.execute_consented_tools(state, [tool.definition.name])

    assert first == second
    assert first[0]["status"] == "succeeded"
    assert first[0]["record_count"] == 1
    assert "records" not in first[0]
    assert "raw_personal_data" not in str(first[0])
    assert tool.calls == 1


def test_model_tool_selector_receives_only_flow_eligible_definitions(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class _SelectorClient:
        def complete(
            self,
            agent_name: str,
            system_prompt: str,
            conversation: Any,
            documents: Any,
        ) -> str:
            captured["agent_name"] = agent_name
            captured["system_prompt"] = system_prompt
            captured["documents"] = documents
            return '{"selected_tools":["registeradries_address_validate"]}'

    monkeypatch.setattr(
        "app.case_workflows.service.get_routed_llm_client",
        lambda **kwargs: SimpleNamespace(
            client=_SelectorClient(),
            provider="azurefoundry-eu",
            model="synthetic-model-route",
            route_type="default",
        ),
    )
    workflow_store = CaseWorkflowStore(
        CaseWorkflowStoreConfig(
            db_option="local", db_cloud="", sqlite_path=tmp_path / "selector.sqlite3"
        )
    )
    service = ProductionCaseWorkflowServices(
        api_store=cast(Any, object()), workflow_store=workflow_store
    )
    eligible = [
        {
            "name": "registeradries_address_validate",
            "purpose": "Validate a recipient address",
            "provider": "registeradries.sk mapping",
            "input_fields": ["address_text"],
            "required_fact_keys": ["recipient_identification"],
        }
    ]

    selected, metadata = service.propose_optional_tools(
        cast(
            Any,
            {
                "user_id": "synthetic-user",
                "request_text": "Validate the recipient address.",
                "external_provider_acknowledged": True,
            },
        ),
        eligible,
    )

    exposed = json.loads(captured["documents"][0].content)
    assert selected == ["registeradries_address_validate"]
    assert exposed == eligible
    assert "obchodny_register_company_check" not in str(exposed)
    assert metadata["provider"] == "azurefoundry-eu"


def test_every_enabled_slovak_case_type_has_a_valid_active_assignment(tmp_path: Path) -> None:
    service = _service(tmp_path)

    enabled = [
        item
        for item in service.template_store.list_case_types(
            include_deleted=False, jurisdiction="SK"
        )
        if item.is_enabled
    ]
    assert enabled
    for case_type in enabled:
        assignment = service.store.get_active_assignment(
            case_type_key=case_type.case_type_key, jurisdiction="SK"
        )
        status, _ = service.validate_assignment(
            _assignment_payload(assignment)
        )
        assert status == "valid"


def test_api_interrupt_resume_pins_assignment_and_emits_ordered_audit_events(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("JURISDIGTA_ADMIN_API_KEY", "admin-secret")
    service = _service(tmp_path)
    app.dependency_overrides[get_case_workflow_service] = lambda: service
    client = TestClient(app)
    try:
        start = client.post(
            "/v1/case-workflows/runs",
            headers=AUTH_HEADERS,
            json={
                "case_id": "synthetic-case-635",
                "session_id": "synthetic-session-635",
                "user_id": "synthetic-user-635",
                "jurisdiction": "SK",
                "case_type_key": "sk.civil.payment_confirmation",
                "request_text": "Priprav potvrdenie o zaplatení pôžičky.",
                "routing_confidence": 1.0,
                "routing_evidence": ["synthetic exact match"],
                "facts": {},
            },
        )
        assert start.status_code == 201, start.text
        run = start.json()
        assert run["status"] == "waiting_for_user"
        assert run["graph_key"] == "legal_document_workflow"
        assert run["flow_key"] == "sk.civil.payment_confirmation"

        values = ["Platiteľ A", "Príjemca B", "100 EUR", "2026-08-26", "pôžička"]
        for value in values:
            resumed = client.post(
                f"/v1/case-workflows/runs/{run['workflow_run_id']}/resume",
                headers=AUTH_HEADERS,
                json={"user_id": "synthetic-user-635", "value": value},
            )
            assert resumed.status_code == 200, resumed.text
            run = resumed.json()
        assert run["pending_action"]["type"] == "tool_consent"
        consented = client.post(
            f"/v1/case-workflows/runs/{run['workflow_run_id']}/resume",
            headers=AUTH_HEADERS,
            json={"user_id": "synthetic-user-635", "value": "Súhlasím"},
        )
        assert consented.status_code == 200, consented.text
        run = consented.json()
        assert run["status"] == "completed"
        assert run["review_decisions"]["output"] == "passed"
        assert run["review_decisions"]["case"] == "approved"
        artifact_id = run["artifacts"][0]["artifact_id"]
        pdf_response = client.get(
            f"/v1/case-workflows/runs/{run['workflow_run_id']}/artifacts/{artifact_id}/pdf",
            headers=AUTH_HEADERS,
            params={"user_id": "synthetic-user-635"},
        )
        assert pdf_response.status_code == 200
        assert pdf_response.content.startswith(b"%PDF")
        pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_response.content)).pages)
        assert "100 EUR" in pdf_text
        assert "ľudskú kontrolu" in pdf_text

        events_response = client.get(
            f"/v1/case-workflows/runs/{run['workflow_run_id']}/events",
            headers=AUTH_HEADERS,
            params={"user_id": "synthetic-user-635"},
        )
        assert events_response.status_code == 200
        event_types = [item["event_type"] for item in events_response.json()["items"]]
        event_sequences = [
            int(item["event_id"].rsplit(":", 2)[1])
            for item in events_response.json()["items"]
        ]
        assert event_sequences == sorted(set(event_sequences))
        for required in (
            "langgraph_run_started",
            "workflow_assignment_pinned",
            "workflow_interrupted",
            "workflow_resumed",
            "input_validation_completed",
            "output_validation_completed",
            "case_review_completed",
            "langgraph_run_completed",
        ):
            assert required in event_types
        assert event_types.index("workflow_interrupted") < event_types.index("workflow_resumed")
    finally:
        app.dependency_overrides.clear()


def test_assignment_replacement_requires_confirmation_and_admin_key(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("JURISDIGTA_ADMIN_API_KEY", "admin-secret")
    service = _service(tmp_path)
    app.dependency_overrides[get_case_workflow_service] = lambda: service
    client = TestClient(app)
    payload = {
        "case_type_key": "sk.civil.payment_confirmation",
        "jurisdiction": "SK",
        "graph_key": "legal_document_workflow",
        "graph_version": 1,
        "flow_key": "sk.civil.payment_confirmation",
        "flow_version": 1,
        "confirmation": True,
    }
    try:
        forbidden = client.post(
            "/v1/case-workflows/assignments", headers=AUTH_HEADERS, json=payload
        )
        assert forbidden.status_code == 403
        app.dependency_overrides[require_ai_model_admin] = lambda: AdminContext(
            user_id="test-admin", email="admin@example.test"
        )
        without_confirmation = client.post(
            "/v1/case-workflows/assignments",
            headers=ADMIN_HEADERS,
            json={**payload, "confirmation": False},
        )
        assert without_confirmation.status_code == 409
        replacement = client.post(
            "/v1/case-workflows/assignments", headers=ADMIN_HEADERS, json=payload
        )
        assert replacement.status_code == 201
        history = service.store.list_assignments(
            case_type_key="sk.civil.payment_confirmation", jurisdiction="SK"
        )
        assert len(history) == 2
        assert sum(item.is_active for item in history) == 1
    finally:
        app.dependency_overrides.clear()


def _assignment_payload(value: WorkflowAssignmentResponse) -> WorkflowAssignmentRequest:
    return WorkflowAssignmentRequest(
        case_type_key=value.case_type_key,
        jurisdiction=value.jurisdiction,
        graph_key=value.graph_key,
        graph_version=value.graph_version,
        flow_key=value.flow_key,
        flow_version=value.flow_version,
        confirmation=True,
    )
