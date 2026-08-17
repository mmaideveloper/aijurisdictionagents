"""Encrypt approved real-model E2E credentials into branch-local PostgreSQL."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm.azure_foundry_client import AzureFoundryClient, AzureFoundryConfig
from aijurisdictionagents.schemas import Message


PROVIDER_ID = "azure_foundry"
PROFILE_ID = "azure_foundry_gpt_4o_mini"
EXPECTED_MODEL = "gpt-4o-mini"
_PLACEHOLDERS = {"", "unknown-variable", "your_azure_key", "optional_aad_token"}


@dataclass(frozen=True)
class E2EModelConfig:
    endpoint: str
    api_version: str
    deployment: str
    secret_type: str
    secret_value: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".env",
        help="Ignored dotenv file containing E2E_AZURE_FOUNDRY_* values.",
    )
    parser.add_argument(
        "--verify-model",
        action="store_true",
        help="Send one synthetic connectivity prompt through the imported real model.",
    )
    return parser.parse_args()


def _resolved_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value.lower() in _PLACEHOLDERS or "YOUR_RESOURCE_NAME" in value:
        raise ValueError(f"{name} must contain a resolved E2E value.")
    return value


def _config_from_env() -> E2EModelConfig:
    endpoint = _resolved_env("E2E_AZURE_FOUNDRY_ENDPOINT").rstrip("/")
    api_version = _resolved_env("E2E_AZURE_FOUNDRY_API_VERSION")
    deployment = _resolved_env("E2E_AZURE_FOUNDRY_DEPLOYMENT")
    api_key = os.getenv("E2E_AZURE_FOUNDRY_API_KEY", "").strip()
    ad_token = os.getenv("E2E_AZURE_FOUNDRY_AD_TOKEN", "").strip()
    api_key = "" if api_key.lower() in _PLACEHOLDERS else api_key
    ad_token = "" if ad_token.lower() in _PLACEHOLDERS else ad_token
    if bool(api_key) == bool(ad_token):
        raise ValueError(
            "Configure exactly one of E2E_AZURE_FOUNDRY_API_KEY or "
            "E2E_AZURE_FOUNDRY_AD_TOKEN."
        )
    if not endpoint.startswith("https://"):
        raise ValueError("E2E_AZURE_FOUNDRY_ENDPOINT must use HTTPS.")
    if deployment != EXPECTED_MODEL:
        raise ValueError(
            f"This bootstrap expects {EXPECTED_MODEL!r}; got {deployment!r}. "
            "Create a task-specific bootstrap for a different required model."
        )
    return E2EModelConfig(
        endpoint=endpoint,
        api_version=api_version,
        deployment=deployment,
        secret_type="api_key" if api_key else "azure_ad_token",
        secret_value=api_key or ad_token,
    )


def _assert_safe_local_runtime() -> None:
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "mock":
        raise ValueError("LLM_PROVIDER=mock is forbidden for real-model E2E bootstrap.")
    if os.getenv("DB_OPTION", "").strip().lower() != "postgres":
        raise ValueError("DB_OPTION=postgres is required for real local E2E bootstrap.")
    database_url = _resolved_env("DB_CLOUD")
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DB_CLOUD must be a PostgreSQL URL.")
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Refusing to write E2E credentials to a non-loopback database.")
    encryption_key = _resolved_env("AI_MODEL_CREDENTIAL_ENCRYPTION_KEY")
    if len(encryption_key) < 24:
        raise ValueError("AI_MODEL_CREDENTIAL_ENCRYPTION_KEY must contain at least 24 characters.")


def _bootstrap(store: ApiDatabaseStore, config: E2EModelConfig) -> None:
    store.initialize()
    provider = store.upsert_ai_model_provider(
        provider_id=PROVIDER_ID,
        provider_code=PROVIDER_ID,
        provider_type="azurefoundry",
        display_name="Azure AI Foundry",
        base_url=config.endpoint,
        api_version=config.api_version,
        region="eu",
        data_zone="eu",
        is_external=True,
        is_local=False,
        health_check_url=config.endpoint,
        enabled=True,
    )
    profiles = {
        item.model_profile_id: item
        for item in store.list_ai_model_profiles(provider_id=provider.provider_id)
    }
    profile = profiles.get(PROFILE_ID)
    if profile is None:
        raise RuntimeError(f"Required seeded model profile {PROFILE_ID} is missing.")
    if profile.model_code != config.deployment or profile.deployment_name != config.deployment:
        raise RuntimeError(f"Model profile {PROFILE_ID} does not select {config.deployment}.")
    store.upsert_ai_model_credential(
        credential_id=f"{PROVIDER_ID}:{config.secret_type}:e2e-default",
        provider_id=provider.provider_id,
        secret_value=config.secret_value,
        credential_name="e2e-default",
        secret_type=config.secret_type,
        enabled=True,
    )


def _verify_model(store: ApiDatabaseStore, config: E2EModelConfig) -> None:
    stored_secret = store.get_ai_model_provider_secret(
        provider_id=PROVIDER_ID,
        secret_type=config.secret_type,
    )
    if not stored_secret:
        raise RuntimeError("The encrypted database credential could not be decrypted.")
    client = AzureFoundryClient(
        AzureFoundryConfig(
            endpoint=config.endpoint,
            deployment=config.deployment,
            api_version=config.api_version,
            temperature=0.0,
            api_key=stored_secret if config.secret_type == "api_key" else None,
            azure_ad_token=stored_secret if config.secret_type == "azure_ad_token" else None,
        )
    )
    response = client.complete(
        "e2e-credential-check",
        "This is a synthetic connectivity check. Return a short non-empty acknowledgement.",
        [
            Message(
                role="user",
                content="Synthetic E2E model connectivity check.",
                agent_name="E2E",
            )
        ],
        [],
    )
    if not response.strip():
        raise RuntimeError("The real model returned an empty connectivity response.")


def main() -> int:
    args = _arguments()
    load_dotenv(args.env_file, override=False)
    _assert_safe_local_runtime()
    config = _config_from_env()
    store = ApiDatabaseStore.from_env()
    _bootstrap(store, config)
    if args.verify_model:
        _verify_model(store, config)
    print(
        "Real-model E2E credential ready: "
        f"provider={PROVIDER_ID} profile={PROFILE_ID} model={config.deployment} "
        f"credential_type={config.secret_type} verified={args.verify_model}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
