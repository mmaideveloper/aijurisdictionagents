from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.provider_credentials.api import get_provider_credential_store, router
from app.provider_credentials.store import ProviderCredentialStore, ProviderCredentialStoreConfig
from app.security import require_api_key


def _build_store(tmp_path: Path, monkeypatch) -> ProviderCredentialStore:
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://jurisdigta-foundry.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-secret-value")
    return ProviderCredentialStore(
        ProviderCredentialStoreConfig(
            db_option="sqlite",
            db_cloud="",
            sqlite_path=tmp_path / "provider_credentials.sqlite3",
        )
    )


def _build_client(store: ProviderCredentialStore) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_provider_credential_store] = lambda: store
    app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app)


def test_provider_credentials_seed_azure_foundry_from_env(tmp_path: Path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)

    items = store.list()

    assert len(items) == 1
    azure = items[0]
    assert azure.provider_key == "azurefoundry"
    assert azure.display_name == "Azure Foundry"
    assert azure.endpoint == "https://jurisdigta-foundry.openai.azure.com/"
    assert azure.deployment == "gpt-4.1"
    assert azure.embeddings_model == "text-embedding-3-large"
    assert azure.api_version == "2025-01-01-preview"
    assert azure.auth_method == "api_key"
    assert azure.secret_name == "AZURE_OPENAI_API_KEY"
    assert azure.has_secret is True
    assert azure.metadata["configured"] is True


def test_provider_credentials_api_update_and_soft_delete(tmp_path: Path, monkeypatch) -> None:
    store = _build_store(tmp_path, monkeypatch)
    client = _build_client(store)

    list_response = client.get("/v1/provider-credentials")
    assert list_response.status_code == 200
    assert [item["provider_key"] for item in list_response.json()["items"]] == ["azurefoundry"]

    patch_response = client.patch(
        "/v1/provider-credentials/azurefoundry",
        json={
            "deployment": "gpt-4.1-mini",
            "api_version": "2025-02-01-preview",
            "metadata": {"source": "admin", "configured": True},
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["deployment"] == "gpt-4.1-mini"
    assert patched["api_version"] == "2025-02-01-preview"
    assert patched["metadata"]["source"] == "admin"
    assert "test-secret-value" not in str(patched)

    delete_response = client.delete("/v1/provider-credentials/azurefoundry")
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["is_deleted"] is True
    assert deleted["is_enabled"] is False

    active_response = client.get("/v1/provider-credentials")
    assert active_response.status_code == 200
    assert active_response.json()["items"] == []

    deleted_response = client.get("/v1/provider-credentials", params={"include_deleted": True})
    assert deleted_response.status_code == 200
    assert deleted_response.json()["items"][0]["provider_key"] == "azurefoundry"
