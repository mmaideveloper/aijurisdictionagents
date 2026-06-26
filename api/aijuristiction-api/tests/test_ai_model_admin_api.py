from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.ai_model_admin_api import get_admin_store
from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore

AUTH_HEADERS = {"x-api-key": "aijuris"}


def _store(tmp_path: Path) -> ApiDatabaseStore:
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blob")
    store.initialize()
    return store


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
