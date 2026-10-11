from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.chat import api as chat_api
from app.chat.client_audit import router, get_store, get_case_workflow_service
from app.chat.models import Session
from app.chat.repository import InMemoryChatRepository
from app.case_workflows.store import CaseWorkflowStore, CaseWorkflowStoreConfig
from app.security import require_api_key
from app.causal_trace import build_causal_flow


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    owner = uuid4()
    session = Session(user_id=owner, case_id="synthetic-case", correlation_id="synthetic-correlation")
    repository = InMemoryChatRepository()
    repository.create_session(session)
    monkeypatch.setattr(chat_api, "_repository", repository)
    ledger = CaseWorkflowStore(CaseWorkflowStoreConfig(db_option="local", db_cloud="", sqlite_path=tmp_path / "ledger.sqlite3"))
    request_id = str(uuid4())
    ledger.record_debug_event(correlation_id=session.correlation_id, session_id=str(session.id), request_id=request_id,
        parent_request_id="", component="api", stage="http_request", status="started",
        payload={"path": f"/v1/chat/sessions/{session.id}/stream"})
    case = SimpleNamespace(user_id=str(owner), status="active")
    identity = SimpleNamespace(is_enabled=True)
    store = SimpleNamespace(authenticate_user_device_auth_token=lambda **args: identity if args["user_id"] == str(owner) and args["token"] == "synthetic-device-token" and args["device_id"] == "synthetic-device" else None,
        get_case=lambda **_: case)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: None
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_case_workflow_service] = lambda: SimpleNamespace(store=ledger)
    return SimpleNamespace(client=TestClient(app), session=session, ledger=ledger, case=case, identity=identity,
        headers={"x-jurisdigta-device-id": "synthetic-device", "x-jurisdigta-device-token": "synthetic-device-token"},
        body={"user_id": str(owner), "request_id": request_id, "phase": "stream_completed", "elapsed_ms": 42},
        url=f"/v1/chat/sessions/{session.id}/client-observations")


def test_owned_request_records_bounded_unverified_observation_and_deduplicates(fixture):
    for _ in range(2):
        assert fixture.client.post(fixture.url, json=fixture.body, headers=fixture.headers).status_code == 202
    events = fixture.ledger.list_debug_events(correlation_id=fixture.session.correlation_id)
    reports = [event for event in events if event["component"] == "frontend"]
    assert len(reports) == 1
    assert reports[0]["parent_request_id"] == fixture.body["request_id"]
    assert reports[0]["status"] == "client_reported"
    assert reports[0]["payload"] == {"schema_version": 1, "source": "client_reported_unverified", "elapsed_ms": 42, "target_request_id": fixture.body["request_id"]}
    assert "synthetic-device-token" not in str(events)
    flow = build_causal_flow(events)
    client_node = next(node for node in flow["nodes"] if node["id"] == reports[0]["request_id"])
    assert client_node["parent_link_source"] == "client_reported_unverified"


def test_device_authentication_and_enabled_account_required(fixture):
    assert fixture.client.post(fixture.url, json=fixture.body).status_code == 401
    fixture.identity.is_enabled = False
    assert fixture.client.post(fixture.url, json=fixture.body, headers=fixture.headers).status_code == 401


@pytest.mark.parametrize("change", ["owner", "deleted", "expired", "request"])
def test_unowned_deleted_expired_or_unknown_request_cannot_be_reported(fixture, change):
    if change == "owner":
        fixture.session.user_id = uuid4()
    elif change == "deleted":
        fixture.case.status = "deleted"
    elif change == "expired":
        fixture.session.created_at = datetime.now(timezone.utc) - timedelta(days=8)
    else:
        fixture.body["request_id"] = str(uuid4())
    assert fixture.client.post(fixture.url, json=fixture.body, headers=fixture.headers).status_code == 404
    assert all(event["component"] != "frontend" for event in fixture.ledger.list_debug_events(correlation_id=fixture.session.correlation_id))


@pytest.mark.parametrize("extra", [{"prompt": "private text"}, {"phase": "model_passed"}, {"elapsed_ms": -1}, {"elapsed_ms": True}])
def test_content_arbitrary_phases_and_invalid_timing_are_rejected(fixture, extra):
    assert fixture.client.post(fixture.url, json={**fixture.body, **extra}, headers=fixture.headers).status_code == 422
