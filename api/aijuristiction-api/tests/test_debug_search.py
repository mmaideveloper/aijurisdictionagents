from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from fastapi.testclient import TestClient
import pytest

from app.ai_model_admin_api import AdminContext, get_admin_store, require_ai_model_admin
from app.case_workflows.service import get_case_workflow_service
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from app.decision_trace_api import require_decision_trace_admin
from app.main import app
from app.debug_trace import debug_event_sink
from aijurisdictionagents.correlation import CorrelationContext


class OwnerStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.role = "admin"
        self.enabled = True

    def get_case(self, *, case_id: str) -> Any:
        if case_id not in {"case-a", "case-b"}:
            raise KeyError(case_id)
        return SimpleNamespace(case_id=case_id, user_id="user-a" if case_id == "case-a" else "user-b", status="open")

    def find_user_by_id(self, *, user_id: str) -> Any:
        return SimpleNamespace(role=self.role, is_enabled=self.enabled)

    def record_ai_model_admin_audit_event(self, **values: Any) -> None:
        self.events.append(values)


@pytest.fixture
def search_fixture(tmp_path: Path) -> Iterator[tuple[TestClient, CaseWorkflowStore, OwnerStore]]:
    store = CaseWorkflowStore(CaseWorkflowStoreConfig("local", "", tmp_path / "trace.sqlite3"))
    owners = OwnerStore()
    app.dependency_overrides[require_decision_trace_admin] = lambda: AdminContext(user_id="admin", email="admin@example.test")
    app.dependency_overrides[get_admin_store] = lambda: owners
    app.dependency_overrides[get_case_workflow_service] = lambda: SimpleNamespace(store=store)
    with TestClient(app) as client:
        yield client, store, owners
    app.dependency_overrides.clear()


def seed(store: CaseWorkflowStore, owners: Any, *, suffix: str, owner: str = "a") -> None:
    store.record_debug_event(
        correlation_id=f"corr-{suffix}", session_id=f"session-{suffix}", request_id="request",
        parent_request_id="", component="chat", stage="session_created", status="completed",
        payload={"prompt": "PRIVATE MUST NOT APPEAR", "session": {"user_id": "spoofed"}},
    )
    store.register_trace_session(
        correlation_id=f"corr-{suffix}", session_id=f"session-{suffix}", user_id=f"user-{owner}",
        case_id=f"case-{owner}", owner_store=owners,
    )


def get(client: TestClient, **params: Any) -> Any:
    return client.get("/v1/admin/debug", params=params, headers={"x-api-key": "aijuris"})


@pytest.mark.parametrize("field,value", [("user_id", "user-a"), ("case_id", "case-a"),
                                         ("session_id", "session-a"), ("correlation_id", "corr-a")])
def test_each_identifier_and_minimized_audit(search_fixture: Any, field: str, value: str) -> None:
    client, store, owners = search_fixture
    seed(store, owners, suffix="a")
    seed(store, owners, suffix="b", owner="b")
    response = get(client, **{field: value})
    assert response.status_code == 200
    assert [row["correlation_id"] for row in response.json()["items"]] == ["corr-a"]
    assert "PRIVATE" not in response.text and "prompt" not in response.text
    assert set(response.json()["items"][0]) == {"correlation_id", "session_id", "user_id", "case_id", "created_at", "expires_at"}
    audit = owners.events[-1]
    assert audit["action"] == "search_debug_traces"
    assert audit["new_value_summary"]["filter_fields"] == [field]
    assert value not in str(audit["new_value_summary"])


def test_and_filters_multiple_sessions_and_unknown(search_fixture: Any) -> None:
    client, store, owners = search_fixture
    seed(store, owners, suffix="a")
    seed(store, owners, suffix="a2")
    seed(store, owners, suffix="b", owner="b")
    assert len(get(client, user_id="user-a", case_id="case-a").json()["items"]) == 2
    assert get(client, user_id="user-a", case_id="case-b").json()["items"] == []
    assert get(client, session_id="unknown").json()["items"] == []
    assert get(client, correlation_id="corr-a", session_id="session-a2").json()["items"] == []


def test_snapshot_keyset_pagination_and_cursor_binding(search_fixture: Any) -> None:
    client, store, owners = search_fixture
    for suffix in ("a1", "a2", "a3"):
        seed(store, owners, suffix=suffix)
    with store._connect() as conn:
        conn.execute("UPDATE debug_trace_sessions SET created_at = ?", ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),))
        conn.commit()
    first = get(client, user_id="user-a", limit=2).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    seed(store, owners, suffix="later")
    second = get(client, user_id="user-a", limit=2, cursor=first["next_cursor"]).json()
    ids = [row["correlation_id"] for row in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 3 and "corr-later" not in ids
    assert second["next_cursor"] is None
    assert get(client, user_id="user-b", cursor=first["next_cursor"]).status_code == 422
    assert get(client, user_id="user-a", cursor="malformed").status_code == 422


def test_time_bounds_expiry_and_deletion(search_fixture: Any) -> None:
    client, store, owners = search_fixture
    seed(store, owners, suffix="a")
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert get(client, user_id="user-a", end=past).json()["items"] == []
    assert get(client, user_id="user-a", start="2020-01-01T00:00:00Z", end="2020-01-09T00:00:00Z").status_code == 422
    assert get(client, user_id="user-a", start="2020-01-02T00:00:00Z", end="2020-01-01T00:00:00Z").status_code == 422
    assert get(client, user_id="user-a", start="2020-01-01T00:00:00").status_code == 422
    assert get(client, user_id="user-a", end="2099-01-01T00:00:00Z").status_code == 422
    with store._connect() as conn:
        conn.execute("UPDATE debug_trace_sessions SET expires_at = ?", (past,))
        conn.commit()
    assert get(client, user_id="user-a").json()["items"] == []
    seed(store, owners, suffix="fresh")
    store.delete_case_workflows(case_id="case-a", user_id="user-a")
    assert get(client, user_id="user-a").json()["items"] == []
    assert store.list_debug_events(correlation_id="corr-fresh") == []
    seed(store, owners, suffix="session-delete")
    store.delete_session_decision_traces(session_id="session-session-delete")
    assert get(client, user_id="user-a").json()["items"] == []


def test_unverified_and_historical_ownership_stays_unknown(search_fixture: Any) -> None:
    client, store, owners = search_fixture
    seed(store, owners, suffix="a", owner="a")
    store.register_trace_session(correlation_id="spoofed", session_id="spoofed", user_id="user-b", case_id="case-a", owner_store=owners)
    assert get(client, correlation_id="spoofed").json()["items"] == []
    with store._connect() as conn:
        conn.execute("DELETE FROM debug_trace_sessions")
        conn.commit()
    store._initialize()
    historical = get(client, correlation_id="corr-a").json()["items"][0]
    assert historical["user_id"] is None and historical["case_id"] is None
    assert get(client, user_id="user-a").json()["items"] == []


@pytest.mark.parametrize("role,enabled", [("user", True), ("admin", False)])
def test_server_role_blocks_search_details_export(search_fixture: Any, role: str, enabled: bool) -> None:
    client, _, owners = search_fixture
    del app.dependency_overrides[require_decision_trace_admin]
    app.dependency_overrides[require_ai_model_admin] = lambda: AdminContext(user_id="actor", email="actor@example.test")
    owners.role, owners.enabled = role, enabled
    for url in ("/v1/admin/debug?user_id=user-a", "/v1/admin/debug/corr-a", "/v1/admin/debug/corr-a/export"):
        assert client.get(url, headers={"x-api-key": "aijuris"}).status_code == 403
    assert owners.events == []


def test_validation_and_service_failure(search_fixture: Any, monkeypatch: Any) -> None:
    client, store, _ = search_fixture
    assert get(client).status_code == 422
    assert get(client, user_id="*").status_code == 422
    assert get(client, user_id="user-a", limit=101).status_code == 422
    def unavailable(**_: Any) -> Any:
        raise RuntimeError("secret connection string")
    monkeypatch.setattr(store, "search_trace_sessions", unavailable)
    response = get(client, user_id="user-a")
    assert response.status_code == 503 and "secret" not in response.text


def test_chat_capture_resolves_case_owner_without_copying_content(search_fixture: Any, monkeypatch: Any) -> None:
    from app.case_workflows import service

    client, store, owners = search_fixture
    monkeypatch.setattr(service, "get_case_workflow_service", lambda: SimpleNamespace(store=store, api_store=owners))
    debug_event_sink(
        CorrelationContext(correlation_id="captured", session_id="captured-session"),
        "chat", "session_created", "completed",
        {"session": {"case_id": "case-a", "user_id": None}, "prompt": "PRIVATE"},
    )
    response = get(client, user_id="user-a", case_id="case-a")
    assert response.status_code == 200
    assert response.json()["items"][0]["correlation_id"] == "captured"
    assert "PRIVATE" not in response.text
    # Later evidence never renews the metadata retention deadline.
    before = response.json()["items"][0]["expires_at"]
    debug_event_sink(CorrelationContext(correlation_id="captured", session_id="captured-session"),
                     "chat", "reply", "completed", {})
    assert get(client, session_id="captured-session").json()["items"][0]["expires_at"] == before
