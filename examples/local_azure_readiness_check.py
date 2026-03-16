#!/usr/bin/env python3
"""Readiness checker for local+Azure API/mobile verification workflow."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List
from urllib import error, request


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(command: List[str]) -> str:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return f"failed to execute: {exc}"

    output = (completed.stdout or "") + (completed.stderr or "")
    output = output.strip() or "(no output)"
    return f"exit={completed.returncode}; {output.splitlines()[0]}"


def tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def fetch_json(url: str) -> Dict[str, object]:
    with request.urlopen(url, timeout=5) as response:  # noqa: S310
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def check_api_health() -> CheckResult:
    base_url = os.getenv("AIJ_API_BASE_URL", "http://127.0.0.1:8080")
    health_url = f"{base_url}/health"
    try:
        payload = fetch_json(health_url)
        return CheckResult("api_health", True, f"{health_url} responded: {payload}")
    except (error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        return CheckResult("api_health", False, f"{health_url} unreachable or invalid JSON: {exc}")


def check_env_vars() -> List[CheckResult]:
    required = [
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_RESOURCE_GROUP",
        "AZURE_LOCATION",
        "AZURE_DB_HOST",
        "AZURE_DB_NAME",
        "AZURE_DB_USER",
        "AZURE_DB_PASSWORD",
    ]
    results: List[CheckResult] = []
    for name in required:
        value = os.getenv(name)
        masked = "set" if value else "missing"
        results.append(CheckResult(f"env:{name}", value is not None and value != "", masked))
    return results


def main() -> None:
    checks: List[CheckResult] = []

    tools = {
        "python": ["python", "--version"],
        "docker": ["docker", "--version"],
        "az": ["az", "version"],
        "flutter": ["flutter", "--version"],
        "powershell": ["pwsh", "-Version"],
    }
    for name, probe in tools.items():
        installed = has_command(name if name != "powershell" else "pwsh")
        details = run_command(probe) if installed else "command not found"
        checks.append(CheckResult(f"tool:{name}", installed, details))

    checks.append(CheckResult("port:5432", tcp_reachable("127.0.0.1", 5432), "PostgreSQL local port probe"))
    checks.append(CheckResult("port:8080", tcp_reachable("127.0.0.1", 8080), "API local port probe"))
    checks.append(CheckResult("port:7357", tcp_reachable("127.0.0.1", 7357), "Flutter web local port probe"))
    checks.append(check_api_health())
    checks.extend(check_env_vars())

    report = {
        "repo_root": str(Path(__file__).resolve().parents[1]),
        "checks": [asdict(check) for check in checks],
    }

    failures = [item for item in checks if not item.ok]
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
