"""Run isolated real-model reflection services and the browser acceptance example."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from uuid import uuid4

from dotenv import load_dotenv
import httpx

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_PAID_EMAIL, provision_e2e_test_users
import prepare_issue_635_langgraph_e2e as seed
from run_issue_810_e2e_services import _start_service, _wait_for_health, _require_available_port

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "issue-753-synthetic-civil-code"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Keep the isolated services running for manual inspection",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    environment = os.environ.copy()
    for target, source in (
        ("AZURE_OPENAI_ENDPOINT", "E2E_AZURE_FOUNDRY_ENDPOINT"),
        ("AZURE_OPENAI_API_VERSION", "E2E_AZURE_FOUNDRY_API_VERSION"),
        ("AZURE_OPENAI_DEPLOYMENT", "E2E_AZURE_FOUNDRY_DEPLOYMENT"),
        ("AZURE_OPENAI_API_KEY", "E2E_AZURE_FOUNDRY_API_KEY"),
    ):
        value = environment.get(source, "").strip()
        if value in {"", "unknown-variable"}:
            raise RuntimeError(f"Missing {source}; use the approved E2E credential import")
        environment[target] = value
    if environment.get("JURISDIGTA_E2E_TEST_USER_PASSWORD", "") in {"", "unknown-variable"}:
        raise RuntimeError("Missing JURISDIGTA_E2E_TEST_USER_PASSWORD")
    run_id = "issue-753-" + uuid4().hex
    evidence = ROOT / "runs" / "e2e" / "issue-753" / run_id
    evidence.mkdir(parents=True, exist_ok=True)
    shared_secret = secrets.token_urlsafe(48)
    environment.update(
        DB_OPTION="postgres",
        DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/aij_e2e_753_reflection_durable_resume",
        LAWS_DB_BACKEND="postgres",
        LAWS_DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5433/laws_e2e_753_reflection",
        STORAGE_OPTION="local",
        STORE_LOCAL=str(evidence / "files"),
        LLM_PROVIDER="azurefoundry",
        INTERNAL_MCP_BASE_URL="http://127.0.0.1:8073",
        INTERNAL_MCP_SHARED_SECRET=shared_secret,
        MCP_API_JWT_SECRET=shared_secret,
        API_BASE_URL="http://127.0.0.1:8083",
        FRONTEND_BASE_URL="http://127.0.0.1:5173",
        VITE_API_BASE_URL="http://127.0.0.1:8083",
        VITE_API_KEY="aijuris",
        LOCAL_AUTH_ACCEPT_ANY_CODE="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    os.environ.update(environment)
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(
        store=store, password=environment["JURISDIGTA_E2E_TEST_USER_PASSWORD"]
    )
    user = next(item for item in users if item.email == E2E_TEST_PAID_EMAIL)
    from app.case_workflows.store import CaseWorkflowStore

    workflow_store = CaseWorkflowStore.from_env()
    for prior in store.list_cases(user_id=user.user_id):
        if prior.title.startswith("[issue-753-"):
            store.soft_delete_case(case_id=prior.case_id, user_id=user.user_id)
            workflow_store.delete_case_workflows(case_id=prior.case_id, user_id=user.user_id)
    seed.SYNTHETIC_LAW_ID = SOURCE_ID
    seed._seed_synthetic_law()
    manifest = {
        "runId": run_id,
        "syntheticOnly": True,
        "userId": user.user_id,
        "email": user.email,
        "sourceId": SOURCE_ID,
        "evidence": str(evidence),
        "retention": "Delete within seven days",
    }
    (evidence.parent / "active.json").write_text(json.dumps(manifest), encoding="utf-8")
    processes = []
    try:
        for name, target, port in (
            ("mcp", "app.mcp_main:app", 8073),
            ("api", "app.main:app", 8083),
        ):
            _require_available_port(port)
            process = _start_service(
                name=name, target=target, port=port, environment=environment, evidence_dir=evidence
            )
            processes.append(process)
            _wait_for_health(f"http://127.0.0.1:{port}/health", process, timeout_seconds=600)
            print(f"service={name} ready", flush=True)
        direct = httpx.post(
            "http://127.0.0.1:8073/mcp",
            headers={"X-JurisDigta-Internal-MCP-Secret": shared_secret},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "getLawText",
                    "arguments": {"document_id": SOURCE_ID, "max_chars": 3000},
                },
            },
            timeout=60,
        )
        direct.raise_for_status()
        assert "Syntetick" in direct.text or "syntetick" in direct.text
        (evidence / "direct-mcp.json").write_text(
            json.dumps({"sourceId": SOURCE_ID, "matched": True}), encoding="utf-8"
        )
        _require_available_port(5173)
        frontend_log = (evidence / "frontend.log").open("w", encoding="utf-8")
        try:
            frontend = subprocess.Popen(
                [
                    shutil.which("node") or "node",
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                ],
                cwd=ROOT / "frontend/aijurisdictionfronend",
                env=environment,
                stdout=frontend_log,
                stderr=frontend_log,
            )
        finally:
            frontend_log.close()
        processes.append(frontend)
        _wait_for_health("http://127.0.0.1:5173", frontend)
        print(f"services=ready evidence={evidence}", flush=True)
        if args.serve:
            frontend.wait()
            return 0
        result = subprocess.run(
            [
                shutil.which("npx.cmd") or "npx",
                "playwright",
                "test",
                "tests/issue-753-reflection.spec.ts",
                "--output",
                str(evidence / "playwright"),
            ],
            cwd=ROOT / "api/aijuristiction-api/e2e-playwright",
            env=environment,
            check=False,
        )
        if result.returncode:
            return result.returncode
        from pypdf import PdfReader
        import fitz

        pdf_path = evidence / "reflection.pdf"
        pdf = PdfReader(pdf_path)
        assert not pdf.is_encrypted and len(pdf.pages) > 0
        assert "100 EUR" in "\n".join(page.extract_text() or "" for page in pdf.pages)
        with fitz.open(pdf_path) as document:
            document[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(
                evidence / "reflection-page-1.png"
            )
        result_path = evidence / "result-manifest.json"
        manifest = json.loads(result_path.read_text(encoding="utf-8"))
        manifest["pdfValidation"] = "passed"
        manifest["result"] = "passed"
        result_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"real_e2e=passed manifest={result_path}", flush=True)
        return 0
    finally:
        for prior in store.list_cases(user_id=user.user_id):
            if prior.title.startswith("[issue-753-"):
                store.soft_delete_case(case_id=prior.case_id, user_id=user.user_id)
                workflow_store.delete_case_workflows(case_id=prior.case_id, user_id=user.user_id)
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        # Browser failure snapshots can include form values. Never retain them
        # as plain text, even for synthetic accounts with a reusable password.
        for path in evidence.rglob("*"):
            if path.suffix not in {".md", ".json", ".log"}:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            for key in (
                "JURISDIGTA_E2E_TEST_USER_PASSWORD",
                "AZURE_OPENAI_API_KEY",
                "INTERNAL_MCP_SHARED_SECRET",
            ):
                secret = environment.get(key, "")
                if secret:
                    content = content.replace(secret, "[REDACTED]")
            path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
