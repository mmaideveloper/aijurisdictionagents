"""Synthetic-only local #922 acceptance harness. Private auth files are not evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/issue922"
API_DB = "postgresql://postgres:postgres@127.0.0.1:5432/issue922"


def configure() -> None:
    import truststore
    truststore.inject_into_ssl()
    load_dotenv(ROOT / ".env", override=False)
    for suffix in ("ENDPOINT", "API_VERSION", "DEPLOYMENT", "API_KEY"):
        value = os.getenv("E2E_AZURE_FOUNDRY_" + suffix, "")
        if value in {"", "unknown-variable"}:
            raise RuntimeError("Missing E2E_AZURE_FOUNDRY_" + suffix)
        os.environ["AZURE_OPENAI_" + suffix] = value
    os.environ.update(DB_OPTION="postgres", DB_CLOUD=API_DB,
                      LLM_PROVIDER="azurefoundry", STORAGE_OPTION="local",
                      STORE_LOCAL=str(ROOT / "runs/storage/issue922/files"),
                      CASE_ENCRYPTION_KEY_FILE=str(OUTPUT / "test-keyring.json"),
                      API_KEY="aijuris", LOCAL_LLM_IO_LOGGING="0",
                      INTERNAL_MCP_BASE_URL="http://127.0.0.1:8923",
                      INTERNAL_MCP_SHARED_SECRET="issue922-loopback-synthetic-only",
                      LAWS_DB_BACKEND="postgres",
                      LAWS_DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5433/issue922_e2e_laws",
                      EMAIL_DB_OPTION="postgres", EMAIL_DB_CLOUD=API_DB)


def setup() -> None:
    import base64
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from reportlab.pdfgen.canvas import Canvas
    OUTPUT.mkdir(parents=True, exist_ok=True)
    keyring = OUTPUT / "test-keyring.json"
    if not keyring.exists():
        keyring.write_text(json.dumps({"active": "synthetic-e2e", "keys": {"synthetic-e2e": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()}}))
    canvas = Canvas(str(OUTPUT / "synthetic-source.pdf"))
    for index, line in enumerate(("SYNTHETIC CASE DOCUMENT - NOT A REAL AGREEMENT", "Loan principal: EUR 7319. Control identifier: BLUE-922.", "Synthetic debtor owes synthetic creditor this principal.", "This fixture refers to Civil Code section 569: confirmation of debt payment.")):
        canvas.drawString(50, 780 - 35 * index, line)
    canvas.save()
    from aijurisdictionagents.api_db import ApiDatabaseStore
    from aijurisdictionagents.privacy import PrivacyControls, CONSENT_VERSION
    from aijurisdictionagents.case_exports import now
    from prepare_issue_635_langgraph_e2e import _seed_synthetic_law, SYNTHETIC_LAW_ID
    from aijurisdictionagents.db_migrations import apply_sql_migrations
    apply_sql_migrations(project="laws", db_option="postgres", target=os.environ["LAWS_DB_CLOUD"])
    _seed_synthetic_law()
    store = ApiDatabaseStore.from_env()
    store.initialize()
    run_id = "issue922-" + uuid4().hex[:10]
    identities = []
    for role in ("owner", "other", "admin"):
        user = store.create_user(email=f"{run_id}-{role}@example.invalid", password="Synthetic-922-test-only!", full_name=f"Synthetic {role}")
        subscription = store.request_subscription_change(user_id=user.user_id, plan_code="premium")
        store.update_subscription_status(subscription_id=subscription.subscription_id, status="paid")
        PrivacyControls(store).consent(user.user_id, "external_models", True, version=CONSENT_VERSION)
        store.upsert_ai_model_user_override(user_id=user.user_id, model_profile_id="azure_foundry_gpt_4o_mini", admin_user_id=user.user_id, reason="Synthetic real-model acceptance")
        if role == "admin":
            with store._connect() as conn:
                store._execute(conn, "UPDATE users SET role = 'admin' WHERE user_id = ?", (user.user_id,))
                store._execute(conn, "INSERT INTO case_export_permissions VALUES (?, ?)", (user.user_id, now()))
        identities.append({"userId": user.user_id, "email": user.email, "name": user.full_name, "role": "admin" if role == "admin" else "user", "testRole": role})
    (OUTPUT / "input-manifest.json").write_text(json.dumps({"runId": run_id, "identities": identities, "sourceId": SYNTHETIC_LAW_ID}, indent=2))
    print("Synthetic users and law seeded; no production data copied")


def authenticate() -> None:
    import httpx
    import psycopg
    manifest = json.loads((OUTPUT / "input-manifest.json").read_text())
    for user in manifest["identities"]:
        device_id = manifest["runId"] + user["testRole"]
        payload = {"email": user["email"], "password": "Synthetic-922-test-only!", "device_id": device_id}
        with httpx.Client(base_url="http://127.0.0.1:8922", headers={"x-api-key": "aijuris"}, timeout=90) as client:
            response = client.post("/v1/users/sign-in", json=payload)
            if response.status_code == 428:
                with psycopg.connect(API_DB) as conn:
                    row = conn.execute("SELECT body FROM email_outbox WHERE recipient = %s ORDER BY created_at DESC LIMIT 1", (user["email"],)).fetchone()
                match = re.search(r"login code is: (\d+)", row[0]) if row else None
                if not match:
                    raise RuntimeError("Synthetic login verification unavailable")
                payload["verification_code"] = match.group(1)
                response = client.post("/v1/users/sign-in", json=payload)
            if response.status_code != 200 or not response.json().get("device_auth_token"):
                raise RuntimeError(f"Synthetic login failed HTTP {response.status_code}")
            private = {**user, "deviceId": device_id, "deviceAuthToken": response.json()["device_auth_token"]}
            (OUTPUT / f"private-{user['testRole']}.json").write_text(json.dumps(private))
    print("Synthetic users authenticated through real API; credentials redacted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["setup", "authenticate", "api", "mcp"])
    args = parser.parse_args()
    configure()
    if args.mode == "setup":
        setup()
    elif args.mode == "authenticate":
        authenticate()
    else:
        import uvicorn
        os.chdir(ROOT / "api/aijuristiction-api")
        uvicorn.run("app.main:app" if args.mode == "api" else "app.mcp_main:app", host="127.0.0.1", port=8922 if args.mode == "api" else 8923)
