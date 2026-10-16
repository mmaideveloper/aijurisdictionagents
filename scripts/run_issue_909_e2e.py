"""Prepare isolated synthetic IT acceptance services; never print credentials.

Bootstrap the approved credential into aijurisdiction_e2e_909 first, then run this
script. The browser creates the case; no mocked UI or model is used here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

from dotenv import load_dotenv
import httpx
import psycopg

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations
from aijurisdictionagents.privacy import CONSENT_VERSION, PrivacyControls
from run_issue_864_e2e_services import _require_available_port, _start_service, _wait_for_health

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/e2e/issue909"
API_DB = "postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction_e2e_909"
LAWS_DB = "postgresql://postgres:postgres@127.0.0.1:5432/laws_e2e_909"


def prepare(run_id: str) -> dict[str, object]:
    apply_sql_migrations(project="laws", db_option="postgres", target=LAWS_DB)
    now = datetime.now(timezone.utc)
    source_id = run_id + "-security"
    seed = ROOT / "databases/laws-collector/seeds/issue896"
    title = "Synthetic GDPR organizational IT security — NOT actual legislation"
    text = ("Article 32\nSynthetic E2E requirement: for a shared hospital data warehouse assess processing risk, "
            "restrict access per legal entity and purpose, and document proportionate security safeguards. "
            "ISSUE909_SECURITY_MARKER. This is a synthetic fixture, not a statement of actual law.")
    with psycopg.connect(LAWS_DB) as conn:
        conn.execute((ROOT / "databases/laws-collector/seeds/issue909/cleanup.sql").read_text(encoding="utf-8"))
        for filename, arguments in [
            ("01_seed.sql", (source_id,)),
            ("02_seed.sql", (source_id, title, title, now, now, now, now, now)),
            ("03_seed.sql", (source_id, now, now, now)),
            ("04_seed.sql", (source_id, "GDPR 2016/679 organizational IT", title, now, now)),
            ("05_seed.sql", (source_id, text, len(text.encode()), now, now)),
            ("06_seed.sql", (run_id + "-provision", "paragraf-32", "Synthetic warehouse security", text, 32, now)),
        ]:
            statement = (seed / filename).read_text(encoding="utf-8-sig").replace("issue-896", run_id).replace("issue896", run_id)
            conn.execute(statement, arguments)
    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(email=run_id + "@example.test", password="Synthetic-909-test-only!",
                             full_name="Synthetic IT Reviewer", country="SK")
    # Synthetic fixture consent exercises the actual privacy policy; never alter
    # another account or disable the policy to make the acceptance run succeed.
    PrivacyControls(store).consent(user.user_id, "external_models", True, version=CONSENT_VERSION, country="SK")
    subscription = store.request_subscription_change(user_id=user.user_id, plan_code="case")
    store.update_subscription_status(subscription_id=subscription.subscription_id, status="paid")
    for task in ("default", "chat_reply", "software_regulatory_assessment"):
        store.upsert_ai_task_route_policy(policy_id=f"{run_id}:{task}", task_type=task, plan_code="case",
            preferred_external_model_profile_id="azure_foundry_gpt_4o_mini", allow_external=True,
            require_external_ack=True, require_eu_data_zone=True, fallback_local_on_error=False,
            fallback_local_on_budget=False, priority=10000, enabled=True)
    return dict(run_id=run_id, synthetic_email=user.email, synthetic_user_id=user.user_id,
                expected_source_ids=[source_id], databases="branch-local-loopback-postgresql",
                synthetic_legal_fixtures_not_actual_legislation=True,
                retention="Delete ignored evidence within seven days; clean cases, files and synthetic source records after validation.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse", action="store_true", help="Reuse this run's isolated synthetic accounts and source IDs")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    environment = os.environ.copy()
    environment.update(DB_OPTION="postgres", DB_CLOUD=API_DB, LAWS_DB_BACKEND="postgres", LAWS_DB_CLOUD=LAWS_DB,
        STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/issue909/files"), LLM_PROVIDER="azurefoundry",
        API_KEY="aijuris", INTERNAL_MCP_BASE_URL="http://127.0.0.1:8299", INTERNAL_MCP_STARTUP_PROBE_ENABLED="true",
        LOCAL_LLM_IO_LOGGING="0", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", LOCAL_AUTH_ACCEPT_ANY_CODE="true",
        EMAIL_TRANSPORT="file", EMAIL_DB_OPTION="postgres", EMAIL_DB_CLOUD=API_DB)
    for name in ("ENDPOINT", "API_VERSION", "DEPLOYMENT", "API_KEY"):
        value = environment.get(f"E2E_AZURE_FOUNDRY_{name}", "")
        if value in {"", "unknown-variable"}:
            raise RuntimeError(f"Missing E2E_AZURE_FOUNDRY_{name}")
        environment[f"AZURE_OPENAI_{name}"] = value
    secret = secrets.token_urlsafe(48)
    environment.update(INTERNAL_MCP_SHARED_SECRET=secret, MCP_API_JWT_SECRET=secret)
    os.environ.update(environment)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run_id = "issue909-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()
    manifest = json.loads((OUTPUT / "input-manifest.json").read_text(encoding="utf-8")) if args.reuse else prepare(run_id)
    from app.document_templates.store import DocumentTemplateStore
    from app.case_types.models import CaseTypeUpdateRequest
    from app.software_assessment.organizational_it import CASE_TYPE_KEY, PROMPT
    DocumentTemplateStore.from_env().update_case_type(case_type_key=CASE_TYPE_KEY, jurisdiction="SK",
                                                     payload=CaseTypeUpdateRequest(prompt_text=PROMPT))
    processes: list[subprocess.Popen] = []
    try:
        for name, target, port in [("mcp", "app.mcp_main:app", 8299), ("api", "app.main:app", 8199)]:
            _require_available_port(port)
            process = _start_service(name=name, target=target, port=port, environment=environment, evidence_dir=OUTPUT)
            processes.append(process)
            _wait_for_health(f"http://127.0.0.1:{port}/health", process, timeout_seconds=600)
            print(f"service={name} ready", flush=True)
        response = httpx.post("http://127.0.0.1:8299/mcp", headers={"X-JurisDigta-Internal-MCP-Secret": secret},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "getLawText",
                "arguments": {"document_id": manifest["expected_source_ids"][0], "section_start": 32, "section_end": 32, "max_chars": 15000}}}, timeout=60)
        response.raise_for_status()
        if "ISSUE909_SECURITY_MARKER" not in response.text:
            raise RuntimeError("Direct MCP query did not return the synthetic source")
        manifest.update(direct_mcp_checked=True, local_services={"frontend": 5199, "api": 8199, "mcp": 8299, "postgres": 5432})
        (OUTPUT / "input-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _require_available_port(5199)
        frontend_env = dict(environment, VITE_API_BASE_URL="http://127.0.0.1:8199", VITE_API_KEY="aijuris")
        with (OUTPUT / "frontend.log").open("w") as output:
            process = subprocess.Popen(["cmd", "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5199"],
                cwd=ROOT / "frontend/aijurisdictionfronend", env=frontend_env, stdout=output, stderr=subprocess.STDOUT)
        processes.append(process)
        print("Real-provider synthetic services ready; frontend=http://127.0.0.1:5199", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(1)
    finally:
        for process in reversed(processes):
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
