from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_e2e_model_credentials.py"
_SPEC = importlib.util.spec_from_file_location("bootstrap_e2e_model_credentials", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_safe_runtime_rejects_non_loopback_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("DB_OPTION", "postgres")
    monkeypatch.setenv("DB_CLOUD", "postgresql://user:secret@production.example.test/api")
    monkeypatch.setenv("AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "synthetic-encryption-key-for-tests")

    with pytest.raises(ValueError, match="non-loopback"):
        _MODULE._assert_safe_local_runtime()


def test_bootstrap_encrypts_e2e_credential_without_revealing_it(tmp_path: Path) -> None:
    store = ApiDatabaseStore(
        db_path=tmp_path / "api.sqlite3",
        blob_root=tmp_path / "files",
    )
    config = _MODULE.E2EModelConfig(
        endpoint="https://synthetic-foundry.example.test",
        api_version="2024-10-21",
        deployment="gpt-4o-mini",
        secret_type="api_key",
        secret_value="synthetic-secret-never-production",
    )

    _MODULE._bootstrap(store, config)

    providers = {item.provider_id: item for item in store.list_ai_model_providers()}
    credentials = store.list_ai_model_credentials(provider_id="azure_foundry", reveal=False)
    assert providers["azure_foundry"].base_url == config.endpoint
    assert len(credentials) == 1
    assert credentials[0].secret_value is None
    assert store.get_ai_model_provider_secret(provider_id="azure_foundry") == config.secret_value


def test_verify_model_uses_secret_reloaded_from_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ApiDatabaseStore(
        db_path=tmp_path / "api.sqlite3",
        blob_root=tmp_path / "files",
    )
    config = _MODULE.E2EModelConfig(
        endpoint="https://synthetic-foundry.example.test",
        api_version="2024-10-21",
        deployment="gpt-4o-mini",
        secret_type="api_key",
        secret_value="synthetic-secret-never-production",
    )
    _MODULE._bootstrap(store, config)
    captured: dict[str, str | None] = {}

    class FakeClient:
        def __init__(self, client_config: Any) -> None:
            captured["api_key"] = client_config.api_key

        def complete(self, *args: object, **kwargs: object) -> str:
            return "ready"

    monkeypatch.setattr(_MODULE, "AzureFoundryClient", FakeClient)

    different_memory_config = _MODULE.E2EModelConfig(
        endpoint=config.endpoint,
        api_version=config.api_version,
        deployment=config.deployment,
        secret_type=config.secret_type,
        secret_value="must-not-be-used-directly",
    )
    _MODULE._verify_model(store, different_memory_config)

    assert captured["api_key"] == config.secret_value


def test_production_model_bootstrap_keeps_exact_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_MODULE, "PROVIDER_ID", "azurefoundryeu")
    monkeypatch.setattr(_MODULE, "PROFILE_ID", "azurefoundryeu:gpt-5-mini")
    monkeypatch.setattr(_MODULE, "EXPECTED_MODEL", "gpt-5-mini")
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "files")
    config = _MODULE.E2EModelConfig(
        endpoint="https://synthetic-foundry.example.test", api_version="2025-04-01-preview",
        deployment="gpt-5-mini", secret_type="api_key", secret_value="synthetic-test-only",
    )
    _MODULE._bootstrap(store, config)
    profile = next(p for p in store.list_ai_model_profiles() if p.model_profile_id == _MODULE.PROFILE_ID)
    assert profile.model_code == profile.deployment_name == "gpt-5-mini"
    assert profile.model_parameters == {}

    class ProductionModelProbe:
        def __init__(self, client_config: Any) -> None:
            assert client_config.deployment == "gpt-5-mini"
            assert client_config.temperature in (None, 1.0)

        def complete(self, *args: object, **kwargs: object) -> str:
            return "synthetic acknowledgement"

    monkeypatch.setattr(_MODULE, "AzureFoundryClient", ProductionModelProbe)
    _MODULE._verify_model(store, config)
    monkeypatch.setenv("E2E_AZURE_FOUNDRY_ENDPOINT", config.endpoint)
    monkeypatch.setenv("E2E_AZURE_FOUNDRY_API_VERSION", config.api_version)
    monkeypatch.setenv("E2E_AZURE_FOUNDRY_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setenv("E2E_AZURE_FOUNDRY_API_KEY", config.secret_value)
    monkeypatch.delenv("E2E_AZURE_FOUNDRY_AD_TOKEN", raising=False)
    with pytest.raises(ValueError, match="expects 'gpt-5-mini'"):
        _MODULE._config_from_env()
