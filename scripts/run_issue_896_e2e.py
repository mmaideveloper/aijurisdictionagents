"""Prepare and run real local #896 services; synthetic records, no secret output."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from dotenv import load_dotenv
import httpx
import psycopg
from reportlab.pdfgen import canvas

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import provision_e2e_test_users
from aijurisdictionagents.db_migrations import apply_sql_migrations
from run_issue_864_e2e_services import _require_available_port, _start_service, _wait_for_health

ROOT = Path(__file__).resolve().parents[1]
API_DB = "postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction_e2e_896"
LAWS_DB = "postgresql://postgres:postgres@127.0.0.1:5432/laws_e2e_896"
OUTPUT = ROOT / "runs/e2e/issue896"
SOURCE_ID = "issue-896-synthetic-security"


def prepare(environment: dict[str, str], sources_only: bool = False) -> None:
    apply_sql_migrations(project="laws", db_option="postgres", target=LAWS_DB)
    now = datetime.now(timezone.utc)
    seed = ROOT / "databases/laws-collector/seeds/issue896"
    title = "Synthetic E2E software security GDPR 2016/679 — NOT actual legislation"
    text = "§ 32\nSynthetic E2E security requirement: personal-data software must restrict access to authorized roles, assess processing risk, protect data in transit and document proportionate safeguards. ISSUE896_SECURITY_MARKER."
    with psycopg.connect(LAWS_DB) as conn:
        for filename, arguments in [
            ("01_seed.sql", (SOURCE_ID,)),
            ("02_seed.sql", (SOURCE_ID, title, title, now, now, now, now, now)),
            ("03_seed.sql", (SOURCE_ID, now, now, now)),
            ("04_seed.sql", (SOURCE_ID, "2016/679 GDPR software security", title, now, now)),
            ("05_seed.sql", (SOURCE_ID, text, len(text.encode()), now, now)),
            ("06_seed.sql", ("issue896-security-32", "paragraf-32", "Synthetic security", text, 32, now)),
        ]:
            conn.execute((seed / filename).read_text(encoding="utf-8-sig"), arguments)
        # Additional reviewed synthetic scope fixtures. These are explicitly not
        # actual legislative texts or evidence of real regulatory compliance.
        for key, year, number, label, requirement in [
            ("ai", 2024, 1689, "AI Act", "For AI software assess risk, document intended purpose, validate robustness and accuracy, and provide human oversight."),
            ("mdr", 2017, 745, "MDR zdravotnícke pomôcky", "For software with an intended medical purpose document device qualification, risk management, clinical evidence, safety verification and human review."),
            ("ivdr", 2017, 746, "IVDR in vitro diagnostika", "For software interpreting human specimen information document IVD qualification, performance evidence, risk management and verification."),
        ]:
            prefix = f"issue-896-{key}"
            identifier = f"{prefix}-synthetic-source"
            synthetic_title = f"Synthetic {label} {year}/{number} — NOT actual legislation"
            body = f"§ 1\nSynthetic E2E requirement: {requirement} ISSUE896_{key.upper()}_MARKER."
            url = f"https://eur-lex.europa.eu/eli/reg/{year}/{number}/oj"
            for filename, arguments in [
                ("01_seed.sql", (identifier,)),
                ("02_seed.sql", (identifier, synthetic_title, synthetic_title, now, now, now, now, now)),
                ("03_seed.sql", (identifier, now, now, now)),
                ("04_seed.sql", (identifier, f"{year}/{number} {label}", synthetic_title, now, now)),
                ("05_seed.sql", (identifier, body, len(body.encode()), now, now)),
                ("06_seed.sql", (prefix + "-provision", "paragraf-1", "Synthetic scope requirement", body, 1, now)),
            ]:
                statement = (seed / filename).read_text(encoding="utf-8-sig").replace("issue-896", prefix)
                statement = statement.replace("2016, 679", f"{year}, {number}")
                statement = statement.replace("https://eur-lex.europa.eu/eli/reg/2016/679/oj", url)
                conn.execute(statement, arguments)
    if sources_only:
        print("Four synthetic regulatory source fixtures prepared; not actual legislation.", flush=True)
        return
    store = ApiDatabaseStore.from_env()
    store.initialize()
    sys.path.insert(0, str(ROOT / "api/aijuristiction-api"))
    from app.case_types.models import CaseTypeUpdateRequest
    from app.document_templates.store import DocumentTemplateStore
    from app.software_assessment.models import CASE_TYPE_KEY
    from app.software_assessment.workflow import DEFAULT_PROMPT
    DocumentTemplateStore.from_env().update_case_type(case_type_key=CASE_TYPE_KEY, jurisdiction="SK",
        payload=CaseTypeUpdateRequest(prompt_text=DEFAULT_PROMPT))
    # The password is a public synthetic fixture, not a production credential.
    users = provision_e2e_test_users(store=store, password="Synthetic-896-test-only!")
    user = next(item for item in users if item.plan_code == "case")
    for task in ("default", "chat_reply", "software_regulatory_assessment"):
        store.upsert_ai_task_route_policy(policy_id=f"issue896:{task}", task_type=task, plan_code="case",
            preferred_external_model_profile_id="azure_foundry_gpt_4o_mini", allow_external=True,
            require_external_ack=True, require_eu_data_zone=True, fallback_local_on_error=False,
            fallback_local_on_budget=False, priority=10000, enabled=True)
    payload = io.BytesIO()
    writer = canvas.Canvas(payload)
    writer.drawString(40, 800, "Synthetic supplier architecture. Purpose: contact administration.")
    writer.showPage()
    writer.drawString(40, 800, "Everyone can read all contact records. There are no access restrictions.")
    writer.drawString(40, 780, "All phone numbers are sent over plain HTTP on the public internet.")
    writer.save()
    (OUTPUT / "supplier.pdf").write_bytes(payload.getvalue())
    (OUTPUT / "input-manifest.json").write_text(json.dumps({"run_id": f"issue896-{now.strftime('%Y%m%dT%H%M%SZ')}",
        "synthetic_user_id": user.user_id, "synthetic_email": user.email, "source_id": SOURCE_ID,
        "retention": "Delete ignored evidence within seven days; remove synthetic cases/files after validation."}, indent=2))
    print("Synthetic PostgreSQL source/account/document prepared; credentials redacted.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--sources-only", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    environment = os.environ.copy()
    environment.update(DB_OPTION="postgres", DB_CLOUD=API_DB, LAWS_DB_BACKEND="postgres", LAWS_DB_CLOUD=LAWS_DB,
        STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/issue896/files"), LLM_PROVIDER="azurefoundry",
        INTERNAL_MCP_BASE_URL="http://127.0.0.1:8286", INTERNAL_MCP_STARTUP_PROBE_ENABLED="true",
        LOCAL_LLM_IO_LOGGING="0", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        LOCAL_AUTH_ACCEPT_ANY_CODE="true", EMAIL_TRANSPORT="file", EMAIL_DB_OPTION="postgres", EMAIL_DB_CLOUD=API_DB)
    for name in ("ENDPOINT", "API_VERSION", "DEPLOYMENT", "API_KEY"):
        value = environment.get(f"E2E_AZURE_FOUNDRY_{name}", "")
        if value in {"", "unknown-variable"}:
            raise RuntimeError(f"Missing E2E_AZURE_FOUNDRY_{name}")
        environment[f"AZURE_OPENAI_{name}"] = value
    secret = secrets.token_urlsafe(48)
    environment.update(INTERNAL_MCP_SHARED_SECRET=secret, MCP_API_JWT_SECRET=secret)
    os.environ.update(environment)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.prepare or args.sources_only:
        prepare(environment, sources_only=args.sources_only)
        return
    processes = []
    try:
        for name, target, port in [("mcp", "app.mcp_main:app", 8286), ("api", "app.main:app", 8186)]:
            _require_available_port(port)
            process = _start_service(name=name, target=target, port=port, environment=environment, evidence_dir=OUTPUT)
            processes.append(process)
            _wait_for_health(f"http://127.0.0.1:{port}/health", process)
            print(f"service={name} ready", flush=True)
        response = httpx.post("http://127.0.0.1:8286/mcp", headers={"X-JurisDigta-Internal-MCP-Secret": secret},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "getLawText",
                "arguments": {"document_id": SOURCE_ID, "section_start": 32, "section_end": 32, "max_chars": 15000}}}, timeout=60)
        response.raise_for_status()
        if "ISSUE896_SECURITY_MARKER" not in response.text:
            raise RuntimeError("Direct MCP query did not return the seeded source.")
        print("Direct MCP synthetic source check passed.", flush=True)
        _require_available_port(5186)
        frontend_env = dict(environment, VITE_API_BASE_URL="http://127.0.0.1:8186", VITE_API_KEY="aijuris")
        npm = subprocess.Popen(["cmd", "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5186"],
            cwd=ROOT / "frontend/aijurisdictionfronend", env=frontend_env,
            stdout=(OUTPUT / "frontend.log").open("w"), stderr=subprocess.STDOUT)
        processes.append(npm)
        print("Frontend starting at loopback port 5186; synthetic authentication, real model and databases.", flush=True)
        while all(item.poll() is None for item in processes):
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
