"""Execute an approved erasure request; external cleanup remains explicitly pending."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "api/aijuristiction-api"))

from aijurisdictionagents.api_db import ApiDatabaseStore  # noqa: E402
from aijurisdictionagents.privacy import PrivacyControls, PrivacyDenied, utcnow  # noqa: E402
from aijurisdictionagents.privacy_retention import cleanup_files, purge_case  # noqa: E402


def execute(request_id: str, store: ApiDatabaseStore) -> dict[str, object]:
    from app.case_workflows.store import CaseWorkflowStore
    controls = PrivacyControls(store)
    request = next((item for item in controls.requests() if item["request_id"] == request_id), None)
    if not request or request["status"] != "approved_pending_execution":
        raise PrivacyDenied("approved_privacy_request_required")
    user_id = str(request["user_id"])
    if controls.state(user_id)["legal_hold"]:
        raise PrivacyDenied("legal_hold_requires_owner_resolution")
    controls.restrict(user_id, True)
    workflows = CaseWorkflowStore.from_env()
    purged = 0
    for case in store.list_cases(user_id=user_id, include_deleted=True):
        if controls.state(user_id)["legal_hold"]:
            raise PrivacyDenied("legal_hold_requires_owner_resolution")
        workflows.delete_case_workflows(case_id=case.case_id, user_id=user_id)
        purged += int(purge_case(store, case.case_id, user_id))
    files = cleanup_files(store)
    # A disabled, deidentified tombstone preserves accounting references and the
    # restore suppression identity. It is not claimed to be irreversible anonymization.
    with store._connect() as conn:
        hold = store._fetchone(conn, "SELECT legal_hold FROM privacy_subject_state WHERE user_id = ?", (user_id,))
        if hold and hold[0]:
            raise PrivacyDenied("legal_hold_requires_owner_resolution")
        store._execute(conn, "UPDATE users SET email = ?, full_name = 'Erased account', phone_number = NULL, first_name = NULL, last_name = NULL, address = NULL, city = NULL, country = NULL, zip_code = NULL, tax_number = NULL, identity_card_number = NULL, date_of_birth = NULL, social_security_number = NULL, password_hash = '', mcp_api_key_hash = NULL, mcp_api_key_expires_at = NULL, is_enabled = 0 WHERE user_id = ?", (f"erased-{user_id}@invalid.example", user_id))
        for table in ("device_auth_tokens", "mcp_oauth_authorization_codes", "mcp_otp_verifications", "user_mfa_settings", "mfa_login_challenges", "ai_model_group_users", "ai_model_user_overrides"):
            store._execute(conn, f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        store._execute(conn, "DELETE FROM privacy_consent_events WHERE user_id = ?", (user_id,))
        store._execute(conn, "UPDATE privacy_requests SET status = 'pending_external_cleanup', updated_at = ? WHERE request_id = ?", (utcnow(), request_id))
    controls.event("dsar_request", "pending", count=purged)
    return {"status": "pending_external_cleanup", "purged_cases": purged, **files,
            "remaining": ["accounting and subscriptions legal-owner review", "email and external processor cleanup", "log/telemetry cleanup", "backup expiry and restore suppression", "live API cache eviction/restart"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    store = ApiDatabaseStore.from_env()
    store.initialize()
    if not args.execute:
        controls = PrivacyControls(store)
        request = next((item for item in controls.requests() if item["request_id"] == args.request_id), None)
        print(json.dumps({"mode": "dry_run", "status": request["status"] if request else "not_found"}))
        return
    print(json.dumps(execute(args.request_id, store)))


if __name__ == "__main__":
    main()
