from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm.routing import get_routed_llm_client


def _store(tmp_path: Path) -> ApiDatabaseStore:
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blob")
    store.initialize()
    return store


def test_free_plan_routes_to_seeded_local_ollama_model(tmp_path: Path) -> None:
    store = _store(tmp_path)
    user = store.create_user(email="free@example.com", password="secret", full_name="Free User")

    route = store.resolve_ai_model_route(
        user_id=user.user_id,
        plan_code="free",
        task_type="legal_analysis",
    )

    assert route.route_type == "free_local"
    assert route.provider is not None
    assert route.provider.provider_code == "local_ollama"
    assert route.model_profile is not None
    assert route.model_profile.model_profile_id == "local_ollama_default"
    assert route.model_profile.model_code == "qwen3.6:27b"
    assert route.model_profile.is_default_for_free is True


def test_case_plan_routes_to_seeded_azure_foundry_gpt_4o_mini_model(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "test-routing-secret")
    store = _store(tmp_path)
    user = store.create_user(email="case@example.com", password="secret", full_name="Case User")
    subscription = store.request_subscription_change(user_id=user.user_id, plan_code="case")
    store.update_subscription_status(subscription_id=subscription.subscription_id, status="paid")
    store.upsert_ai_model_provider(
        provider_code="azure_foundry",
        provider_type="azurefoundry",
        display_name="Azure AI Foundry",
        base_url="https://example.openai.azure.com",
        api_version="2024-10-21",
        data_zone="eu",
        is_external=True,
    )
    store.upsert_ai_model_credential(
        provider_id="azure_foundry",
        secret_value="azure-secret-key",
        secret_type="api_key",
    )

    routed = get_routed_llm_client(
        store=store,
        user_id=user.user_id,
        task_type="chat_reply",
    )

    assert routed.provider == "azure_foundry"
    assert routed.model == "gpt-4o-mini"
    assert routed.route_type == "external"
    assert routed.plan_code == "case"
    assert routed.subscription_id == subscription.subscription_id


def test_model_credentials_are_encrypted_and_revealed_only_when_requested(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "test-routing-secret")
    store = _store(tmp_path)

    credential = store.upsert_ai_model_credential(
        provider_id="azure_foundry",
        secret_value="secret-value-123",
        secret_type="api_key",
    )
    redacted = store.list_ai_model_credentials(provider_id="azure_foundry")
    revealed = store.list_ai_model_credentials(provider_id="azure_foundry", reveal=True)

    assert credential.protected_secret != "secret-value-123"
    assert "secret-value-123" not in credential.protected_secret
    assert redacted[0].secret_value is None
    assert redacted[0].secret_preview == "sec...-123"
    assert revealed[0].secret_value == "secret-value-123"
    assert revealed[0].last_revealed_at is not None


def test_admin_model_credentials_api_redacts_by_default(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    monkeypatch.setenv("AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "test-routing-secret")
    monkeypatch.setenv("JURISDIGTA_ADMIN_API_KEY", "admin-secret")
    client = TestClient(app)
    headers = {"x-api-key": "aijuris", "x-admin-api-key": "admin-secret"}

    create_response = client.put(
        "/v1/admin/ai-models/providers/azure_foundry/credentials",
        headers=headers,
        json={"secret_value": "secret-value-123", "secret_type": "api_key"},
    )
    list_response = client.get(
        "/v1/admin/ai-models/credentials?provider_id=azure_foundry",
        headers=headers,
    )
    reveal_response = client.get(
        "/v1/admin/ai-models/credentials?provider_id=azure_foundry&reveal=true",
        headers=headers,
    )

    assert create_response.status_code == 201
    assert create_response.json()["secret_value"] is None
    assert "secret-value-123" not in create_response.text
    assert list_response.status_code == 200
    assert list_response.json()[0]["secret_value"] is None
    assert "secret-value-123" not in list_response.text
    assert reveal_response.status_code == 200
    assert reveal_response.json()[0]["secret_value"] == "secret-value-123"


def test_admin_model_routing_api_upserts_provider_and_profile(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    monkeypatch.setenv("JURISDIGTA_ADMIN_API_KEY", "admin-secret")
    client = TestClient(app)
    headers = {"x-api-key": "aijuris", "x-admin-api-key": "admin-secret"}

    provider_response = client.put(
        "/v1/admin/ai-models/providers/local_ollama_alt",
        headers=headers,
        json={
            "provider_code": "local_ollama_alt",
            "provider_type": "ollama",
            "display_name": "Local Ollama Alt",
            "base_url": "http://127.0.0.1:11434/v1",
            "is_local": True,
        },
    )
    profile_response = client.put(
        "/v1/admin/ai-models/profiles/local_ollama_alt_qwen",
        headers=headers,
        json={
            "provider_id": "local_ollama_alt",
            "model_code": "qwen3.6:27b",
            "deployment_name": "qwen3.6:27b",
            "is_default_for_free": True,
            "enabled": True,
        },
    )
    profiles_response = client.get(
        "/v1/admin/ai-models/profiles?provider_id=local_ollama_alt",
        headers=headers,
    )

    assert provider_response.status_code == 201
    assert provider_response.json()["base_url"] == "http://127.0.0.1:11434/v1"
    assert profile_response.status_code == 201
    assert profile_response.json()["model_code"] == "qwen3.6:27b"
    assert profile_response.json()["is_default_for_free"] is True
    assert profiles_response.status_code == 200
    assert profiles_response.json()[0]["model_profile_id"] == "local_ollama_alt_qwen"


def test_paid_external_route_requires_acknowledgement(tmp_path: Path) -> None:
    store = _store(tmp_path)
    user = store.create_user(email="paid@example.com", password="secret", full_name="Paid User")
    provider = store.upsert_ai_model_provider(
        provider_code="azure_foundry",
        provider_type="azurefoundry",
        display_name="Azure AI Foundry",
        base_url="https://example.openai.azure.com",
        region="swedencentral",
        data_zone="eu",
        is_external=True,
    )
    profile = store.upsert_ai_model_profile(
        provider_id=provider.provider_id,
        model_code="gpt-4.1",
        deployment_name="jurisdigta-gpt-4-1",
        input_price_per_1m=2.0,
        output_price_per_1m=8.0,
        eu_data_zone_capable=True,
    )
    store.upsert_ai_task_route_policy(
        task_type="document_generation",
        plan_code="case",
        preferred_external_model_profile_id=profile.model_profile_id,
        preferred_local_model_profile_id="local_ollama_default",
        allow_external=True,
        require_external_ack=True,
    )

    blocked = store.resolve_ai_model_route(
        user_id=user.user_id,
        plan_code="case",
        task_type="document_generation",
    )
    allowed = store.resolve_ai_model_route(
        user_id=user.user_id,
        plan_code="case",
        task_type="document_generation",
        external_acknowledged=True,
    )

    assert blocked.route_type == "external_ack_required"
    assert blocked.requires_external_ack is True
    assert allowed.route_type == "external"
    assert allowed.provider is not None
    assert allowed.provider.provider_code == "azure_foundry"
    assert allowed.model_profile is not None
    assert allowed.model_profile.model_code == "gpt-4.1"


def test_usage_ledger_summarizes_tokens_and_cost_by_case_model(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_ai_model_usage(
        provider="azure_foundry",
        model="gpt-4.1",
        route_type="external",
        input_tokens=1000,
        cached_input_tokens=250,
        output_tokens=500,
        estimated_cost_eur=0.01,
        case_id="case-1",
        user_id="user-1",
        subscription_id="sub-1",
        plan_code="case",
        task_type="document_generation",
    )
    store.record_ai_model_usage(
        provider="azure_foundry",
        model="gpt-4.1",
        route_type="external",
        input_tokens=200,
        output_tokens=100,
        estimated_cost_eur=0.002,
        case_id="case-1",
        user_id="user-1",
        subscription_id="sub-1",
        plan_code="case",
        task_type="document_generation",
    )

    summaries = store.summarize_ai_model_usage(minutes=60, case_id="case-1")

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.request_count == 2
    assert summary.input_tokens == 1200
    assert summary.cached_input_tokens == 250
    assert summary.output_tokens == 600
    assert summary.total_tokens == 1800
    assert summary.estimated_cost_eur == 0.012


def test_usage_ledger_lists_question_model_audit_entries(tmp_path: Path) -> None:
    store = _store(tmp_path)
    usage_id = store.record_ai_model_usage(
        provider="azure_foundry",
        model="gpt-4.1",
        route_type="external",
        input_tokens=100,
        output_tokens=50,
        case_id="case-1",
        user_id="user-1",
        task_type="chat_reply",
        session_id="session-1",
        question_id="question-1",
        question_text="What law applies to this lease termination?",
        answer_id="answer-1",
        audit_metadata={"source": "test", "model_used": True},
    )

    entries = store.list_ai_model_usage_audit(case_id="case-1")

    assert len(entries) == 1
    entry = entries[0]
    assert entry.usage_id == usage_id
    assert entry.session_id == "session-1"
    assert entry.question_id == "question-1"
    assert entry.answer_id == "answer-1"
    assert entry.question_preview == "What law applies to this lease termination?"
    assert len(entry.question_sha256) == 64
    assert entry.provider == "azure_foundry"
    assert entry.model == "gpt-4.1"
    assert entry.audit_metadata["source"] == "test"


def test_status_exporter_renders_ai_model_usage_metrics() -> None:
    exporter = _load_status_exporter()

    rendered = exporter._render_metrics(
        {
            "generated_at": "2026-06-25T12:00:00Z",
            "status": "ok",
            "window_minutes": 60,
            "ai_model_usage": {
                "status": "ok",
                "window_minutes": 60,
                "summaries": [
                    {
                        "case_id": "case-1",
                        "user_id": "user-1",
                        "subscription_id": "sub-1",
                        "plan_code": "case",
                        "task_type": "document_generation",
                        "provider": "azure_foundry",
                        "model": "gpt-4.1",
                        "route_type": "external",
                        "status": "ok",
                        "fallback_reason": "",
                        "request_count": 2,
                        "input_tokens": 1200,
                        "cached_input_tokens": 250,
                        "output_tokens": 600,
                        "total_tokens": 2050,
                        "estimated_cost_eur": 0.012,
                    },
                ],
            },
        }
    )

    assert "jurisdigta_ai_model_output_tokens_window" in rendered
    assert 'case_id="case-1"' in rendered
    assert 'model="gpt-4.1"' in rendered
    assert " 600.0" in rendered
    assert "jurisdigta_ai_model_estimated_cost_eur_window" in rendered


def _load_status_exporter() -> Any:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "server" / "export_system_status_metrics.py"
    spec = importlib.util.spec_from_file_location("export_system_status_metrics", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load status exporter module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
