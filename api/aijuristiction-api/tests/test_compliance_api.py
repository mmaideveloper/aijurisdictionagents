from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore


AUTH_HEADERS = {"x-api-key": "aijuris"}
client = TestClient(app)


def _configure(monkeypatch, tmp_path: Path) -> ApiDatabaseStore:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


def test_compliance_api_records_revocation_exports_and_restricts(monkeypatch, tmp_path: Path) -> None:
    store = _configure(monkeypatch, tmp_path)
    user = store.create_user(email="api-dsar@example.test", password="synthetic")

    grant = client.post(
        f"/v1/compliance/users/{user.user_id}/consents",
        headers=AUTH_HEADERS,
        json={
            "scope": "external_model",
            "notice_version": "external-model-v1",
            "granted": True,
            "source": "ui",
            "country": "SK",
            "purpose": "external_ai_generation",
        },
    )
    assert grant.status_code == 201
    assert grant.json()["granted"] is True

    restriction = client.put(
        f"/v1/compliance/users/{user.user_id}/processing-restriction",
        headers=AUTH_HEADERS,
        json={"restricted": True, "reason_code": "subject_request"},
    )
    assert restriction.status_code == 200
    assert restriction.json()["restricted"] is True

    export = client.get(
        f"/v1/compliance/users/{user.user_id}/dsar/export",
        headers=AUTH_HEADERS,
    )
    assert export.status_code == 200
    assert export.json()["user"]["email"] == "api-dsar@example.test"

    unconfirmed = client.post(
        f"/v1/compliance/users/{user.user_id}/dsar/actions",
        headers=AUTH_HEADERS,
        json={"action": "delete", "confirmed": False},
    )
    assert unconfirmed.status_code == 409
