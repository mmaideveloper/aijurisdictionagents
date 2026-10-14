"""Run isolated real PostgreSQL/API/MCP/frontend privacy acceptance services."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import time

from dotenv import load_dotenv
import psycopg
from psycopg import sql

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations
from prepare_issue_635_langgraph_e2e import _seed_synthetic_law
from run_issue_864_e2e_services import _start_service, _wait_for_health, _require_available_port

ROOT = Path(__file__).resolve().parents[1]
API_DATABASE = "postgresql://postgres:postgres@127.0.0.1:5432/issue_389_privacy_e2e"
LAWS_DATABASE = "postgresql://postgres:postgres@127.0.0.1:5432/laws_issue_389_e2e"
API_PORT, MCP_PORT, FRONTEND_PORT = 8389, 8489, 5389


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-current", action="store_true", help="Restart services for the same synthetic run after a code correction")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    previous = None
    if args.reuse_current:
        pointer_data = json.loads((ROOT / "runs/e2e/privacy-389/current.json").read_text())
        evidence = Path(pointer_data["evidence"]).resolve()
        evidence.relative_to((ROOT / "runs/e2e").resolve())
        previous = json.loads((evidence / "result-manifest.json").read_text())
        run_id = previous["run_id"]
    else:
        run_id = "privacy-389-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        evidence = ROOT / "runs/e2e" / run_id
    evidence.mkdir(parents=True, exist_ok=True)
    os.environ.update(DB_OPTION="postgres", DB_CLOUD=API_DATABASE,
                      LAWS_DB_BACKEND="postgres", LAWS_DB_CLOUD=LAWS_DATABASE,
                      STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/privacy-389/files"),
                      LLM_PROVIDER="azurefoundry", EMAIL_DB_OPTION="postgres", EMAIL_DB_CLOUD=API_DATABASE,
                      SYSTEM_EMBEDDING_MODEL_OPTION="local",
                      INTERNAL_MCP_BASE_URL=f"http://127.0.0.1:{MCP_PORT}",
                      INTERNAL_MCP_STARTUP_PROBE_ENABLED="true", LOCAL_LLM_IO_LOGGING="0",
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    shared = secrets.token_urlsafe(48)
    os.environ.update(INTERNAL_MCP_SHARED_SECRET=shared, MCP_API_JWT_SECRET=shared)
    for target, source in (("AZURE_OPENAI_ENDPOINT", "E2E_AZURE_FOUNDRY_ENDPOINT"),
                           ("AZURE_OPENAI_API_VERSION", "E2E_AZURE_FOUNDRY_API_VERSION"),
                           ("AZURE_OPENAI_DEPLOYMENT", "E2E_AZURE_FOUNDRY_DEPLOYMENT"),
                           ("AZURE_OPENAI_API_KEY", "E2E_AZURE_FOUNDRY_API_KEY")):
        value = os.getenv(source, "").strip()
        if value in {"", "unknown-variable"}:
            raise RuntimeError(f"Missing {source}; real acceptance remains pending")
        os.environ[target] = value
    with psycopg.connect("postgresql://postgres:postgres@127.0.0.1:5432/postgres", autocommit=True, connect_timeout=5) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("laws_issue_389_e2e",)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("laws_issue_389_e2e")))
    apply_sql_migrations(project="laws", db_option="postgres", target=LAWS_DATABASE)
    _seed_synthetic_law()
    with psycopg.connect(LAWS_DATABASE) as conn:
        conn.execute((ROOT / "databases/laws-collector/seeds/issue389/01_source_artifact.sql").read_text())
    store = ApiDatabaseStore.from_env()
    store.initialize()
    email = f"{run_id}@example.test"
    # This password belongs only to a disposable synthetic loopback account.
    user = store.get_user(user_id=previous["user_id"]) if previous else store.create_user(email=email, password="Privacy389-Synthetic!", full_name="Synthetic Privacy Test")
    if user.email.lower() != email.lower():
        raise RuntimeError("Reuse is limited to the matching synthetic identity")
    if not previous:
        subscription = store.request_subscription_change(user_id=user.user_id, plan_code="case")
        store.update_subscription_status(subscription_id=subscription.subscription_id, status="paid")
    for task in ("default", "chat_reply"):
        store.upsert_ai_task_route_policy(policy_id=f"privacy389:{task}", task_type=task, plan_code="case",
            preferred_external_model_profile_id="azure_foundry_gpt_4o_mini", allow_external=True,
            require_external_ack=False, require_eu_data_zone=True, fallback_local_on_error=False,
            fallback_local_on_budget=False, priority=10000, enabled=True)
    manifest = {"run_id": run_id, "synthetic_only": True, "user_id": user.user_id, "email": email,
                "api": f"http://127.0.0.1:{API_PORT}", "mcp": f"http://127.0.0.1:{MCP_PORT}",
                "frontend": f"http://127.0.0.1:{FRONTEND_PORT}", "database": "loopback-postgresql",
                "expected_provider": "azure_foundry", "expected_model": "gpt-4o-mini",
                "seed_source_id": "issue-635-civil-code", "retention_days": 7,
                "status": "pending"}
    if previous:
        manifest = {**previous, **manifest}
    (evidence / "result-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    pointer = ROOT / "runs/e2e/privacy-389"
    pointer.mkdir(parents=True, exist_ok=True)
    (pointer / "current.json").write_text(json.dumps({"evidence": str(evidence)}), encoding="utf-8")
    processes: list[subprocess.Popen[str]] = []
    stopped = False

    def stop(_signal: int, _frame: object) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        for name, target, port in (("mcp", "app.mcp_main:app", MCP_PORT), ("api", "app.main:app", API_PORT)):
            _require_available_port(port)
            process = _start_service(name=name, target=target, port=port, environment=os.environ.copy(), evidence_dir=evidence)
            processes.append(process)
            _wait_for_health(f"http://127.0.0.1:{port}/health", process)
            print(f"{name}=ready", flush=True)
        _require_available_port(FRONTEND_PORT)
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node is required for the real frontend")
        frontend = ROOT / "frontend/aijurisdictionfronend"
        environment = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE"}}
        environment.update(VITE_API_BASE_URL=manifest["api"], VITE_API_KEY="aijuris")
        with (evidence / "frontend.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([node, str(frontend / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(FRONTEND_PORT), "--strictPort"], cwd=frontend, env=environment, stdout=log, stderr=log, text=True)
        processes.append(process)
        _wait_for_health(manifest["frontend"], process, timeout_seconds=60)
        print(f"frontend=ready evidence={evidence} synthetic_email={email}", flush=True)
        while not stopped:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("An acceptance service exited")
            time.sleep(1)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
