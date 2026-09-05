"""Run isolated API and MCP services for issue #653 real local acceptance.

The launcher loads the ignored repository dotenv file without printing values, forces both
services onto task-specific loopback PostgreSQL databases, enables the authenticated startup
probe, and keeps logs under the ignored ``runs/e2e`` tree.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "api" / "aijuristiction-api"
API_URL = "http://127.0.0.1:18080"
MCP_URL = "http://127.0.0.1:18070"
API_DATABASE_URL = (
    "postgresql://postgres:postgres@127.0.0.1:5432/"
    "aij_e2e_653_internal_mcp_connectivity_v2"
)
LAWS_DATABASE_URL = (
    "postgresql://postgres:postgres@127.0.0.1:5433/"
    "laws_e2e_653_internal_mcp_connectivity_v2"
)


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    environment = os.environ.copy()
    environment.update(
        {
            "DB_OPTION": "postgres",
            "DB_CLOUD": API_DATABASE_URL,
            "LAWS_DB_BACKEND": "postgres",
            "LAWS_DB_CLOUD": LAWS_DATABASE_URL,
            "STORAGE_OPTION": "local",
            "STORE_LOCAL": str(REPO_ROOT / "runs" / "e2e" / "issue-653-local-internal-mcp" / "files"),
            "LLM_PROVIDER": "azurefoundry",
            "INTERNAL_MCP_BASE_URL": MCP_URL,
            "INTERNAL_MCP_STARTUP_PROBE_ENABLED": "true",
            "INTERNAL_MCP_STARTUP_PROBE_ATTEMPTS": "10",
            "INTERNAL_MCP_REQUEST_TIMEOUT_SECONDS": "3",
            "INTERNAL_MCP_RETRY_ATTEMPTS": "3",
            "INTERNAL_MCP_RETRY_BACKOFF_SECONDS": "0.5",
            "MCP_OAUTH_TEST_MFA_BYPASS_ENABLED": "true",
            "MCP_OAUTH_TEST_MFA_BYPASS_EMAILS": "mcp-claude-test-paid@jurisdigta.eu",
            "MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT": "2099-01-01T00:00:00Z",
        }
    )
    if environment.get("MCP_API_JWT_SECRET", "").strip() in {"", "unknown-variable"}:
        environment["MCP_API_JWT_SECRET"] = secrets.token_urlsafe(48)
    _require_resolved(environment, "JURISDIGTA_E2E_TEST_USER_PASSWORD")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = REPO_ROOT / "runs" / "e2e" / "issue-653-local-internal-mcp" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[str]] = []
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        mcp = _start_service(
            name="mcp",
            target="app.mcp_main:app",
            port=18070,
            environment=environment,
            evidence_dir=evidence_dir,
        )
        processes.append(mcp)
        _wait_for_health(f"{MCP_URL}/health", mcp)
        print(f"service=mcp status=ready pid={mcp.pid}", flush=True)

        api = _start_service(
            name="api",
            target="app.main:app",
            port=18080,
            environment=environment,
            evidence_dir=evidence_dir,
        )
        processes.append(api)
        _wait_for_health(f"{API_URL}/health", api)
        print(f"service=api status=ready pid={api.pid}", flush=True)
        print(f"evidence={evidence_dir}", flush=True)

        while not stop_requested:
            failed = next((process for process in processes if process.poll() is not None), None)
            if failed is not None:
                raise RuntimeError(f"Local E2E service exited unexpectedly with code {failed.returncode}")
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


def _start_service(
    *,
    name: str,
    target: str,
    port: int,
    environment: dict[str, str],
    evidence_dir: Path,
) -> subprocess.Popen[str]:
    stdout_path = evidence_dir / f"{name}.out.log"
    stderr_path = evidence_dir / f"{name}.err.log"
    stdout = stdout_path.open("w", encoding="utf-8")
    stderr = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)],
        cwd=API_DIR,
        env=environment,
        stdout=stdout,
        stderr=stderr,
        text=True,
    )
    stdout.close()
    stderr.close()
    return process


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


def _require_resolved(environment: dict[str, str], name: str) -> None:
    value = environment.get(name, "").strip()
    if value in {"", "unknown-variable"}:
        raise RuntimeError(f"{name} must be resolved for issue #653 local acceptance")


if __name__ == "__main__":
    raise SystemExit(main())
