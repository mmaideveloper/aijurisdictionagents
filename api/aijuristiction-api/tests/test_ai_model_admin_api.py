from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai_model_admin_api import get_admin_store, get_ollama_admin_service
from app.cases_api import get_store as get_cases_store
import app.ai_model_admin_api as ai_model_admin_api
from app.main import app
from app.ollama_admin_service import OllamaInstalledModel
from aijurisdictionagents.api_db import ApiDatabaseStore

AUTH_HEADERS = {"x-api-key": "aijuris"}


def _store(tmp_path: Path) -> ApiDatabaseStore:
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blob")
    store.initialize()
    return store


class FakeOllamaAdminService:
    base_url = "http://127.0.0.1:11434"

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.pulled: list[str] = []
        self.removed: list[str] = []

    def list_models(self) -> list[OllamaInstalledModel]:
        if self.unavailable:
            import httpx

            raise httpx.ConnectError("offline")
        return [
            OllamaInstalledModel(
                name="qwen3:1.7b",
                model="qwen3:1.7b",
                modified_at="2026-06-27T10:00:00Z",
                size=17_000_000_000,
                digest="sha256:default",
            ),
            OllamaInstalledModel(
                name="llama3.2:3b",
                model="llama3.2:3b",
                modified_at="2026-06-27T11:00:00Z",
                size=2_000_000_000,
                digest="sha256:unused",
            ),
        ]

    def list_running_model_names(self) -> set[str]:
        return set()

    def pull_model(self, model: str) -> str:
        self.pulled.append(model)
        return model

    def remove_model(self, model: str) -> str:
        self.removed.append(model)
        return model


def test_admin_dashboard_requires_allowlisted_admin_user(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    user = store.create_user(email="user@example.com", password="secret", full_name="Normal User")
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).get(
            "/v1/admin/ai-models",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": user.user_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_dashboard_allows_global_admin_role(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "")
    store = _store(tmp_path)
    admin = store.create_user(email="role-admin@example.com", password="secret", full_name="Role Admin")
    store.update_admin_user(user_id=admin.user_id, role="admin", is_enabled=True)
    app.dependency_overrides[get_admin_store] = lambda: store
    try:
        response = TestClient(app).get(
            "/v1/admin/ai-models",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["admin"]["email"] == "role-admin@example.com"
    assert response.json()["users_page"]["total"] == 1


def test_admin_dashboard_allows_device_token_for_production_web_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ai_model_admin_api, "_is_local_request", lambda request: False)
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "")
    store = _store(tmp_path)
    admin = store.create_user(email="role-admin@example.com", password="secret", full_name="Role Admin")
    store.update_admin_user(user_id=admin.user_id, role="admin", is_enabled=True)
    token = store.issue_device_auth_token(user_id=admin.user_id, device_id="web-device-1")
    app.dependency_overrides[get_admin_store] = lambda: store
    try:
        response = TestClient(app).get(
            "/v1/admin/ai-models",
            headers={
                **AUTH_HEADERS,
                "x-jurisdigta-admin-user-id": admin.user_id,
                "x-jurisdigta-device-id": "web-device-1",
                "x-jurisdigta-device-token": token,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["admin"]["email"] == "role-admin@example.com"


def test_admin_dashboard_rejects_production_user_id_without_device_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ai_model_admin_api, "_is_local_request", lambda request: False)
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "")
    store = _store(tmp_path)
    admin = store.create_user(email="role-admin@example.com", password="secret", full_name="Role Admin")
    store.update_admin_user(user_id=admin.user_id, role="admin", is_enabled=True)
    app.dependency_overrides[get_admin_store] = lambda: store
    try:
        response = TestClient(app).get(
            "/v1/admin/ai-models",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_update_user_role_and_enabled_status(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    target = store.create_user(email="target@example.com", password="secret", full_name="Target User")
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        response = client.patch(
            f"/v1/admin/users/{target.user_id}",
            headers=headers,
            json={"role": "admin", "is_enabled": False, "reason": "Test admin update."},
        )
        sign_in_response = client.post(
            "/v1/users/sign-in",
            headers=AUTH_HEADERS,
            json={"email": "target@example.com", "password": "secret"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["is_enabled"] is False
    assert sign_in_response.status_code == 401


def test_admin_can_search_list_and_soft_delete_expired_user_case(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    target = store.create_user(email="mmatonok@gmail.com", password="secret", full_name="Test User")
    case = store.create_case(user_id=target.user_id, company_id=None, title="Expired free test case")
    expired_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    with store._connect() as conn:
        store._execute(
            conn,
            "UPDATE cases SET created_at = ?, updated_at = ? WHERE case_id = ?",
            (expired_at, expired_at, case.case_id),
        )
        conn.commit()
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_cases_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        search_response = client.get("/v1/admin/cases/users?email=mmatonok", headers=headers)
        list_response = client.get(
            f"/v1/admin/cases/users/{target.user_id}/cases?include_deleted=true",
            headers=headers,
        )
        public_delete_response = client.delete(
            f"/v1/cases/{case.case_id}?user_id={target.user_id}",
            headers=AUTH_HEADERS,
        )
        delete_response = client.request(
            "DELETE",
            f"/v1/admin/cases/{case.case_id}",
            headers=headers,
            json={"user_id": target.user_id, "reason": "Production Free-plan test reset."},
        )
        refreshed_response = client.get(
            f"/v1/admin/cases/users/{target.user_id}/cases?include_deleted=true",
            headers=headers,
        )
        active_count = store.count_active_cases(user_id=target.user_id)
        audit_events = store.list_ai_model_admin_audit_events(limit=5)
    finally:
        app.dependency_overrides.clear()

    assert search_response.status_code == 200
    assert search_response.json()["items"] == [
        {
            "user_id": target.user_id,
            "email": "mmatonok@gmail.com",
            "full_name": "Test User",
            "role": "user",
            "is_enabled": True,
            "created_at": target.created_at,
        }
    ]
    assert list_response.status_code == 200
    listed_case = list_response.json()["cases"][0]
    assert listed_case["case_id"] == case.case_id
    assert listed_case["target_user_email"] == "mmatonok@gmail.com"
    assert "documents" not in listed_case
    assert public_delete_response.status_code == 403
    assert public_delete_response.json()["detail"]["code"] == "case_write_window_expired"
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert delete_response.json()["case"]["status"] == "deleted"
    assert refreshed_response.json()["cases"][0]["status"] == "deleted"
    assert active_count == 0
    assert audit_events[0].action == "case.soft_delete"
    assert audit_events[0].entity_type == "case"
    assert audit_events[0].entity_id == case.case_id
    assert audit_events[0].reason == "Production Free-plan test reset."
    assert "mmatonok@gmail.com" in audit_events[0].old_value_summary
    assert "deleted" in audit_events[0].new_value_summary


def test_admin_case_management_rejects_non_admin(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    user = store.create_user(email="user@example.com", password="secret", full_name="Normal User")
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).get(
            "/v1/admin/cases/users?email=user@example.com",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": user.user_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_case_soft_delete_rejects_user_mismatch_and_missing_reason(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    first = store.create_user(email="first@example.com", password="secret", full_name="First User")
    second = store.create_user(email="second@example.com", password="secret", full_name="Second User")
    case = store.create_case(user_id=first.user_id, company_id=None, title="First case")
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        missing_reason_response = client.request(
            "DELETE",
            f"/v1/admin/cases/{case.case_id}",
            headers=headers,
            json={"user_id": first.user_id, "reason": ""},
        )
        mismatch_response = client.request(
            "DELETE",
            f"/v1/admin/cases/{case.case_id}",
            headers=headers,
            json={"user_id": second.user_id, "reason": "Test reset."},
        )
    finally:
        app.dependency_overrides.clear()

    assert missing_reason_response.status_code == 422
    assert mismatch_response.status_code == 404
    assert store.get_case(case_id=case.case_id).status == "open"


def test_admin_can_manage_models_groups_and_audit_events(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    member = store.create_user(email="member@example.com", password="secret", full_name="Member User")
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        provider_response = client.post(
            "/v1/admin/ai-models/providers",
            headers=headers,
            json={
                "provider_code": "azure_foundry",
                "provider_type": "azurefoundry",
                "display_name": "Azure AI Foundry",
                "base_url": "https://example.openai.azure.com",
                "region": "swedencentral",
                "data_zone": "eu",
                "is_external": True,
                "enabled": True,
                "reason": "Enable paid EU external routing.",
            },
        )
        assert provider_response.status_code == 200
        provider_id = provider_response.json()["provider_id"]

        profile_response = client.post(
            "/v1/admin/ai-models/profiles",
            headers=headers,
            json={
                "provider_id": provider_id,
                "model_code": "gpt-4.1",
                "deployment_name": "jurisdigta-gpt-4-1",
                "input_price_per_1m": 2.0,
                "cached_input_price_per_1m": 0.5,
                "output_price_per_1m": 8.0,
                "billing_currency": "EUR",
                "eu_data_zone_capable": True,
            },
        )
        assert profile_response.status_code == 200
        profile_id = profile_response.json()["model_profile_id"]

        credential_response = client.post(
            f"/v1/admin/ai-models/providers/{provider_id}/credentials",
            headers=headers,
            json={
                "credential_name": "default",
                "secret_type": "api_key",
                "secret_value": "test-secret",
                "enabled": True,
            },
        )
        assert credential_response.status_code == 200

        group_response = client.post(
            "/v1/admin/ai-models/groups",
            headers=headers,
            json={"group_code": "paid_case_review", "display_name": "Paid case review", "priority": 20},
        )
        assert group_response.status_code == 200
        group_id = group_response.json()["model_group_id"]

        member_response = client.post(
            f"/v1/admin/ai-models/groups/{group_id}/members",
            headers=headers,
            json={"user_id": member.user_id},
        )
        assert member_response.status_code == 200
        assert member_response.json()["email"] == "member@example.com"

        policy_response = client.post(
            "/v1/admin/ai-models/policies",
            headers=headers,
            json={
                "task_type": "document_generation",
                "plan_code": "case",
                "model_group_id": group_id,
                "preferred_external_model_profile_id": profile_id,
                "preferred_local_model_profile_id": "local_ollama_default",
                "allow_external": True,
                "require_external_ack": True,
                "require_eu_data_zone": True,
                "priority": 20,
            },
        )
        assert policy_response.status_code == 200

        dashboard_response = client.get("/v1/admin/ai-models", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert dashboard_response.status_code == 200
    payload = dashboard_response.json()
    assert payload["admin"]["email"] == "admin@example.com"
    assert any(item["provider_code"] == "azure_foundry" for item in payload["providers"])
    assert any(item["secret_preview"].endswith("cret") for item in payload["credentials"])
    assert any(item["model_group_id"] == group_id for item in payload["groups"])
    assert any(item["user_id"] == member.user_id for item in payload["memberships"])
    assert len(payload["audit_events"]) >= 4
    assert "case data outside" in payload["compliance_notes"][0]


def test_external_policy_requires_external_model(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).post(
            "/v1/admin/ai-models/policies",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
            json={"task_type": "default", "plan_code": "case", "allow_external": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "preferred_external_model_profile_id" in response.json()["detail"]


def test_admin_can_list_ollama_inventory_with_removal_guards(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    fake_ollama = FakeOllamaAdminService()
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).get(
            "/v1/admin/ai-models/ollama/models",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    models = response.json()["models"]
    default_model = next(item for item in models if item["name"] == "qwen3:1.7b")
    unused_model = next(item for item in models if item["name"] == "llama3.2:3b")
    assert default_model["removable"] is False
    assert any("default" in item.lower() for item in default_model["removal_blockers"])
    assert default_model["configured_profile_ids"] == ["local_ollama_default"]
    assert unused_model["removable"] is True


def test_admin_can_start_ollama_import_job(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    fake_ollama = FakeOllamaAdminService()
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).post(
            "/v1/admin/ai-models/ollama/import",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
            json={"model": "llama3.2:3b", "reason": "Add small fallback model."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["action"] == "pull"
    assert fake_ollama.pulled == ["llama3.2:3b"]


def test_admin_can_start_unused_ollama_remove_job(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    fake_ollama = FakeOllamaAdminService()
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).request(
            "DELETE",
            "/v1/admin/ai-models/ollama/models/llama3.2:3b",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
            json={"reason": "Remove unused model."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["action"] == "remove"
    assert fake_ollama.removed == ["llama3.2:3b"]


def test_admin_cannot_remove_default_ollama_model(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    fake_ollama = FakeOllamaAdminService()
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).request(
            "DELETE",
            "/v1/admin/ai-models/ollama/models/qwen3:1.7b",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
            json={"reason": "Try remove active default."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "blockers" in response.json()["detail"]
    assert fake_ollama.removed == []


def test_ollama_import_rejects_invalid_model_name(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).post(
            "/v1/admin/ai-models/ollama/import",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
            json={"model": "https://example.com/model", "reason": "Invalid source."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Ollama registry tag" in response.json()["detail"]


def test_ollama_inventory_reports_unavailable_service(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: FakeOllamaAdminService(unavailable=True)
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).get(
            "/v1/admin/ai-models/ollama/models",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
