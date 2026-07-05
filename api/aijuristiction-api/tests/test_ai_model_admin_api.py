from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

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

    def __init__(self, *, unavailable: bool = False, models: list[OllamaInstalledModel] | None = None) -> None:
        self.unavailable = unavailable
        self.models = models
        self.pulled: list[str] = []
        self.removed: list[str] = []

    def list_models(self) -> list[OllamaInstalledModel]:
        if self.unavailable:
            import httpx

            raise httpx.ConnectError("offline")
        if self.models is not None:
            return self.models
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


def test_admin_can_export_user_case_and_records_audit_event(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    target = store.create_user(email="target@example.com", password="secret", full_name="Target User")
    case = store.create_case(user_id=target.user_id, company_id=None, title="Admin export case")
    store.add_case_message(case_id=case.case_id, role="user", content="Please prepare a document.")
    store.add_case_document(
        case_id=case.case_id,
        kind="generated_document",
        version=1,
        original_filename="document.txt",
        payload=b"Document content",
        uploaded_by_user_id=target.user_id,
    )
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_cases_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        response = client.get(
            f"/v1/admin/cases/{case.case_id}/export"
            f"?user_id={target.user_id}&reason=Golden%20fixture%20review",
            headers=headers,
        )
        audit_events = store.list_ai_model_admin_audit_events(limit=5)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    with ZipFile(BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["exported_by"] == "admin:admin@example.com"
        assert manifest["case_id"] == case.case_id
    assert audit_events[0].action == "case.export"
    assert audit_events[0].entity_type == "case"
    assert audit_events[0].entity_id == case.case_id
    assert audit_events[0].reason == "Golden fixture review"
    assert "target@example.com" in audit_events[0].old_value_summary
    assert "exported" in audit_events[0].new_value_summary


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


def test_admin_can_soft_delete_provider_with_audit_and_routing_fallback(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    target = store.create_user(email="target@example.com", password="secret", full_name="Target User")
    provider = store.upsert_ai_model_provider(
        provider_code="external_delete_test",
        provider_type="openai_compatible",
        display_name="External Delete Test",
        base_url="https://llm.example.test/v1",
        region="eu",
        data_zone="eu",
        is_external=True,
        enabled=True,
    )
    profile = store.upsert_ai_model_profile(
        provider_id=provider.provider_id,
        model_code="external-model",
        deployment_name="external-model",
        eu_data_zone_capable=True,
        enabled=True,
    )
    credential = store.upsert_ai_model_credential(
        provider_id=provider.provider_id,
        credential_name="default",
        secret_type="api_key",
        secret_value="secret-delete-test",
        enabled=True,
    )
    store.upsert_ai_model_user_override(
        user_id=target.user_id,
        model_profile_id=profile.model_profile_id,
        admin_user_id=admin.user_id,
        reason="Assign external provider before delete.",
    )
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        delete_response = client.request(
            "DELETE",
            f"/v1/admin/ai-models/providers/{provider.provider_id}",
            headers=headers,
            json={"reason": "Provider contract ended."},
        )
        dashboard_response = client.get("/v1/admin/ai-models", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert delete_response.status_code == 200
    deleted_provider = delete_response.json()
    assert deleted_provider["provider_id"] == provider.provider_id
    assert deleted_provider["enabled"] is False
    assert deleted_provider["deleted_at"]
    assert deleted_provider["deleted_reason"] == "Provider contract ended."

    providers = store.list_ai_model_providers(include_deleted=True)
    assert any(item.provider_id == provider.provider_id and item.deleted_at for item in providers)
    assert all(item.provider_id != provider.provider_id for item in store.list_ai_model_providers())
    disabled_profile = next(item for item in store.list_ai_model_profiles() if item.model_profile_id == profile.model_profile_id)
    disabled_credential = next(
        item for item in store.list_ai_model_credentials(provider_id=provider.provider_id)
        if item.credential_id == credential.credential_id
    )
    assert disabled_profile.enabled is False
    assert disabled_credential.enabled is False

    route = store.resolve_ai_model_route(user_id=target.user_id, plan_code="free", task_type="default")
    assert route.route_type == "free_local"
    assert route.provider is not None
    assert route.provider.provider_id == "local_ollama"

    payload = dashboard_response.json()
    assert all(item["provider_id"] != provider.provider_id for item in payload["providers"])
    audit_events = store.list_ai_model_admin_audit_events(limit=5)
    assert audit_events[0].action == "provider.soft_delete"
    assert audit_events[0].entity_id == provider.provider_id
    assert "secret-delete-test" not in audit_events[0].old_value_summary
    assert "secret-delete-test" not in audit_events[0].new_value_summary


def test_admin_can_soft_delete_model_admin_records_and_hide_them_from_dashboard(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    provider = store.upsert_ai_model_provider(
        provider_code="external_record_delete_test",
        provider_type="openai_compatible",
        display_name="External Record Delete Test",
        base_url="https://llm.example.test/v1",
        region="eu",
        data_zone="eu",
        is_external=True,
        enabled=True,
    )
    profile = store.upsert_ai_model_profile(
        provider_id=provider.provider_id,
        model_code="record-delete-model",
        deployment_name="record-delete-model",
        eu_data_zone_capable=True,
        enabled=True,
    )
    group = store.upsert_ai_model_group(
        group_code="record_delete_group",
        display_name="Record delete group",
        priority=30,
        enabled=True,
    )
    policy = store.upsert_ai_task_route_policy(
        task_type="record_delete",
        plan_code="case",
        model_group_id=group.model_group_id,
        preferred_external_model_profile_id=profile.model_profile_id,
        preferred_local_model_profile_id="local_ollama_default",
        allow_external=True,
        require_external_ack=True,
        require_eu_data_zone=True,
        priority=30,
        enabled=True,
    )
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        blocked_profile_delete = client.request(
            "DELETE",
            f"/v1/admin/ai-models/profiles/{profile.model_profile_id}",
            headers=headers,
            json={"reason": "Retire profile."},
        )
        policy_delete = client.request(
            "DELETE",
            f"/v1/admin/ai-models/policies/{policy.policy_id}",
            headers=headers,
            json={"reason": "Retire policy."},
        )
        profile_delete = client.request(
            "DELETE",
            f"/v1/admin/ai-models/profiles/{profile.model_profile_id}",
            headers=headers,
            json={"reason": "Retire profile."},
        )
        group_delete = client.request(
            "DELETE",
            f"/v1/admin/ai-models/groups/{group.model_group_id}",
            headers=headers,
            json={"reason": "Retire group."},
        )
        dashboard_response = client.get("/v1/admin/ai-models", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert blocked_profile_delete.status_code == 400
    assert "enabled routing policy" in blocked_profile_delete.json()["detail"]
    assert policy_delete.status_code == 200
    assert policy_delete.json()["deleted_at"]
    assert profile_delete.status_code == 200
    assert profile_delete.json()["deleted_at"]
    assert group_delete.status_code == 200
    assert group_delete.json()["deleted_at"]

    payload = dashboard_response.json()
    assert all(item["policy_id"] != policy.policy_id for item in payload["policies"])
    assert all(item["model_profile_id"] != profile.model_profile_id for item in payload["profiles"])
    assert all(item["model_group_id"] != group.model_group_id for item in payload["groups"])
    audit_actions = [item.action for item in store.list_ai_model_admin_audit_events(limit=10)]
    assert "policy.soft_delete" in audit_actions
    assert "profile.soft_delete" in audit_actions
    assert "group.soft_delete" in audit_actions


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


def test_admin_can_search_assign_update_and_disable_user_model_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    target = store.create_user(email="target@example.com", password="secret", full_name="Target User")
    provider = store.upsert_ai_model_provider(
        provider_code="azure_foundry_override",
        provider_type="azurefoundry",
        display_name="Azure AI Foundry Override",
        base_url="https://example.openai.azure.com",
        region="swedencentral",
        data_zone="eu",
        is_external=True,
    )
    profile = store.upsert_ai_model_profile(
        provider_id=provider.provider_id,
        model_code="gpt-4o-paid",
        deployment_name="jurisdigta-gpt-4o-paid",
        eu_data_zone_capable=True,
    )
    second_profile = store.upsert_ai_model_profile(
        provider_id=provider.provider_id,
        model_code="gpt-4.1-paid",
        deployment_name="jurisdigta-gpt-4-1-paid",
        eu_data_zone_capable=True,
    )
    app.dependency_overrides[get_admin_store] = lambda: store
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        search_response = client.get("/v1/admin/ai-models/users?email=target@example.com", headers=headers)
        create_response = client.put(
            f"/v1/admin/ai-models/users/{target.user_id}/model-override",
            headers=headers,
            json={
                "model_profile_id": profile.model_profile_id,
                "reason": "Assign paid external profile for testing.",
            },
        )
        update_response = client.put(
            f"/v1/admin/ai-models/users/{target.user_id}/model-override",
            headers=headers,
            json={
                "model_profile_id": second_profile.model_profile_id,
                "reason": "Switch to newer paid external profile.",
            },
        )
        delete_response = client.request(
            "DELETE",
            f"/v1/admin/ai-models/users/{target.user_id}/model-override",
            headers=headers,
            json={"reason": "Return to normal routing."},
        )
        non_admin = store.create_user(email="user@example.com", password="secret", full_name="Normal User")
        denied_response = client.get(
            "/v1/admin/ai-models/users?email=target@example.com",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": non_admin.user_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert search_response.status_code == 200
    assert search_response.json()["items"][0]["user_id"] == target.user_id
    assert create_response.status_code == 200
    assert create_response.json()["override"]["model_profile_id"] == profile.model_profile_id
    assert create_response.json()["effective_route"]["route_type"] == "user_override_external"
    assert update_response.status_code == 200
    assert update_response.json()["override"]["model_profile_id"] == second_profile.model_profile_id
    assert delete_response.status_code == 200
    assert delete_response.json()["override"]["enabled"] is False
    assert delete_response.json()["effective_route"]["route_type"] == "free_local"
    assert denied_response.status_code == 403
    audit_actions = [item.action for item in store.list_ai_model_admin_audit_events(limit=10)]
    assert "user_override.create" in audit_actions
    assert "user_override.update" in audit_actions
    assert "user_override.disable" in audit_actions


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
    assert default_model["installed"] is True
    assert any("default" in item.lower() for item in default_model["removal_blockers"])
    assert default_model["configured_profile_ids"] == ["local_ollama_default"]
    assert unused_model["removable"] is True


def test_admin_ollama_inventory_includes_configured_profile_when_runtime_has_no_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    fake_ollama = FakeOllamaAdminService(models=[])
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
    configured_model = next(item for item in models if item["name"] == "qwen3:1.7b")
    assert configured_model["installed"] is False
    assert configured_model["is_default"] is False
    assert configured_model["removable"] is True
    assert configured_model["configured_profile_ids"] == ["local_ollama_default"]
    assert any("not installed" in item.lower() for item in configured_model["removal_blockers"])


def test_admin_ollama_inventory_deduplicates_configured_profile_by_case(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    store.upsert_ai_model_profile(
        model_profile_id="local_ollama_qwen4b",
        provider_id="local_ollama",
        model_code="qwen3:4b",
        deployment_name="Qwen3:4b",
        billing_currency="EUR",
        eu_data_zone_capable=True,
        is_default_for_free=True,
        enabled=True,
    )
    fake_ollama = FakeOllamaAdminService(
        models=[
            OllamaInstalledModel(
                name="qwen3:4b",
                model="qwen3:4b",
                modified_at="2026-07-03T10:00:00Z",
                size=4_000_000_000,
                digest="sha256:qwen4b",
            )
        ]
    )
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
    assert [item["name"] for item in models].count("qwen3:4b") == 1
    assert "Qwen3:4b" not in [item["name"] for item in models]
    qwen_model = next(item for item in models if item["name"] == "qwen3:4b")
    assert qwen_model["installed"] is True
    assert qwen_model["is_default"] is True
    assert qwen_model["configured_profile_ids"] == ["local_ollama_qwen4b"]


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


def test_admin_can_set_ollama_default_and_free_route_uses_new_model(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    free_user = store.create_user(email="free@example.com", password="secret", full_name="Free User")
    fake_ollama = FakeOllamaAdminService()
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        response = client.post(
            "/v1/admin/ai-models/ollama/models/llama3.2:3b/default",
            headers=headers,
            json={"reason": "Promote smaller local model for free users."},
        )
        inventory_response = client.get("/v1/admin/ai-models/ollama/models", headers=headers)
        route = store.resolve_ai_model_route(user_id=free_user.user_id, plan_code="free", task_type="default")
        policies = {item.policy_id: item for item in store.list_ai_task_route_policies()}
        audit_events = store.list_ai_model_admin_audit_events(limit=5)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["model_code"] == "llama3.2:3b"
    assert response.json()["is_default_for_free"] is True
    assert route.model_profile is not None
    assert route.model_profile.model_code == "llama3.2:3b"
    assert policies["default:free:default"].preferred_local_model_profile_id == response.json()["model_profile_id"]
    assert policies["default:case:default"].preferred_local_model_profile_id == response.json()["model_profile_id"]
    models = inventory_response.json()["models"]
    promoted_model = next(item for item in models if item["name"] == "llama3.2:3b")
    old_model = next(item for item in models if item["name"] == "qwen3:1.7b")
    assert promoted_model["is_default"] is True
    assert promoted_model["removable"] is False
    assert old_model["is_default"] is False
    assert old_model["removable"] is True
    assert audit_events[0].action == "ollama_default.set"


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


def test_admin_can_remove_configured_non_default_ollama_model_and_rewrite_policies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    store.upsert_ai_model_profile(
        model_profile_id="local_ollama_qwen4b",
        provider_id="local_ollama",
        model_code="qwen3:4b",
        deployment_name="qwen3:4b",
        billing_currency="EUR",
        eu_data_zone_capable=True,
        is_default_for_free=False,
        enabled=True,
    )
    store.upsert_ai_task_route_policy(
        policy_id="default:free:custom",
        task_type="default",
        plan_code="free",
        preferred_local_model_profile_id="local_ollama_qwen4b",
        allow_external=False,
        enabled=True,
    )
    fake_ollama = FakeOllamaAdminService(
        models=[
            OllamaInstalledModel(
                name="qwen3:1.7b",
                model="qwen3:1.7b",
                modified_at="2026-06-27T10:00:00Z",
                size=17_000_000_000,
                digest="sha256:default",
            ),
            OllamaInstalledModel(
                name="qwen3:4b",
                model="qwen3:4b",
                modified_at="2026-07-03T10:00:00Z",
                size=4_000_000_000,
                digest="sha256:qwen4b",
            ),
        ]
    )
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).request(
            "DELETE",
            "/v1/admin/ai-models/ollama/models/qwen3:4b",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
            json={"reason": "Remove non-default configured model."},
        )
        profiles = {item.model_profile_id: item for item in store.list_ai_model_profiles(include_deleted=True)}
        policies = {item.policy_id: item for item in store.list_ai_task_route_policies()}
        audit_events = store.list_ai_model_admin_audit_events(limit=5)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["action"] == "remove"
    assert fake_ollama.removed == ["qwen3:4b"]
    assert profiles["local_ollama_qwen4b"].enabled is False
    assert profiles["local_ollama_qwen4b"].deleted_at is not None
    assert policies["default:free:custom"].preferred_local_model_profile_id == "local_ollama_default"
    assert audit_events[0].action == "ollama_remove_started"
    assert "local_ollama_qwen4b" in audit_events[0].old_value_summary


def test_admin_can_delete_not_installed_configured_ollama_model_even_if_marked_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    store.upsert_ai_model_profile(
        model_profile_id="local_ollama_missing",
        provider_id="local_ollama",
        model_code="Qwen3:4b",
        deployment_name="Qwen3:4b",
        billing_currency="EUR",
        eu_data_zone_capable=True,
        is_default_for_free=True,
        enabled=True,
    )
    store.upsert_ai_task_route_policy(
        policy_id="default:free:custom",
        task_type="default",
        plan_code="free",
        preferred_local_model_profile_id="local_ollama_missing",
        allow_external=False,
        enabled=True,
    )
    fake_ollama = FakeOllamaAdminService(models=[])
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    client = TestClient(app)
    headers = {**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id}
    try:
        inventory_response = client.get("/v1/admin/ai-models/ollama/models", headers=headers)
        remove_response = client.request(
            "DELETE",
            "/v1/admin/ai-models/ollama/models/Qwen3:4b",
            headers=headers,
            json={"reason": "Delete missing configured Ollama model."},
        )
        profiles = {item.model_profile_id: item for item in store.list_ai_model_profiles(include_deleted=True)}
        policies = {item.policy_id: item for item in store.list_ai_task_route_policies()}
        refreshed_inventory_response = client.get("/v1/admin/ai-models/ollama/models", headers=headers)
    finally:
        app.dependency_overrides.clear()

    missing_model = next(item for item in inventory_response.json()["models"] if item["name"] == "Qwen3:4b")
    assert missing_model["installed"] is False
    assert missing_model["is_default"] is False
    assert missing_model["removable"] is True
    assert remove_response.status_code == 200
    assert remove_response.json()["status"] == "succeeded"
    assert fake_ollama.removed == []
    assert profiles["local_ollama_missing"].deleted_at is not None
    assert policies["default:free:custom"].preferred_local_model_profile_id is None
    assert all(item["name"] != "Qwen3:4b" for item in refreshed_inventory_response.json()["models"])


def test_admin_can_remove_ollama_model_after_linked_profiles_are_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = _store(tmp_path)
    admin = store.create_user(email="admin@example.com", password="secret", full_name="Admin User")
    store.upsert_ai_model_profile(
        model_profile_id="local_ollama_default",
        provider_id="local_ollama",
        model_code="qwen3:1.7b",
        deployment_name="qwen3:1.7b",
        billing_currency="EUR",
        eu_data_zone_capable=True,
        is_default_for_free=True,
        enabled=False,
    )
    fake_ollama = FakeOllamaAdminService()
    app.dependency_overrides[get_admin_store] = lambda: store
    app.dependency_overrides[get_ollama_admin_service] = lambda: fake_ollama
    monkeypatch.setenv("JURISDIGTA_ADMIN_EMAILS", "admin@example.com")
    try:
        response = TestClient(app).request(
            "DELETE",
            "/v1/admin/ai-models/ollama/models/qwen3:1.7b",
            headers={**AUTH_HEADERS, "x-jurisdigta-admin-user-id": admin.user_id},
            json={"reason": "Remove disabled local runtime model."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["action"] == "remove"
    assert fake_ollama.removed == ["qwen3:1.7b"]


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
