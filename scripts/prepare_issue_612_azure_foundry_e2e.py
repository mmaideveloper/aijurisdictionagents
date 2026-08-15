"""Prepare isolated synthetic state for the issue #612 live Azure Foundry E2E."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from aijurisdictionagents.api_db import ApiDatabaseStore


DEFAULT_ENDPOINT = (
    "https://ai-mmatonok4721ai562138909778.services.ai.azure.com/"
    "api/projects/documentprocessing"
)
DEFAULT_MODEL = "gpt-5-mini"
SYNTHETIC_EMAIL = "issue-612-foundry-e2e@example.test"
SYNTHETIC_PASSWORD = "Issue-612-synthetic-only!"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--blob-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    load_dotenv(args.repo_root / ".env", override=False)

    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    ad_token = os.getenv("AZURE_OPENAI_AD_TOKEN", "").strip()
    if not api_key and not ad_token:
        raise RuntimeError(
            "Production Azure Foundry E2E requires AZURE_OPENAI_API_KEY or "
            "AZURE_OPENAI_AD_TOKEN; mock fallback is forbidden."
        )

    endpoint = args.endpoint.strip().rstrip(",/")
    model = args.model.strip()
    if not endpoint.startswith("https://"):
        raise ValueError("Azure Foundry endpoint must use HTTPS.")
    if not model:
        raise ValueError("Azure Foundry model is required.")

    store = ApiDatabaseStore(db_path=args.db_path, blob_root=args.blob_root)
    store.initialize()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    user = store.create_user(
        email=SYNTHETIC_EMAIL,
        password=SYNTHETIC_PASSWORD,
        full_name="Issue 612 Synthetic E2E User",
        data_processing_consent_at=now,
        data_processing_consent_version="issue-612-live-e2e-v1",
    )
    store.update_admin_user(user_id=user.user_id, role="admin", is_enabled=True)

    provider = store.upsert_ai_model_provider(
        provider_id="azure_foundry",
        provider_code="azure_foundry",
        provider_type="azurefoundry",
        display_name="azureFoundryEU",
        base_url=endpoint,
        api_version="",
        region="westeurope",
        data_zone="eu",
        is_external=True,
        is_local=False,
        health_check_url=endpoint,
        enabled=True,
    )
    profile_id = "issue_612_azure_foundry_gpt_5_mini"
    store.upsert_ai_model_profile(
        model_profile_id=profile_id,
        provider_id=provider.provider_id,
        model_code=model,
        deployment_name=model,
        context_window_tokens=128_000,
        eu_data_zone_capable=True,
        model_parameters={"temperature": None},
        enabled=True,
    )
    secret_type = "api_key" if api_key else "azure_ad_token"
    store.upsert_ai_model_credential(
        provider_id=provider.provider_id,
        secret_value=api_key or ad_token,
        credential_name="issue-612-live-e2e",
        secret_type=secret_type,
        enabled=True,
    )
    store.upsert_ai_model_user_override(
        user_id=user.user_id,
        model_profile_id=profile_id,
        admin_user_id=user.user_id,
        reason="Synthetic live E2E validation for issue #612.",
    )
    case = store.create_case(
        user_id=user.user_id,
        company_id=None,
        title="Issue 612 Azure Foundry v1 E2E",
    )

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_at": now,
                "synthetic_only": True,
                "user": {
                    "userId": user.user_id,
                    "email": user.email,
                    "name": user.full_name,
                },
                "case_id": case.case_id,
                "provider": "azureFoundryEU",
                "endpoint": endpoint,
                "model": model,
                "model_profile_id": profile_id,
                "model_parameters": {"temperature": None},
                "credential_type": secret_type,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"Prepared sanitized E2E manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
