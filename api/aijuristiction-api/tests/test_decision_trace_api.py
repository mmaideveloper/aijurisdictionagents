from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn, cast

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.ai_model_admin_api import AdminContext
from app.case_workflows.service import get_case_workflow_service
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from app.main import app
from app.decision_trace_api import require_decision_trace_admin
from aijurisdictionagents.orchestration.case_workflow import (
    CaseWorkflowOutcome,
    CaseWorkflowState,
    WorkflowEvent,
)


AUTH_HEADERS = {"x-api-key": "aijuris"}


def _store_with_trace(tmp_path: Path) -> CaseWorkflowStore:
    store = CaseWorkflowStore(
        CaseWorkflowStoreConfig(
            db_option="local", db_cloud="", sqlite_path=tmp_path / "workflows.sqlite3"
        )
    )
    state = CaseWorkflowState(
        workflow_run_id="run-1",
        correlation_id="correlation-1",
        case_id="case-1",
        session_id="session-1",
        user_id="user-1",
        jurisdiction="SK",
        case_type_key="case-type-1",
        graph_key="graph-1",
        graph_version=1,
        flow_key="flow-1",
        flow_version=1,
        status="completed",
        stage="finalize",
        events=[
            WorkflowEvent(
                event_id="run-1:001:workflow_routed",
                event_type="workflow_routed",
                stage="route",
                status="completed",
                created_at="2026-09-05T00:00:00+00:00",
                details={"reason": "registered_flow_selected"},
            ),
            WorkflowEvent(
                event_id="run-1:002:workflow_finalized",
                event_type="workflow_finalized",
                stage="finalize",
                status="completed",
                created_at="2026-09-05T00:00:01+00:00",
                details={"reason": "all_required_reviews_passed"},
            )
        ],
    )
    store.save_run(assignment_id="assignment-1", outcome=CaseWorkflowOutcome(state, ()))
    return store


def test_admin_can_page_exact_session_timeline(tmp_path: Path) -> None:
    store = _store_with_trace(tmp_path)
    app.dependency_overrides[require_decision_trace_admin] = lambda: AdminContext(
        user_id="admin-1", email="admin@example.test"
    )
    app.dependency_overrides[get_case_workflow_service] = lambda: SimpleNamespace(store=store)
    try:
        response = TestClient(app).get(
            "/v1/admin/chat-sessions/session-1/decision-trace?limit=1",
            headers=AUTH_HEADERS,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["session_id"] == "session-1"
    assert payload["items"][0]["decision"]["reason_code"] == "registered_flow_selected"
    assert payload["next_offset"] == 1

    app.dependency_overrides[require_decision_trace_admin] = lambda: AdminContext(
        user_id="admin-1", email="admin@example.test"
    )
    app.dependency_overrides[get_case_workflow_service] = lambda: SimpleNamespace(store=store)
    try:
        second_page = TestClient(app).get(
            "/v1/admin/chat-sessions/session-1/decision-trace?limit=1&offset=1",
            headers=AUTH_HEADERS,
        )
    finally:
        app.dependency_overrides.clear()
    assert second_page.json()["items"][0]["decision"]["reason_code"] == (
        "all_required_reviews_passed"
    )
    assert second_page.json()["next_offset"] is None


def test_trace_admin_requires_enabled_server_side_admin_role() -> None:
    enabled_admin = SimpleNamespace(role="admin", is_enabled=True)
    regular_user = SimpleNamespace(role="user", is_enabled=True)

    approved = require_decision_trace_admin(
        AdminContext(user_id="admin-1", email="admin@example.test"),
        cast(Any, SimpleNamespace(find_user_by_id=lambda **_: enabled_admin)),
    )
    assert approved.user_id == "admin-1"
    with pytest.raises(HTTPException) as exc_info:
        require_decision_trace_admin(
            AdminContext(user_id="user-1", email="user@example.test"),
            cast(Any, SimpleNamespace(find_user_by_id=lambda **_: regular_user)),
        )
    assert exc_info.value.status_code == 403


def test_non_admin_receives_same_403_before_session_lookup(tmp_path: Path) -> None:
    store = _store_with_trace(tmp_path)

    def deny() -> NoReturn:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required")

    app.dependency_overrides[require_decision_trace_admin] = deny
    app.dependency_overrides[get_case_workflow_service] = lambda: SimpleNamespace(store=store)
    client = TestClient(app)
    try:
        existing = client.get(
            "/v1/admin/chat-sessions/session-1/decision-trace", headers=AUTH_HEADERS
        )
        missing = client.get(
            "/v1/admin/chat-sessions/session-unknown/decision-trace", headers=AUTH_HEADERS
        )
    finally:
        app.dependency_overrides.clear()

    assert existing.status_code == missing.status_code == 403
    assert existing.json() == missing.json()


def test_session_retention_hook_deletes_trace_without_orphans(tmp_path: Path) -> None:
    store = _store_with_trace(tmp_path)

    assert store.delete_session_decision_traces(session_id="session-1") == 2
    items, has_more = store.list_decision_traces(
        session_id="session-1", limit=50, offset=0
    )
    assert items == []
    assert has_more is False
