from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.ai_model_admin_api import AdminContext, get_admin_store
from app.case_workflows.service import get_case_workflow_service
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from app.decision_trace_api import require_decision_trace_admin
from app.main import app
from app.observability import AzureApplicationInsightsLogService, ObservabilityConfigurationError


AUTH_HEADERS = {"x-api-key": "aijuris"}


class _AuditStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_ai_model_admin_audit_event(self, **values: Any) -> None:
        self.events.append(values)


def _store(tmp_path: Path) -> CaseWorkflowStore:
    return CaseWorkflowStore(
        CaseWorkflowStoreConfig(
            db_option="local", db_cloud="", sqlite_path=tmp_path / "workflows.sqlite3"
        )
    )


def test_debug_event_is_session_scoped_and_redacts_credentials(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_debug_event(
        correlation_id="corr-303",
        session_id="session-303",
        request_id="request-2",
        parent_request_id="request-1",
        component="model",
        stage="completion",
        status="completed",
        payload={
            "prompt": "Troubleshooting-relevant user content",
            "authorization": "Bearer must-not-export",
            "nested": {"api_key": "must-not-export"},
            "token_count": 321,
            "error": "Request used Bearer abc.def.ghi and sk-proj-1234567890abcdef",
        },
    )

    events = store.list_debug_events(correlation_id="corr-303")

    assert len(events) == 1
    assert events[0]["session_id"] == "session-303"
    assert events[0]["parent_request_id"] == "request-1"
    assert events[0]["payload"]["prompt"] == "Troubleshooting-relevant user content"
    assert events[0]["payload"]["authorization"] == "[REDACTED]"
    assert events[0]["payload"]["nested"]["api_key"] == "[REDACTED]"
    assert events[0]["payload"]["token_count"] == 321
    assert events[0]["payload"]["error"] == (
        "Request used Bearer [REDACTED] and [REDACTED_API_KEY]"
    )
    assert store.list_debug_events(correlation_id="another-session") == []


def test_retention_purge_physically_deletes_expired_debug_rows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_debug_event(
        correlation_id="corr-expired-303",
        session_id="session-303",
        request_id="request-303",
        parent_request_id="",
        component="api",
        stage="request",
        status="completed",
        payload={},
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE session_debug_events SET expires_at = ? WHERE correlation_id = ?",
            ("2020-01-01T00:00:00+00:00", "corr-expired-303"),
        )
        conn.commit()

    assert store.purge_expired_debug_events() == 1
    assert store.list_debug_events(correlation_id="corr-expired-303") == []


def test_admin_can_view_and_export_exact_correlation_trace(
    tmp_path: Path, monkeypatch: Any
) -> None:
    store = _store(tmp_path)
    store.record_debug_event(
        correlation_id="corr-export-303",
        session_id="session-303",
        request_id="request-303",
        parent_request_id="",
        component="api",
        stage="request",
        status="completed",
        payload={"path": "/v1/chat/sessions"},
    )
    audit_store = _AuditStore()

    def unavailable() -> Any:
        raise ObservabilityConfigurationError("Application Insights is not configured")

    monkeypatch.setattr(AzureApplicationInsightsLogService, "from_env", unavailable)
    app.dependency_overrides[require_decision_trace_admin] = lambda: AdminContext(
        user_id="admin-1", email="admin@example.test"
    )
    app.dependency_overrides[get_case_workflow_service] = lambda: SimpleNamespace(store=store)
    app.dependency_overrides[get_admin_store] = lambda: audit_store
    client = TestClient(app)
    try:
        response = client.get("/v1/admin/debug/corr-export-303", headers=AUTH_HEADERS)
        exported = client.get(
            "/v1/admin/debug/corr-export-303/export", headers=AUTH_HEADERS
        )
        missing = client.get("/v1/admin/debug/not-found", headers=AUTH_HEADERS)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["correlation_id"] == "corr-export-303"
    assert response.json()["timeline"][0]["component"] == "api"
    assert response.json()["retention_days"] == 7
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    assert exported.content.startswith(b"PK")
    assert missing.status_code == 404
    assert [event["action"] for event in audit_store.events] == [
        "view_debug_trace",
        "export_debug_trace",
    ]
