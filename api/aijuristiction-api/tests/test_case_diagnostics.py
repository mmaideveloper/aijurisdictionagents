from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.cases_api import get_case_diagnostics_store, get_store
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from app.main import app


def _record(store: CaseWorkflowStore, correlation: str, case: str = "case-a", user: str = "user-a") -> None:
    store.record_debug_event(
        correlation_id=correlation, session_id=f"session-{correlation}", request_id="request-a",
        parent_request_id="", component="chat", stage="session_created", status="completed",
        payload={"session": {"case_id": case, "user_id": user}, "private": "must not be returned"},
    )


def test_saved_reference_is_scoped_and_excludes_expired_sessions(tmp_path: Path) -> None:
    store = CaseWorkflowStore(CaseWorkflowStoreConfig("local", "", tmp_path / "workflow.sqlite3"))
    assert store.latest_case_correlation_id(case_id="case-a", user_id="user-a") == ""
    _record(store, "first")
    _record(store, "latest")
    _record(store, "other-case", case="case-b")
    _record(store, "other-user", user="user-b")
    assert store.latest_case_correlation_id(case_id="case-a", user_id="user-a") == "latest"
    with store._connect() as conn:
        conn.execute("UPDATE session_debug_events SET expires_at = '2000-01-01T00:00:00+00:00'")
        conn.commit()
    assert store.latest_case_correlation_id(case_id="case-a", user_id="user-a") == ""
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM session_debug_events").fetchone()[0] == 0


@pytest.mark.parametrize("case_status,user_id,expected", [
    ("active", "user-a", 200), ("deleted", "user-a", 404), ("active", "user-b", 404),
])
def test_case_diagnostics_returns_only_authorized_reference(
    tmp_path: Path, case_status: str, user_id: str, expected: int,
) -> None:
    store = CaseWorkflowStore(CaseWorkflowStoreConfig("local", "", tmp_path / "workflow.sqlite3"))
    _record(store, "ordinary-chat-reference")
    case_store = SimpleNamespace(get_case=lambda **_: SimpleNamespace(user_id="user-a", status=case_status))
    app.dependency_overrides[get_store] = lambda: case_store
    app.dependency_overrides[get_case_diagnostics_store] = lambda: store
    try:
        client = TestClient(app)
        response = client.get(f"/v1/cases/case-a/diagnostics?user_id={user_id}", headers={"x-api-key": "aijuris"})
        assert response.status_code == expected
        if expected == 200:
            assert response.json() == {"case_id": "case-a", "correlation_id": "ordinary-chat-reference"}
        assert "must not be returned" not in response.text
        assert client.get("/v1/cases/case-a/diagnostics?user_id=user-a").status_code == 401
    finally:
        app.dependency_overrides.pop(get_store, None)
        app.dependency_overrides.pop(get_case_diagnostics_store, None)
