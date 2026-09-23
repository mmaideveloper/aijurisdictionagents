"""Run the real browser two-line Slovak speech acceptance scenario.

Requires prepared fixtures, loopback services and migrated task PostgreSQL.
Credentials are passed to the browser driver in memory via stdin, never artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", default="http://127.0.0.1:5173")
    parser.add_argument("--api", default="http://127.0.0.1:8080")
    parser.add_argument("--mcp", default="http://127.0.0.1:8070")
    parser.add_argument("--database", default="aij_e2e_525_streaming_stt")
    args = parser.parse_args()
    for url in (args.frontend, args.api, args.mcp):
        if urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Only loopback services are permitted")
    if not args.database.startswith("aij_e2e_") or not args.database.replace("_", "").isalnum():
        raise ValueError("Only task E2E databases are permitted")
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("LLM_PROVIDER", "").lower() == "mock":
        raise ValueError("Mock is not real E2E")
    run_id = "speech-525-" + uuid4().hex[:12]
    output = ROOT / "artifacts" / run_id
    output.mkdir(parents=True, exist_ok=True)
    reference_path = ROOT / "runs/speech-e2e/reference.json"
    if not reference_path.exists():
        (output / "result.json").write_text(json.dumps({"run_id": run_id, "status": "pending",
            "missing": "Real Azure Speech fixture/configuration; run scripts/prepare_speech_e2e.py",
            "retention_days": 7}), encoding="utf-8")
        print("Real speech E2E pending: synthetic fixture is not prepared.")
        return 2
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if reference.get("synthetic") is not True:
        raise ValueError("Synthetic fixture declaration required")
    for url in (args.frontend, args.api + "/health", args.mcp + "/health"):
        if not httpx.get(url, timeout=10).is_success:
            raise ValueError("Required local service unavailable")
    os.environ.update(DB_OPTION="postgres",
        DB_CLOUD=f"postgresql://postgres:postgres@127.0.0.1:5432/{args.database}",
        STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/api/speech-e2e"))
    from aijurisdictionagents.api_db import ApiDatabaseStore
    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(email=f"{run_id}@example.test", password=secrets.token_urlsafe(32),
                             full_name="Synthetic Speech Test")
    case = store.create_case(user_id=user.user_id, company_id=None, title=run_id)
    device_id = run_id
    token = store.issue_device_auth_token(user_id=user.user_id, device_id=device_id)
    # Select the approved real chat route without altering speech routing or other users.
    store.upsert_ai_model_user_override(user_id=user.user_id,
        model_profile_id="azure_foundry_gpt_4o_mini", admin_user_id=user.user_id,
        reason="Isolated synthetic E2E real chat route")
    try:
        route = store.resolve_speech_route(user_id=user.user_id, case_id=case.case_id)
        if route.provider is None or route.provider.provider_type != "azure_speech":
            raise ValueError("Real streaming speech route required")
        payload = {"runId": run_id, "output": str(output), "frontend": args.frontend,
            "api": args.api, "mcp": args.mcp, "caseId": case.case_id,
            "apiKey": os.getenv("API_KEY", "aijuris"),
            "wav": str(ROOT / "runs/speech-e2e/slovak-two-lines.wav"), "lines": reference["lines"],
            "user": {"userId": user.user_id, "email": user.email, "name": "Synthetic Speech Test",
                     "deviceId": device_id, "deviceAuthToken": token, "role": "user"}}
        result = subprocess.run([shutil.which("node") or "node", "e2e/speech-real.mjs"],
            cwd=ROOT / "frontend/aijurisdictionfronend", input=json.dumps(payload), text=True,
            capture_output=True, timeout=300)
        # Deliberately never echo raw subprocess output or payload.
        result_path = output / "result.json"
        manifest = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {"run_id": run_id}
        routes = store.list_ai_model_usage_audit(case_id=case.case_id)
        manifest["chat_routes"] = [{"provider": row.provider, "model": row.model, "status": row.status} for row in routes]
        real_chat = any(row.provider in {"azurefoundry", "azure_foundry"} and row.model and row.status == "ok" and row.audit_metadata.get("model_used") is True for row in routes)
        passed = result.returncode == 0 and real_chat
        manifest["status"] = "passed" if passed else "failed"
        manifest["retention_days"] = 7
        result_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Real speech E2E: {manifest['status']}. Sanitized evidence: {output}")
        return 0 if passed else 1
    finally:
        store.soft_delete_case(case_id=case.case_id, user_id=user.user_id)
        store.update_admin_user(user_id=user.user_id, role="user", is_enabled=False)
        # Revoke credentials immediately; synthetic audit/history follows 7-day evidence retention.
        with store._connect() as conn:
            store._execute(conn, "DELETE FROM device_auth_tokens WHERE user_id = ?", (user.user_id,))
            conn.commit()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Real speech E2E unavailable ({type(exc).__name__}); details withheld to protect credentials.")
        sys.exit(2)
