from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from aijurisdictionagents.api_db import ApiDatabaseStore


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
