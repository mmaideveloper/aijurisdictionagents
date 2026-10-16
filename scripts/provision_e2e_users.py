from __future__ import annotations

import argparse
import os

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import (
    E2E_TEST_PAID_EMAIL,
    E2E_TEST_USER_EMAILS,
    provision_e2e_test_users,
)
from aijurisdictionagents.privacy import CONSENT_VERSION, PrivacyControls


E2E_AUDIT_ACTOR_ID = "post-deployment-e2e"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision approved synthetic production E2E users.")
    parser.add_argument(
        "--grant-synthetic-model-consent",
        action="store_true",
        help="Record current external-model consent only for the approved synthetic E2E accounts.",
    )
    parser.add_argument(
        "--paid-model",
        default="",
        help="Optional enabled external EU model code to assign only to the paid synthetic user.",
    )
    return parser.parse_args()


def _grant_synthetic_model_consent(*, store: ApiDatabaseStore, user_id: str) -> None:
    user = store.get_user(user_id=user_id)
    if user.email not in E2E_TEST_USER_EMAILS:
        raise ValueError("Model consent provisioning is restricted to approved synthetic E2E accounts")
    controls = PrivacyControls(store)
    if not controls.has_consent(user_id, "external_models"):
        controls.consent(user_id, "external_models", True, version=CONSENT_VERSION)
    print(f"synthetic external-model consent ready: user_id={user_id} notice={CONSENT_VERSION}")


def _configure_paid_model(
    *,
    store: ApiDatabaseStore,
    paid_user_id: str,
    model_code: str,
) -> None:
    normalized_model = model_code.strip().lower()
    providers = {item.provider_id: item for item in store.list_ai_model_providers()}
    candidates = []
    for profile in store.list_ai_model_profiles():
        provider = providers.get(profile.provider_id)
        if provider is None:
            continue
        profile_models = {profile.model_code.strip().lower(), profile.deployment_name.strip().lower()}
        if (
            normalized_model in profile_models
            and profile.enabled
            and provider.enabled
            and provider.is_external
            and profile.eu_data_zone_capable
        ):
            candidates.append(profile)
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one enabled external EU profile for {model_code!r}; found {len(candidates)}."
        )
    profile = candidates[0]
    enabled_credentials = [
        credential
        for credential in store.list_ai_model_credentials(provider_id=profile.provider_id)
        if credential.enabled
    ]
    if not enabled_credentials:
        raise RuntimeError(
            f"No enabled credential is configured for E2E model provider {profile.provider_id!r}."
        )
    previous = store.get_ai_model_user_override(user_id=paid_user_id)
    reason = "Required production post-deployment E2E model route for issue #646."
    override = store.upsert_ai_model_user_override(
        user_id=paid_user_id,
        model_profile_id=profile.model_profile_id,
        admin_user_id=E2E_AUDIT_ACTOR_ID,
        reason=reason,
    )
    if previous is None or previous.model_profile_id != override.model_profile_id or not previous.enabled:
        store.record_ai_model_admin_audit_event(
            admin_user_id=E2E_AUDIT_ACTOR_ID,
            admin_email="post-deployment-e2e@jurisdigta.eu",
            action="user_override.create" if previous is None else "user_override.update",
            entity_type="ai_model_user_override",
            entity_id=paid_user_id,
            old_value_summary=(
                {}
                if previous is None
                else {
                    "model_profile_id": previous.model_profile_id,
                    "enabled": previous.enabled,
                }
            ),
            new_value_summary={
                "model_profile_id": override.model_profile_id,
                "enabled": override.enabled,
            },
            reason=reason,
        )
    print(
        "configured: "
        f"{E2E_TEST_PAID_EMAIL} model_profile_id={profile.model_profile_id} audit_actor={E2E_AUDIT_ACTOR_ID}"
    )


def main() -> int:
    args = _arguments()
    password = os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip()
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(store=store, password=password)
    for user in users:
        action = "created" if user.created else "updated"
        print(f"{action}: {user.email} plan={user.plan_code} user_id={user.user_id}")
        if args.grant_synthetic_model_consent:
            _grant_synthetic_model_consent(store=store, user_id=user.user_id)
    if args.paid_model.strip():
        paid_user = next(user for user in users if user.email == E2E_TEST_PAID_EMAIL)
        _configure_paid_model(
            store=store,
            paid_user_id=paid_user.user_id,
            model_code=args.paid_model,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
