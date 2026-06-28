from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm.routing import get_routed_llm_client


client = TestClient(app)


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
    assert route.model_profile.model_code == "qwen3:1.7b"
    assert route.model_profile.is_default_for_free is True


def test_seeded_local_ollama_provider_uses_configured_container_url(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCAL_LLM_OPENAI_BASE_URL", "http://172.18.0.1:11434/v1")
    monkeypatch.setenv("LOCAL_LLM_HEALTH_URL", "http://172.18.0.1:11434/api/tags")
    store = _store(tmp_path)

    provider = next(item for item in store.list_ai_model_providers() if item.provider_code == "local_ollama")

    assert provider.base_url == "http://172.18.0.1:11434/v1"
    assert provider.health_check_url == "http://172.18.0.1:11434/api/tags"


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


def test_expired_paid_subscription_routes_as_free_local_model(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    store = _store(tmp_path)
    user = store.create_user(email="expired@example.com", password="secret", full_name="Expired User")
    subscription = store.request_subscription_change(user_id=user.user_id, plan_code="case")
    paid_subscription = store.update_subscription_status(
        subscription_id=subscription.subscription_id,
        status="paid",
    )
    past_end = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    with store._connect() as conn:
        store._execute(
            conn,
            "UPDATE user_subscriptions SET ends_at = ? WHERE subscription_id = ?",
            (past_end, paid_subscription.subscription_id),
        )
        conn.commit()

    plan = store.get_effective_subscription_plan(user_id=user.user_id)
    effective_subscription = store.get_effective_user_subscription(user_id=user.user_id)
    routed = get_routed_llm_client(
        store=store,
        user_id=user.user_id,
        task_type="chat_reply",
    )

    assert effective_subscription is not None
    assert effective_subscription.plan_code == "free"
    assert plan.plan_code == "free"
    assert routed.plan_code == "free"
    assert routed.subscription_id == effective_subscription.subscription_id
    assert routed.provider == "local_ollama"
    assert routed.route_type == "free_local"
    assert routed.model == "qwen3:1.7b"


def test_effective_model_route_endpoint_reports_free_user_local_model(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "api.sqlite3"
    blob_root = tmp_path / "blob"
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(db_path))
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("STORE_LOCAL", str(blob_root))
    store = ApiDatabaseStore(db_path=db_path, blob_root=blob_root)
    store.initialize()
    user = store.create_user(email="route-label@example.com", password="secret", full_name="Route Label")

    response = client.get(
        f"/v1/model-routing/effective?user_id={user.user_id}&task_type=chat_reply",
        headers={"x-api-key": "aijuris"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_code"] == "free"
    assert payload["route_type"] == "free_local"
    assert payload["provider"] == "local_ollama"
    assert payload["model"] == "qwen3:1.7b"
    assert payload["is_local"] is True
    assert payload["is_external"] is False
    assert payload["label"] == "Local Ollama - qwen3:1.7b"


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
            "model_code": "qwen3:1.7b",
            "deployment_name": "qwen3:1.7b",
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
    assert profile_response.json()["model_code"] == "qwen3:1.7b"
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


def test_usage_ledger_summarizes_tokens_and_cost_by_model_without_identifiers(
    tmp_path: Path,
) -> None:
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
    assert summary.case_id == ""
    assert summary.user_id == ""
    assert summary.subscription_id == ""
    assert summary.input_tokens == 1200
    assert summary.cached_input_tokens == 250
    assert summary.output_tokens == 600
    assert summary.total_tokens == 1800
    assert summary.estimated_cost_eur == 0.012


def test_usage_ledger_lists_top_cases_by_tokens(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_ai_model_usage(
        provider="local_ollama",
        model="qwen3.6:27b",
        route_type="local",
        input_tokens=500,
        output_tokens=250,
        case_id="case-local",
        plan_code="free",
    )
    store.record_ai_model_usage(
        provider="azure_foundry",
        model="gpt-4.1",
        route_type="external",
        input_tokens=3000,
        output_tokens=1000,
        estimated_cost_eur=0.05,
        case_id="case-paid",
        plan_code="case",
    )

    top_cases = store.summarize_top_ai_model_cases(minutes=60, limit=1)

    assert len(top_cases) == 1
    assert top_cases[0].case_id == "case-paid"
    assert top_cases[0].total_tokens == 4000
    assert top_cases[0].estimated_cost_eur == 0.05


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
                        "window_minutes": 60,
                        "plan_code": "case",
                        "task_type": "document_generation",
                        "provider": "azure_foundry",
                        "model": "gpt-4.1",
                        "route_type": "external",
                        "route_class": "paid",
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
                "top_cases": [
                    {
                        "case_ref": "case-...se-1",
                        "window_minutes": 60,
                        "plan_code": "case",
                        "provider": "azure_foundry",
                        "model": "gpt-4.1",
                        "route_type": "external",
                        "route_class": "paid",
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
    assert 'case_id="case-1"' not in rendered
    assert 'user_id="user-1"' not in rendered
    assert 'subscription_id="sub-1"' not in rendered
    assert 'case_ref="case-...se-1"' in rendered
    assert "jurisdigta_ai_model_top_case_total_tokens_window" in rendered
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
