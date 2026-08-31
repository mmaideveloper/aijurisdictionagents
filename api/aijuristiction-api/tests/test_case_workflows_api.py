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
            ),
            checkpointer=InMemorySaver(),
        ),
    )
    service.ensure_default_assignments()
    return service


def test_default_assignment_preserves_legacy_versions_and_selects_policy_v3(
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

    assert assignment.graph_version == 2
    assert assignment.flow_version == 3
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
    service = ProductionCaseWorkflowServices(api_store=cast(Any, object()))
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
