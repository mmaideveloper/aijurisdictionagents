"""Run the local API/MCP against task storage and the approved real E2E model."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

from prepare_issue_635_langgraph_e2e import _seed_synthetic_law

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=["api", "mcp"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    # Same explicit approved-E2E mapping as run_issue_720_e2e_service.py.
    for suffix in ("ENDPOINT", "API_VERSION", "DEPLOYMENT", "API_KEY"):
        value = os.getenv("E2E_AZURE_FOUNDRY_" + suffix, "")
        if not value or value == "unknown-variable":
            raise RuntimeError("Missing E2E_AZURE_FOUNDRY_" + suffix)
        os.environ["AZURE_OPENAI_" + suffix] = value
    os.environ.update(
        DB_OPTION="postgres", DB_CLOUD="postgresql://postgres:postgres@127.0.0.1:5432/issue806_reporting",
        LLM_PROVIDER="azurefoundry", STORAGE_OPTION="local",
        STORE_LOCAL=str(ROOT / "runs/storage/api/files"), LOCAL_LLM_IO_LOGGING="0",
        INTERNAL_MCP_BASE_URL="http://127.0.0.1:8706", API_KEY="aijuris",
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
    )
    # Synthetic service-to-service credential stays local and never authenticates to prod.
    os.environ["INTERNAL_MCP_SHARED_SECRET"] = "issue806-loopback-synthetic-only"
    os.environ["LAWS_DB_BACKEND"] = "postgres"
    os.environ["LAWS_DB_CLOUD"] = "postgresql://postgres:postgres@127.0.0.1:5433/issue806_e2e_laws"
    _seed_synthetic_law()
    os.chdir(ROOT / "api/aijuristiction-api")
    uvicorn.run("app.main:app" if args.service == "api" else "app.mcp_main:app",
                host="127.0.0.1", port=8806 if args.service == "api" else 8706)


if __name__ == "__main__":
    main()
