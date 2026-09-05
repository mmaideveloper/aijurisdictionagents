"""Run an issue #753 local service with the approved encrypted E2E model route."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[1]


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value == "unknown-variable":
        raise RuntimeError(f"{name} is required for the real E2E service")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=("api", "mcp"))
    args = parser.parse_args()
    load_dotenv(REPO_ROOT / ".env", override=False)
    os.environ["DB_OPTION"] = "postgres"
    os.environ["DB_CLOUD"] = (
        "postgresql://postgres:postgres@127.0.0.1:5432/"
        "aij_e2e_753_langgraph_reflection_resume"
    )
    os.environ["LAWS_DB_BACKEND"] = "postgres"
    os.environ["LAWS_DB_CLOUD"] = (
        "postgresql://postgres:postgres@127.0.0.1:5433/laws_e2e_753_reflection"
    )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["LLM_PROVIDER"] = "azurefoundry"
    os.environ["AZURE_OPENAI_ENDPOINT"] = _required("E2E_AZURE_FOUNDRY_ENDPOINT")
    os.environ["AZURE_OPENAI_API_VERSION"] = _required("E2E_AZURE_FOUNDRY_API_VERSION")
    os.environ["AZURE_OPENAI_DEPLOYMENT"] = _required("E2E_AZURE_FOUNDRY_DEPLOYMENT")
    os.environ["AZURE_OPENAI_API_KEY"] = _required("E2E_AZURE_FOUNDRY_API_KEY")
    os.environ["AI_CASE_ORCHESTRATION_MODE"] = "active"
    os.environ["INTERNAL_MCP_BASE_URL"] = "http://127.0.0.1:8070"
    os.environ["INTERNAL_MCP_SHARED_SECRET"] = "issue-753-local-e2e-only"
    api_root = REPO_ROOT / "api" / "aijuristiction-api"
    os.chdir(api_root)
    app = "app.main:app" if args.service == "api" else "app.mcp_main:app"
    port = 8080 if args.service == "api" else 8070
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
