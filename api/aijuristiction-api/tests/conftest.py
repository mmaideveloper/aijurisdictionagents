from __future__ import annotations

import os

import pytest

# API default runtime provider is Azure Foundry.
# Tests use mock provider to stay deterministic and independent from cloud credentials.
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("SYSTEM_EMBEDDING_MODEL_OPTION", "cloud")


@pytest.fixture(autouse=True)
def _default_local_api_environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setenv(
        "API_DOCUMENT_TEMPLATES_SQLITE_PATH",
        str(tmp_path / "document_templates.sqlite3"),
    )
