"""Prepare synthetic identities and case data for issue #864 real E2E."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import load_dotenv
import argparse
import httpx
import psycopg
import re

from run_issue_864_e2e_services import API_DATABASE_URL, LAWS_DATABASE_URL
from psycopg import sql
from aijurisdictionagents.db_migrations import apply_sql_migrations

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import (
    E2E_TEST_PAID_EMAIL,
    provision_e2e_test_users,
)
from aijurisdictionagents.llm.routing import get_routed_llm_client
from prepare_issue_635_langgraph_e2e import _seed_synthetic_law


REPO_ROOT = Path(__file__).resolve().parents[1]
ADMIN_EMAIL = "issue-864-admin@jurisdigta.eu"


def configure() -> None:
    load_dotenv(REPO_ROOT / ".env", override=False)
    os.environ.update(DB_OPTION="postgres", DB_CLOUD=API_DATABASE_URL,
                      LAWS_DB_BACKEND="postgres", LAWS_DB_CLOUD=LAWS_DATABASE_URL)


def setup() -> int:
    configure()
    with psycopg.connect("postgresql://postgres:postgres@127.0.0.1:5432/postgres",
                         autocommit=True, connect_timeout=3) as conn:
        for target in (API_DATABASE_URL, LAWS_DATABASE_URL):
            name = urlsplit(target).path.lstrip("/")
            if conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone() is None:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    from app.flow_packs.store import FlowPackStore
    FlowPackStore.from_env()
    api_migrations = apply_sql_migrations(project="api", db_option="postgres", target=API_DATABASE_URL)
    laws_migrations = apply_sql_migrations(project="laws", db_option="postgres", target=LAWS_DATABASE_URL)
    ApiDatabaseStore.from_env().initialize()
    print(f"Isolated local PostgreSQL ready; migrations api={len(api_migrations)} laws={len(laws_migrations)}")
    return 0


def main() -> int:
    configure()
    parsed = urlsplit(API_DATABASE_URL)
    if os.getenv("DB_OPTION", "").strip().lower() != "postgres":
        raise RuntimeError("Issue #864 final E2E requires DB_OPTION=postgres")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Issue #864 final E2E requires loopback PostgreSQL")
    _seed_synthetic_law()
    with psycopg.connect(LAWS_DATABASE_URL) as conn:
        conn.execute((REPO_ROOT / "databases/laws-collector/seeds/issue864/01_source_artifact.sql").read_text())
    password = os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip()
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(store=store, password=password)
    workflow_user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    deployment = os.getenv("E2E_AZURE_FOUNDRY_DEPLOYMENT", "").strip()
    profiles = {"gpt-5-mini": "azurefoundryeu:gpt-5-mini", "gpt-4o-mini": "azure_foundry_gpt_4o_mini"}
    if deployment not in profiles:
        raise RuntimeError("Bootstrap an approved E2E_AZURE_FOUNDRY_DEPLOYMENT before preparation")
    for task_type in ("default", "chat_reply"):
        store.upsert_ai_task_route_policy(
            policy_id=f"issue864:{task_type}:case", task_type=task_type, plan_code="case",
            preferred_external_model_profile_id=profiles[deployment], allow_external=True,
            require_external_ack=False, require_eu_data_zone=True,
            fallback_local_on_error=False, fallback_local_on_budget=False,
            priority=10000, enabled=True,
        )
    admin = store.find_user_by_email(email=ADMIN_EMAIL)
    if admin is None:
        admin = store.create_user(
            email=ADMIN_EMAIL,
            password=password,
            full_name="JurisDigta Synthetic LangGraph Audit Admin",
        )
    store.update_admin_user(user_id=admin.user_id, role="admin", is_enabled=True)
    run_id = (
        "issue-864-langgraph-audit-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    )
    route = get_routed_llm_client(
        store=store,
        user_id=workflow_user.user_id,
        user_email=workflow_user.email,
        task_type="chat_reply",
    )
    if "azure" not in route.provider.lower() or route.route_type == "mock":
        raise RuntimeError("Real Azure Foundry model route is required; mock is prohibited")
    evidence_root = REPO_ROOT / "runs" / "e2e" / "issue-864-langgraph-audit" / run_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "syntheticOnly": True,
        "runId": run_id,
        "correlationId": f"corr-{run_id}",
        "sessionId": f"session-{run_id}",
        "workflowUser": {
            "userId": workflow_user.user_id,
            "email": workflow_user.email,
        },
        "adminUser": {
            "userId": admin.user_id,
            "email": admin.email,
            "name": "JurisDigta Synthetic LangGraph Audit Admin",
            "role": "admin",
            "isEnabled": True,
        },
        "caseTitle": f"[{run_id}] Generic LangGraph audit",
        "evidenceRoot": str(evidence_root),
        "expectedLegalSourceId": "issue-635-civil-code",
        "expectedProvider": route.provider,
        "expectedModel": route.model,
        "database": "loopback-postgresql",
    }
    manifest_path = evidence_root / "input-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    pointer = REPO_ROOT / "runs" / "e2e" / "issue864"
    pointer.mkdir(parents=True, exist_ok=True)
    (pointer / "input-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    print(f"manifest={manifest_path}")
    print(f"evidence={evidence_root}")
    print(f"provider={route.provider} model={route.model} route_type={route.route_type}")
    return 0


def authenticate() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    pointer = REPO_ROOT / "runs" / "e2e" / "issue864"
    manifest = json.loads((pointer / "input-manifest.json").read_text())
    authenticated = {}
    with httpx.Client(base_url="http://127.0.0.1:8264", timeout=90,
                      headers={"x-api-key": os.getenv("API_KEY", "aijuris")}) as client:
        for name in ("workflowUser", "adminUser"):
            identity = manifest[name]
            device = f"{manifest['runId']}-{name}"
            payload = {"email": identity["email"], "password": os.environ["JURISDIGTA_E2E_TEST_USER_PASSWORD"],
                       "device_id": device}
            response = client.post("/v1/users/sign-in", json=payload)
            if response.status_code == 428:
                with psycopg.connect(API_DATABASE_URL) as conn:
                    row = conn.execute("SELECT body FROM email_outbox WHERE recipient=%s ORDER BY created_at DESC LIMIT 1",
                                       (identity["email"],)).fetchone()
                code = re.search(r"login code is: (\d+)", row[0]) if row else None
                if not code:
                    raise RuntimeError("Synthetic email verification unavailable; values redacted")
                payload["verification_code"] = code.group(1)
                response = client.post("/v1/users/sign-in", json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"Synthetic login failed: HTTP {response.status_code}; values redacted")
            user = response.json()
            if user.get("mfa_required") or user.get("mfa_token"):
                challenge = user["mfa_token"]
                sent = client.post("/v1/users/sign-in/mfa/send-email-code", json={"mfa_token": challenge})
                if sent.status_code != 202:
                    raise RuntimeError("Synthetic MFA email challenge unavailable")
                with psycopg.connect(API_DATABASE_URL) as conn:
                    row = conn.execute("SELECT body FROM email_outbox WHERE recipient=%s ORDER BY created_at DESC LIMIT 1",
                                       (identity["email"],)).fetchone()
                code = re.search(r"login code is: (\d+)", row[0]) if row else None
                if not code:
                    raise RuntimeError("Synthetic MFA verification unavailable; values redacted")
                verified = client.post("/v1/users/sign-in/mfa/verify", json={
                    "mfa_token": challenge, "method": "email", "verification_code": code.group(1),
                    "device_id": device,
                })
                if verified.status_code != 200:
                    raise RuntimeError("Synthetic MFA verification failed; values redacted")
                user = verified.json()
            if not user.get("device_auth_token") or user.get("user_id") != identity["userId"]:
                raise RuntimeError("Real synthetic device authentication is required")
            authenticated[name] = {"userId": user["user_id"], "email": user["email"],
                                   "name": user["full_name"], "role": user.get("role", "user"),
                                   "isEnabled": user.get("is_enabled", True), "deviceId": device,
                                   "deviceAuthToken": user["device_auth_token"]}
    (pointer / "private-auth.json").write_text(json.dumps(authenticated), encoding="utf-8")
    print("Synthetic users authenticated through real API; values redacted.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authenticate", action="store_true")
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()
    try:
        result = setup() if args.setup else authenticate() if args.authenticate else main()
    except psycopg.Error as exc:
        print(f"Local PostgreSQL prerequisite failed: {type(exc).__name__}; connection details redacted.")
        result = 2
    raise SystemExit(result)
