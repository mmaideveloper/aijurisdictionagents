"""Minimal demo for AI model routing and token usage accounting.

Run:
    python examples/model_routing_minimal_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from aijurisdictionagents.api_db import ApiDatabaseStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="model-routing-demo-", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        store = ApiDatabaseStore(db_path=root / "api.sqlite3", blob_root=root / "blob")
        store.initialize()

        user = store.create_user(
            email="demo@example.com",
            password="demo-secret",
            full_name="Demo User",
        )
        external_provider = store.upsert_ai_model_provider(
            provider_code="azure_foundry",
            provider_type="azurefoundry",
            display_name="Azure AI Foundry",
            base_url="https://example.openai.azure.com",
            region="swedencentral",
            data_zone="eu",
            is_external=True,
        )
        external_profile = store.upsert_ai_model_profile(
            model_profile_id="azure_foundry_gpt_4o_mini",
            provider_id=external_provider.provider_id,
            model_code="gpt-4o-mini",
            deployment_name="gpt-4o-mini",
            input_price_per_1m=2.0,
            output_price_per_1m=8.0,
            billing_currency="USD",
            eu_data_zone_capable=True,
        )
        store.upsert_ai_task_route_policy(
            task_type="document_generation",
            plan_code="case",
            preferred_external_model_profile_id=external_profile.model_profile_id,
            preferred_local_model_profile_id="local_ollama_default",
            allow_external=True,
            require_external_ack=True,
            fallback_local_on_budget=True,
            max_cost_eur=0.008,
        )

        free_route = store.resolve_ai_model_route(
            user_id=user.user_id,
            plan_code="free",
            task_type="document_generation",
        )
        paid_route = store.resolve_ai_model_route(
            user_id=user.user_id,
            plan_code="case",
            task_type="document_generation",
            external_acknowledged=True,
        )

        print(f"Free route: {free_route.route_type} -> {free_route.provider.provider_code}")
        print(f"Paid route: {paid_route.route_type} -> {paid_route.provider.provider_code}")

        store.record_ai_model_usage(
            provider=paid_route.provider.provider_code,
            model=paid_route.model_profile.model_code,
            route_type=paid_route.route_type,
            input_tokens=1200,
            output_tokens=700,
            estimated_cost_eur=0.008,
            case_id="case-demo",
            user_id=user.user_id,
            plan_code="case",
            task_type="document_generation",
        )

        summary = store.summarize_ai_model_usage(minutes=60, case_id="case-demo")[0]
        print(
            "Usage: "
            f"requests={summary.request_count}, input={summary.input_tokens}, "
            f"output={summary.output_tokens}, cost_eur={summary.estimated_cost_eur:.4f}"
        )

        budget_route = store.resolve_ai_model_route(
            user_id=user.user_id,
            plan_code="case",
            task_type="document_generation",
            external_acknowledged=True,
        )
        print(
            "Budget route: "
            f"{budget_route.route_type} -> {budget_route.provider.provider_code}; "
            f"reason={budget_route.reason}"
        )


if __name__ == "__main__":
    main()
