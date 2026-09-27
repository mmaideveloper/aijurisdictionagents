"""Run real services for local acceptance with explicit, isolated configuration."""

import argparse
import os
from pathlib import Path
import sys

from dotenv import dotenv_values
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "laws-tests/api"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=["tests", "identity", "mcp"])
    args = parser.parse_args()
    cfg = dotenv_values(ROOT / ".env-laws-test")
    baseline = dotenv_values(ROOT / ".env")
    os.environ.update({k: str(v) for k, v in baseline.items() if v and v != "unknown-variable"})
    os.environ.update(
        {
            "DB_OPTION": "postgres",
            "DB_CLOUD": str(cfg["LAWS_TEST_IDENTITY_DATABASE_URL"]),
            "STORAGE_OPTION": "local",
            "STORE_LOCAL": str(ROOT / "runs/issue840/blobs"),
            "CORS_ALLOW_ORIGINS": "http://127.0.0.1:8412",
            "LLM_PROVIDER": "azurefoundry",
            "PYTHON_DOTENV_DISABLED": "1",
            "LOCAL_LLM_IO_LOGGING": "0",
            "MCP_PORT": "8414",
            "MCP_SERVER_BASE_URL": "http://127.0.0.1:8414",
        }
    )
    for k in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
    ):
        os.environ[k] = str(cfg[k])
    if args.service == "tests":
        from laws_tests.app import create_app

        uvicorn.run(create_app(), host="127.0.0.1", port=8411, access_log=False)
    else:
        sys.path.insert(0, str(ROOT / "api/aijuristiction-api"))
        uvicorn.run(
            "app.main:app" if args.service == "identity" else "app.mcp_main:app",
            host="127.0.0.1",
            port=8413 if args.service == "identity" else 8414,
            access_log=False,
        )


if __name__ == "__main__":
    main()
