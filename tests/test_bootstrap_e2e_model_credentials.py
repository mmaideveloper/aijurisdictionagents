from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_e2e_model_credentials.py"
_SPEC = importlib.util.spec_from_file_location("bootstrap_e2e_model_credentials", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_safe_runtime_rejects_non_loopback_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
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
