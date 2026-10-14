from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.cases_api import get_store
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.privacy import CONSENT_VERSION, PrivacyCheckedClient, PrivacyControls, PrivacyDenied
from aijurisdictionagents.privacy_retention import cleanup_files, purge_case, require_approved_policy


@pytest.fixture
def subject(tmp_path: Path):
    store = ApiDatabaseStore(db_path=tmp_path / "sqlite/api.db", blob_root=tmp_path / "files")
    store.initialize()
    user = store.create_user(email="privacy@example.test", password="not-exportable", full_name="Synthetic user")
    return store, user, PrivacyControls(store)


def test_current_consent_revocation_and_reused_model_route(subject):
    store, user, controls = subject
    class Client:
        calls = 0
        def complete(self, *args):
            self.calls += 1
            return "synthetic"
    client = Client()
    routed = PrivacyCheckedClient(client, controls, user.user_id, True)
    with pytest.raises(PrivacyDenied, match="consent_required"):
        routed.complete("test", "", [], [])
    with pytest.raises(ValueError):
        controls.consent(user.user_id, "external_models", True, version="obsolete")
    controls.consent(user.user_id, "external_models", True, version=CONSENT_VERSION)
    assert routed.complete("test", "", [], []) == "synthetic"
    controls.consent(user.user_id, "external_models", False, version=CONSENT_VERSION)
    with pytest.raises(PrivacyDenied):
        routed.complete("test", "", [], [])
    assert client.calls == 1
    controls.restrict(user.user_id, True)
    with pytest.raises(PrivacyDenied, match="processing_restricted"):
        store.create_case(user_id=user.user_id, company_id=None, title="restricted")


def test_events_are_immutable_and_contain_no_subject_or_secret(subject):
    store, user, controls = subject
    controls.consent(user.user_id, "marketing", True, version=CONSENT_VERSION)
    with store._connect() as conn:
        rows = conn.execute("SELECT * FROM privacy_compliance_events").fetchall()
        assert user.user_id not in str(rows)
        assert user.email not in str(rows)
        assert "not-exportable" not in str(rows)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE privacy_compliance_events SET outcome = 'revoked'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM privacy_compliance_events")


def test_export_requires_device_auth_and_includes_owned_files_only(subject):
    store, user, controls = subject
    own = store.create_case(user_id=user.user_id, company_id=None, title="Owned synthetic case")
    store.add_case_document(case_id=own.case_id, kind="upload", version=1, original_filename="synthetic.txt", payload=b"owned synthetic bytes")
    other = store.create_user(email="other@example.test", password="other-secret")
    case = store.create_case(user_id=other.user_id, company_id=None, title="Not exported")
    store.add_case_document(case_id=case.case_id, kind="upload", version=1, original_filename="other.txt", payload=b"other-user bytes")
    token = store.issue_device_auth_token(user_id=user.user_id, device_id="synthetic-device")
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        path = f"/v1/privacy/subjects/{user.user_id}/export"
        assert client.get(path, headers={"x-api-key": "aijuris"}).status_code == 401
        headers = {"x-api-key": "aijuris", "x-jurisdigta-device-id": "synthetic-device", "x-jurisdigta-device-token": token}
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        with ZipFile(BytesIO(response.content)) as archive:
            data = json.loads(archive.read("personal-data.json"))
            text = json.dumps(data)
            assert "Owned synthetic case" in text
            assert "Not exported" not in text
            assert "password_hash" not in text
            assert "device_auth_tokens" not in text
            assert archive.read(data["file_manifest"][0]["member"]) == b"owned synthetic bytes"
        assert client.get(f"/v1/privacy/subjects/{other.user_id}/export", headers=headers).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_review_is_not_erasure_and_retention_is_fail_closed(subject):
    store, user, controls = subject
    request = controls.request_erasure(user.user_id, "delete")
    assert controls.review_erasure(request, True) == "approved_pending_execution"
    assert controls.state(user.user_id)["restricted"]
    with pytest.raises(ValueError):
        controls.review_erasure(request, True)
    with pytest.raises(PrivacyDenied):
        require_approved_policy({"approved": False})


def test_purge_removes_rows_then_retries_file_cleanup(subject):
    store, user, controls = subject
    case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic purge")
    doc = store.add_case_document(case_id=case.case_id, kind="upload", version=1, original_filename="synthetic.txt", payload=b"synthetic")
    path = store._resolve_storage_path(store.get_case_document(case_id=case.case_id, doc_id=doc).storage_uri)
    assert purge_case(store, case.case_id, user.user_id)
    assert path.exists()
    assert cleanup_files(store) == {"files_removed": 1, "files_pending": 0}
    assert not path.exists()
    assert not purge_case(store, case.case_id, user.user_id)


def test_sensitive_and_marketing_scopes_are_separate_and_hold_blocks_erasure(subject):
    store, user, controls = subject
    controls.consent(user.user_id, "external_models", True, version=CONSENT_VERSION)
    controls.set_policy(user.user_id, legal_hold=False, sensitive_consent_required=True)
    with pytest.raises(PrivacyDenied, match="sensitive_processing"):
        controls.require_processing(user.user_id, "external_models")
    controls.consent(user.user_id, "sensitive_processing", True, version=CONSENT_VERSION)
    controls.require_processing(user.user_id, "external_models")
    with pytest.raises(PrivacyDenied, match="marketing"):
        controls.require_processing(user.user_id, "marketing")
    request = controls.request_erasure(user.user_id, "anonymize")
    controls.set_policy(user.user_id, legal_hold=True, sensitive_consent_required=True)
    with pytest.raises(PrivacyDenied, match="legal_hold"):
        controls.review_erasure(request, True)
    assert controls.requests(user.user_id)[0]["status"] == "pending_review"


def test_restricted_real_provider_chat_and_pending_erasure_cannot_resume(subject, monkeypatch):
    import app.chat.api as chat_api

    store, user, controls = subject
    case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic restricted case")
    controls.request_erasure(user.user_id, "delete")
    token = store.issue_device_auth_token(user_id=user.user_id, device_id="restricted-test")
    headers = {"x-api-key": "aijuris", "x-jurisdigta-device-id": "restricted-test", "x-jurisdigta-device-token": token}
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setattr(chat_api, "_get_store", lambda: store)
    app.dependency_overrides[get_store] = lambda: store
    try:
        client = TestClient(app)
        response = client.post("/v1/chat/sessions", headers=headers,
                               json={"user_id": user.user_id, "case_id": case.case_id})
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "processing_restricted"
        response = client.put(f"/v1/privacy/subjects/{user.user_id}/restriction", headers=headers,
                              json={"restricted": False})
        assert response.status_code == 409
        assert controls.state(user.user_id)["restricted"]
    finally:
        app.dependency_overrides.clear()


def test_approved_erasure_executes_owned_cleanup_and_keeps_external_work_pending(subject, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    from app.case_workflows.store import CaseWorkflowStore
    from scripts.execute_privacy_request import execute

    store, user, controls = subject
    case = store.create_case(user_id=user.user_id, company_id=None, title="Synthetic erasure")
    doc_id = store.add_case_document(case_id=case.case_id, kind="upload", version=1,
                                    original_filename="synthetic.txt", payload=b"synthetic erasure bytes")
    path = store._resolve_storage_path(store.get_case_document(case_id=case.case_id, doc_id=doc_id).storage_uri)
    token = store.issue_device_auth_token(user_id=user.user_id, device_id="erasure-test")
    controls.consent(user.user_id, "marketing", True, version=CONSENT_VERSION)
    request = controls.request_erasure(user.user_id, "delete")
    with pytest.raises(PrivacyDenied, match="approved_privacy_request_required"):
        execute(request, store)
    controls.review_erasure(request, True)
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("API_CASE_WORKFLOWS_SQLITE_PATH", str(store.db_path.parent / "workflows.sqlite3"))
    workflows = CaseWorkflowStore.from_env()
    monkeypatch.setattr(CaseWorkflowStore, "from_env", classmethod(lambda cls: workflows))
    result = execute(request, store)
    assert result["status"] == "pending_external_cleanup"
    assert result["purged_cases"] == 1
    assert result["files_pending"] == 0
    assert not path.exists()
    assert not store.list_cases(user_id=user.user_id, include_deleted=True)
    erased = store.get_user(user_id=user.user_id)
    assert not erased.is_enabled and erased.email.endswith("@invalid.example")
    assert not controls.has_consent(user.user_id, "marketing")
    assert store.authenticate_user_device_auth_token(user_id=user.user_id, device_id="erasure-test", token=token) is None
    assert controls.requests(user.user_id)[0]["status"] == "pending_external_cleanup"
