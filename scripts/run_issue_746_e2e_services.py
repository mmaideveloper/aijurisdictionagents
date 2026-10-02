"""Run real loopback API/MCP against the isolated issue746 PostgreSQL databases."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import time

from dotenv import load_dotenv
import httpx

from prepare_issue_746_e2e import API_DB, LAWS_DB, QUESTION, SOURCE_ID
from run_issue_810_e2e_services import _require_available_port, _start_service, _wait_for_health

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    load_dotenv(ROOT / ".env")
    env = os.environ.copy()
    secret = secrets.token_urlsafe(40)
    env.update(DB_OPTION="postgres", DB_CLOUD=API_DB, LAWS_DB_BACKEND="postgres", LAWS_DB_CLOUD=LAWS_DB,
               STORAGE_OPTION="local", STORE_LOCAL=str(ROOT / "runs/storage/issue746/files"),
               LLM_PROVIDER="azurefoundry", INTERNAL_MCP_BASE_URL="http://127.0.0.1:8247",
               INTERNAL_MCP_SHARED_SECRET=secret, MCP_API_JWT_SECRET=secret,
               INTERNAL_MCP_STARTUP_PROBE_ENABLED="true", LOCAL_LLM_IO_LOGGING="0",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", CHAT_STREAM_TERMINAL_TIMEOUT_SECONDS="660")
    for name in ("ENDPOINT", "API_VERSION", "DEPLOYMENT", "API_KEY"):
        value = env.get(f"E2E_AZURE_FOUNDRY_{name}", "")
        if not value or value == "unknown-variable":
            raise RuntimeError(f"Missing E2E_AZURE_FOUNDRY_{name}")
        env[f"AZURE_OPENAI_{name}"] = value
    output = ROOT / "runs/e2e/issue746"
    processes = []
    try:
        for name, target, port in (("mcp", "app.mcp_main:app", 8247), ("api", "app.main:app", 8246)):
            _require_available_port(port)
            process = _start_service(name=name, target=target, port=port, environment=env, evidence_dir=output)
            processes.append(process)
            _wait_for_health(f"http://127.0.0.1:{port}/health", process)
            print(f"{name} ready", flush=True)
        def call(name: str, arguments: dict) -> dict:
            response = httpx.post("http://127.0.0.1:8247/mcp",
                                  headers={"X-JurisDigta-Internal-MCP-Secret": secret},
                                  json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                        "params": {"name": name, "arguments": arguments}}, timeout=90)
            response.raise_for_status()
            return json.loads(response.json()["result"]["content"][0]["text"])
        search = call("searchLaws", {"query": QUESTION, "country_code": "SK", "limit": 3})
        assert SOURCE_ID in json.dumps(search), "Expected source missing from search"
        law = call("getLawText", {"document_id": SOURCE_ID, "section_start": 4, "section_end": 7, "max_chars": 40000})
        assert all(f"§ {section}" in law["content_text"] for section in (4, 5, 6, 7))
        (output / "direct-mcp.json").write_text(json.dumps({"passed": True, "sourceId": SOURCE_ID,
            "sections": [4, 5, 6, 7], "version": law["version_id"], "effectiveFrom": law["effective_from"]}), encoding="utf-8")
        print("Direct MCP search and sections 4–7 passed", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(1)
    finally:
        for process in processes:
            process.terminate()


if __name__ == "__main__":
    main()
