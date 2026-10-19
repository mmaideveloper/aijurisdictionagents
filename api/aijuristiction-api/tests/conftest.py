from __future__ import annotations

import os
import base64
import json

import pytest

# API default runtime provider is Azure Foundry.
# Tests use mock provider to stay deterministic and independent from cloud credentials.
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("SYSTEM_EMBEDDING_MODEL_OPTION", "cloud")


@pytest.fixture(autouse=True)
def _default_local_api_environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key_file = tmp_path / "case-test-keys.json"
    key_file.write_text(json.dumps({"active": "test", "keys": {"test": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()}}))
    monkeypatch.setenv("CASE_ENCRYPTION_KEY_FILE", str(key_file))
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
    monkeypatch.setenv("API_CASE_WORKFLOWS_SQLITE_PATH", str(tmp_path / "workflows.sqlite3"))
    # Explicit offline dependency injection: production never selects memory as
    # a fallback when durable PostgreSQL configuration is missing.
    from langgraph.checkpoint.memory import InMemorySaver
    from app.case_workflows import service
    monkeypatch.setattr(service, "_build_workflow_checkpointer", lambda _store: InMemorySaver())
    service.get_case_workflow_service.cache_clear()
