"""Run isolated API and MCP services for issue #776 real local acceptance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "api" / "aijuristiction-api"
API_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/issue_776_e2e"
LAWS_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/laws_issue_776_e2e"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-port", type=int, default=8080)
    parser.add_argument("--mcp-port", type=int, default=8070)
    args = parser.parse_args()
    api_url = f"http://127.0.0.1:{args.api_port}"
    mcp_url = f"http://127.0.0.1:{args.mcp_port}"
    load_dotenv(REPO_ROOT / ".env", override=False)
    environment = os.environ.copy()
    environment.update(
        {
            "DB_OPTION": "postgres",
            "DB_CLOUD": API_DATABASE_URL,
            "LAWS_DB_BACKEND": "postgres",
            "LAWS_DB_CLOUD": LAWS_DATABASE_URL,
            "STORAGE_OPTION": "local",
            "STORE_LOCAL": str(REPO_ROOT / "runs" / "e2e" / "issue-776-chat-startup" / "files"),
            "LLM_PROVIDER": "azurefoundry",
            "AI_CASE_ORCHESTRATION_MODE": "active",
            "INTERNAL_MCP_BASE_URL": mcp_url,
            "INTERNAL_MCP_STARTUP_PROBE_ENABLED": "true",
            "INTERNAL_MCP_REQUEST_TIMEOUT_SECONDS": "10",
            "INTERNAL_MCP_RETRY_ATTEMPTS": "3",
            "INTERNAL_MCP_RETRY_BACKOFF_SECONDS": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "LOCAL_LLM_IO_LOGGING": "0",
            "CHAT_EMBEDDING_TIMEOUT_SECONDS": "60",
            "CHAT_STREAM_TERMINAL_TIMEOUT_SECONDS": "660",
        }
    )
    for target, source in (
        ("AZURE_OPENAI_ENDPOINT", "E2E_AZURE_FOUNDRY_ENDPOINT"),
        ("AZURE_OPENAI_API_VERSION", "E2E_AZURE_FOUNDRY_API_VERSION"),
        ("AZURE_OPENAI_DEPLOYMENT", "E2E_AZURE_FOUNDRY_DEPLOYMENT"),
        ("AZURE_OPENAI_API_KEY", "E2E_AZURE_FOUNDRY_API_KEY"),
    ):
        environment[target] = _required(environment, source)
    shared_secret = secrets.token_urlsafe(48)
    environment["INTERNAL_MCP_SHARED_SECRET"] = shared_secret
    environment["MCP_API_JWT_SECRET"] = shared_secret

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = REPO_ROOT / "runs" / "e2e" / "issue-776-chat-startup" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[str]] = []
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        for name, target, port, url in (
            ("mcp", "app.mcp_main:app", args.mcp_port, f"{mcp_url}/health"),
            ("api", "app.main:app", args.api_port, f"{api_url}/health"),
        ):
            _require_available_port(port)
            process = _start_service(
                name=name,
                target=target,
                port=port,
                environment=environment,
                evidence_dir=evidence_dir,
            )
            processes.append(process)
            _wait_for_health(url, process)
            print(f"service={name} status=ready pid={process.pid}", flush=True)
        print(f"evidence={evidence_dir}", flush=True)
        while not stop_requested:
            failed = next((item for item in processes if item.poll() is not None), None)
            if failed is not None:
                raise RuntimeError(
                    f"Local E2E service exited unexpectedly with code {failed.returncode}"
                )
            time.sleep(1)
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


def _required(environment: dict[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if value in {"", "unknown-variable"}:
        raise RuntimeError(f"{name} is required for the real issue #776 E2E")
    return value


def _require_available_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Loopback port {port} is already in use")


def _start_service(
    *,
    name: str,
    target: str,
    port: int,
    environment: dict[str, str],
    evidence_dir: Path,
) -> subprocess.Popen[str]:
    stdout = (evidence_dir / f"{name}.out.log").open("w", encoding="utf-8")
    stderr = (evidence_dir / f"{name}.err.log").open("w", encoding="utf-8")
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)],
            cwd=API_DIR,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
    finally:
        stdout.close()
        stderr.close()


def _wait_for_health(url: str, process: subprocess.Popen[str], timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited before health check with code {process.returncode}")
        try:
            with urlopen(url, timeout=2) as response:  # noqa: S310 - fixed loopback URL
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(1)
    raise TimeoutError(f"Service did not become healthy within {timeout_seconds} seconds")


if __name__ == "__main__":
    raise SystemExit(main())
