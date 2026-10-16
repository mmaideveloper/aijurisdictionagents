"""Prepare synthetic local PostgreSQL and start real API/MCP for #661.

Run the approved import_e2e_model_credentials_from_server.ps1 helper first.
Credentials are loaded from ignored .env and never printed. No remote data is read.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import time
from uuid import uuid4

from dotenv import load_dotenv
import httpx
import psycopg

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_PAID_EMAIL, provision_e2e_test_users
from aijurisdictionagents.db_migrations import apply_sql_migrations
from aijurisdictionagents.privacy import CONSENT_VERSION, PrivacyControls
from run_issue_810_e2e_services import _require_available_port, _start_service, _wait_for_health

ROOT = Path(__file__).resolve().parents[1]
API_DB = "postgresql://postgres:synthetic661@127.0.0.1:55461/issue661_e2e_api"
LAWS_DB = "postgresql://postgres:synthetic661@127.0.0.1:55461/issue661_e2e_laws"


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    output = ROOT / "runs/issue661"
    output.mkdir(parents=True, exist_ok=True)
    run_id = f"issue661-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:6]}"
    env = os.environ.copy()
    env.update(DB_OPTION="postgres", DB_CLOUD=API_DB, LAWS_DB_BACKEND="postgres",
               LAWS_DB_CLOUD=LAWS_DB, STORAGE_OPTION="local",
               STORE_LOCAL=str(ROOT / "runs/storage/issue661/files"), LLM_PROVIDER="azurefoundry",
               INTERNAL_MCP_BASE_URL="http://127.0.0.1:8662", INTERNAL_MCP_SHARED_SECRET=secrets.token_urlsafe(40),
               MCP_API_JWT_SECRET=secrets.token_urlsafe(40), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               LOCAL_LLM_IO_LOGGING="0", CHAT_EMBEDDING_TIMEOUT_SECONDS="5")
    for key in ("ENDPOINT", "API_VERSION", "DEPLOYMENT", "API_KEY"):
        value = env.get(f"E2E_AZURE_FOUNDRY_{key}", "")
        if value in {"", "unknown-variable"}:
            raise RuntimeError(f"Missing approved E2E_AZURE_FOUNDRY_{key}")
        env[f"AZURE_OPENAI_{key}"] = value
    os.environ.update(env)
    apply_sql_migrations(project="laws", db_option="azure", target=LAWS_DB)
    source_id = f"{run_id}-law"
    parameters = {"id": source_id, "version": source_id + "-v1", "metadata": source_id + "-meta",
                  "artifact": source_id + "-html", "title": "Syntetický zákon o nástrojoch právneho asistenta",
                  "text": "§ 1 Syntetický test: právny asistent overí zdroj, uchová citáciu a vyžaduje ľudský dohľad. Nejde o skutočný zákon."}
    with psycopg.connect(LAWS_DB) as conn:
        sql = (ROOT / "databases/laws-collector/seeds/issue661/seed.sql").read_text(encoding="utf-8")
        # Psycopg extended protocol cannot bind a multi-command prepared query.
        for statement in sql.split(";"):
            if statement.strip():
                conn.execute(statement, parameters)
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(store=store, password=env["JURISDIGTA_E2E_TEST_USER_PASSWORD"])
    user = next(row for row in users if row.email == E2E_TEST_PAID_EMAIL)
    PrivacyControls(store).consent(user.user_id, "external_models", True, version=CONSENT_VERSION, country="SK")
    for task_type in ("default", "chat_reply"):
        store.upsert_ai_task_route_policy(policy_id=f"661:{task_type}", task_type=task_type,
            plan_code="case", preferred_external_model_profile_id="azure_foundry_gpt_4o_mini",
            allow_external=True, require_external_ack=False, require_eu_data_zone=True,
            fallback_local_on_error=False, fallback_local_on_budget=False, priority=10000, enabled=True)
    manifest = {"runId": run_id, "sourceId": source_id, "email": user.email, "userId": user.user_id,
                "syntheticOnly": True, "retention": "Delete within seven days; remove isolated databases and files.",
                "services": ["frontend:8663", "api:8661", "mcp:8662", "local-postgresql:55461"],
                "expectedProvider": "azure_foundry", "expectedModel": "gpt-4o-mini"}
    (output / "input-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    processes = []
    try:
        for name, target, port in (("mcp", "app.mcp_main:app", 8662), ("api", "app.main:app", 8661)):
            _require_available_port(port)
            process = _start_service(name=name, target=target, port=port, environment=env, evidence_dir=output)
            processes.append(process)
            _wait_for_health(f"http://127.0.0.1:{port}/health", process)
        response = httpx.post("http://127.0.0.1:8662/mcp", headers={
            "X-JurisDigta-Internal-MCP-Secret": env["INTERNAL_MCP_SHARED_SECRET"]},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "searchLaws", "arguments": {"query": "661/2026", "limit": 3}}}, timeout=30)
        response.raise_for_status()
        assert source_id in response.text, "Synthetic source missing from direct MCP"
        (output / "direct-mcp.json").write_text(json.dumps({"passed": True, "sourceId": source_id}), encoding="utf-8")
        print(f"Real local API/MCP ready; direct PostgreSQL source verified; run={run_id}", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(1)
    finally:
        for process in processes:
            process.terminate()


if __name__ == "__main__":
    main()
