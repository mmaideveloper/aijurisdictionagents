"""Prepare synthetic PostgreSQL state for the issue #651 real-model E2E."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from aijurisdictionagents.api_db import ApiDatabaseStore
from services.court_decision_collector.domain import CourtDecisionRecord
from services.court_decision_collector.postgres_store import PostgresCourtDecisionStore


SYNTHETIC_EMAIL = "issue-651-latest-court-e2e@example.test"
SYNTHETIC_PASSWORD = "Issue-651-synthetic-only!"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-db-cloud", required=True)
    parser.add_argument("--court-db-cloud", required=True)
    parser.add_argument("--blob-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    load_dotenv(args.repo_root / ".env", override=False)
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    ad_token = os.getenv("AZURE_OPENAI_AD_TOKEN", "").strip()
    if not api_key and not ad_token:
        raise RuntimeError("Azure Foundry credential is required; mock fallback is forbidden.")
    endpoint = args.endpoint.strip().rstrip(",/")
    if not endpoint.startswith("https://"):
        raise ValueError("Azure Foundry endpoint must use HTTPS.")

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    api_store = ApiDatabaseStore(
        db_path=args.repo_root / "runs" / "storage" / "issue-651" / "unused.sqlite3",
        blob_root=args.blob_root,
        db_option="postgres",
        db_cloud=args.api_db_cloud,
        storage_option="local",
    )
    api_store.initialize()
    user = api_store.create_user(
        email=SYNTHETIC_EMAIL,
        password=SYNTHETIC_PASSWORD,
        full_name="Issue 651 Synthetic E2E User",
        data_processing_consent_at=now,
        data_processing_consent_version="issue-651-real-e2e-v1",
    )
    api_store.update_admin_user(user_id=user.user_id, role="admin", is_enabled=True)
    provider = api_store.upsert_ai_model_provider(
        provider_id="issue_651_azure_foundry",
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
    profile_id = "issue_651_azure_foundry_gpt_5_mini"
    api_store.upsert_ai_model_profile(
        model_profile_id=profile_id,
        provider_id=provider.provider_id,
        model_code=args.model,
        deployment_name=args.model,
        context_window_tokens=128_000,
        eu_data_zone_capable=True,
        model_parameters={"temperature": None},
        enabled=True,
    )
    credential_type = "api_key" if api_key else "azure_ad_token"
    api_store.upsert_ai_model_credential(
        provider_id=provider.provider_id,
        secret_value=api_key or ad_token,
        credential_name="issue-651-real-e2e",
        secret_type=credential_type,
        enabled=True,
    )
    api_store.upsert_ai_model_user_override(
        user_id=user.user_id,
        model_profile_id=profile_id,
        admin_user_id=user.user_id,
        reason="Synthetic real-model E2E validation for issue #651.",
    )
    case = api_store.create_case(
        user_id=user.user_id,
        company_id=None,
        title=f"Issue 651 latest court decisions {args.run_id}",
    )

    court_store = PostgresCourtDecisionStore(connection_uri=args.court_db_cloud)
    court_store.initialize()
    expected: list[dict[str, str]] = []
    dates = [
        "2026-08-20",
        "2026-08-19",
        "2026-08-18",
        "2026-08-17",
        "2026-08-16",
        "2026-08-15",
    ]
    for index, issue_date in enumerate(dates, start=1):
        decision_form = "uznesenie" if index == 1 else "rozsudok"
        public_metadata = f"{decision_form} {index}Synthetic/2026 ECLI:SK:SYNTH:2026:{index}.1"
        stored = court_store.upsert_decision(
            CourtDecisionRecord(
                source_system=f"synthetic-issue-651-{args.run_id}",
                source_guid=f"{args.run_id}-{index}",
                court_name="Synthetic District Court",
                court_type="synthetic",
                decision_form=decision_form,
                nature="synthetic",
                file_number=f"{index}Synthetic/2026",
                case_number=f"synthetic-{index}",
                ecli=f"ECLI:SK:SYNTH:2026:{index}.1",
                issue_date=issue_date,
                indexed_at=issue_date,
                update_date=issue_date,
                source_url=f"https://example.test/court-decisions/{args.run_id}/{index}",
                raw_text=public_metadata,
                pseudonymized_text=public_metadata,
                metadata={"synthetic": True, "run_id": args.run_id},
            )
        )
        if index <= 5:
            expected.append(
                {
                    "decision_id": stored.decision_id,
                    "file_number": f"{index}Synthetic/2026",
                    "issue_date": issue_date,
                }
            )

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_at": now,
                "run_id": args.run_id,
                "synthetic_only": True,
                "question": "Zobraz 5 posledn\u00fdch s\u00fadnych rozhodnut\u00ed.",
                "user": {"userId": user.user_id, "email": user.email, "name": user.full_name},
                "case_id": case.case_id,
                "case_title": case.title,
                "provider": "Azure AI Foundry",
                "model": args.model,
                "model_profile_id": profile_id,
                "model_parameters": {"temperature": None},
                "credential_type": credential_type,
                "services": ["frontend", "api", "mcp", "postgres-api", "postgres-court-decisions"],
                "expected_decisions": expected,
                "status": "prepared",
                "retention": "Delete this ignored evidence within 7 days.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"Prepared sanitized issue #651 manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
