"""Atomically open or close the synthetic MCP OAuth E2E window on production.

The script changes only the server runtime env file, recreates only the MCP
container, rolls back both changes on failure, and never prints secret values.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any


APPROVED_EMAILS = (
    "mcp-claude-test-free@jurisdigta.eu",
    "mcp-claude-test-paid@jurisdigta.eu",
)
MANAGED_KEYS = {
    "JURISDIGTA_E2E_TEST_USER_PASSWORD",
    "MCP_OAUTH_TEST_MFA_BYPASS_ENABLED",
    "MCP_OAUTH_TEST_MFA_BYPASS_EMAILS",
    "MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT",
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("enable", "disable"))
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path("/srv/jurisdigta/secrets/jurisdigta.env"),
    )
    parser.add_argument("--container", default="jurisdigta-mcp")
    parser.add_argument("--window-minutes", type=int, default=45)
    parser.add_argument("--health-timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--approved-email",
        action="append",
        choices=APPROVED_EMAILS,
        dest="approved_emails",
        help=(
            "Approved synthetic email to authorize during this window. Repeat for multiple users; "
            "defaults to all approved synthetic users for backwards compatibility."
        ),
    )
    return parser.parse_args()


def _read_env(path: Path) -> tuple[bytes, dict[str, str]]:
    original = path.read_bytes()
    values: dict[str, str] = {}
    for raw_line in original.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return original, values


def _render_env(original: bytes, updates: dict[str, str]) -> bytes:
    output: list[str] = []
    seen: set[str] = set()
    for line in original.decode("utf-8").splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in updates:
            if key not in seen:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    return ("\n".join(output) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    metadata = path.stat()
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, metadata.st_mode & 0o777)
        os.chown(temporary_name, metadata.st_uid, metadata.st_gid)
        os.replace(temporary_name, path)
        directory_descriptor = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _run(arguments: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, check=check, text=True, capture_output=capture)


def _inspect_container(name: str) -> dict[str, Any]:
    output = _run(["docker", "inspect", name], capture=True).stdout
    return dict(json.loads(output)[0])


def _validate_expected_mcp_container(container: dict[str, Any]) -> None:
    config = container.get("Config", {})
    host = container.get("HostConfig", {})
    expected_command = ["uvicorn", "app.mcp_main:app", "--host", "0.0.0.0", "--port", "8070"]
    if config.get("Image") != "aijuristiction-api:local":
        raise RuntimeError("Unexpected MCP image; refusing an unsafe container recreation.")
    if config.get("Cmd") != expected_command:
        raise RuntimeError("Unexpected MCP command; refusing an unsafe container recreation.")
    if host.get("NetworkMode") != "aijuristiction-api_default":
        raise RuntimeError("Unexpected MCP network; refusing an unsafe container recreation.")
    bindings = host.get("PortBindings", {}).get("8070/tcp", [])
    if bindings != [{"HostIp": "127.0.0.1", "HostPort": "8070"}]:
        raise RuntimeError("Unexpected MCP port binding; refusing an unsafe container recreation.")


def _container_environment(container: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in container.get("Config", {}).get("Env", []) or []:
        key, value = str(item).split("=", 1)
        result[key] = value
    return result


def _runs_mount_source(container: dict[str, Any]) -> str:
    matches = [
        str(item.get("Source", ""))
        for item in container.get("Mounts", [])
        if item.get("Type") == "bind" and item.get("Destination") == "/workspace/runs" and item.get("RW")
    ]
    if len(matches) != 1 or not matches[0].startswith("/"):
        raise RuntimeError("Unexpected MCP runs mount; refusing an unsafe container recreation.")
    return matches[0]


def _recreate_mcp(
    *,
    container_name: str,
    managed_values: dict[str, str],
    health_timeout_seconds: int,
) -> None:
    current = _inspect_container(container_name)
    _validate_expected_mcp_container(current)
    runs_mount_source = _runs_mount_source(current)
    environment = _container_environment(current)
    for key in MANAGED_KEYS:
        if key in managed_values:
            environment[key] = managed_values[key]

    descriptor, env_name = tempfile.mkstemp(prefix="jurisdigta-mcp-env-", dir="/tmp", text=True)
    backup_name = f"{container_name}-e2e-backup-{int(time.time())}"
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for key in sorted(environment):
                handle.write(f"{key}={environment[key]}\n")
            handle.flush()
            os.fsync(handle.fileno())

        _run(["docker", "stop", container_name], capture=True)
        _run(["docker", "rename", container_name, backup_name])
        try:
            _run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "--restart",
                    "unless-stopped",
                    "--log-opt",
                    "max-size=50m",
                    "--log-opt",
                    "max-file=5",
                    "--network",
                    "aijuristiction-api_default",
                    "-p",
                    "127.0.0.1:8070:8070",
                    "--health-cmd",
                    "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8070/health')\"",
                    "--health-interval",
                    "30s",
                    "--health-timeout",
                    "5s",
                    "--health-start-period",
                    "10s",
                    "--health-retries",
                    "3",
                    "--env-file",
                    env_name,
                    "-v",
                    f"{runs_mount_source}:/workspace/runs",
                    "aijuristiction-api:local",
                    "uvicorn",
                    "app.mcp_main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8070",
                ],
                capture=True,
            )
            deadline = time.monotonic() + health_timeout_seconds
            while time.monotonic() < deadline:
                state = _inspect_container(container_name).get("State", {})
                health = state.get("Health", {}).get("Status", "none")
                if health == "healthy":
                    break
                if health == "unhealthy":
                    raise RuntimeError("Replacement MCP container became unhealthy.")
                time.sleep(3)
            else:
                raise RuntimeError("Replacement MCP container health check timed out.")
            _run(["docker", "rm", backup_name], capture=True)
        except Exception:
            _run(["docker", "rm", "-f", container_name], capture=True, check=False)
            _run(["docker", "rename", backup_name, container_name], check=False)
            _run(["docker", "start", container_name], capture=True, check=False)
            raise
    finally:
        try:
            os.unlink(env_name)
        except FileNotFoundError:
            pass


def main() -> int:
    args = _arguments()
    if not 5 <= args.window_minutes <= 120:
        raise ValueError("window-minutes must be between 5 and 120")
    original, values = _read_env(args.env_file)
    password = values.get("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip()
    if not password or password == "unknown-variable":
        raise RuntimeError("JURISDIGTA_E2E_TEST_USER_PASSWORD is unresolved; mock fallback is forbidden.")

    if args.mode == "enable":
        approved_emails = tuple(dict.fromkeys(args.approved_emails or APPROVED_EMAILS))
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=args.window_minutes)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        updates = {
            "MCP_OAUTH_TEST_MFA_BYPASS_ENABLED": "true",
            "MCP_OAUTH_TEST_MFA_BYPASS_EMAILS": ",".join(approved_emails),
            "MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT": expires_at,
        }
    else:
        updates = {"MCP_OAUTH_TEST_MFA_BYPASS_ENABLED": "false"}

    updated = _render_env(original, updates)
    _atomic_write(args.env_file, updated)
    try:
        _recreate_mcp(
            container_name=args.container,
            managed_values={**values, **updates},
            health_timeout_seconds=args.health_timeout_seconds,
        )
    except Exception:
        _atomic_write(args.env_file, original)
        raise

    state = "enabled" if args.mode == "enable" else "disabled"
    print(f"Synthetic MCP OAuth E2E window {state}; MCP health=healthy; secret values redacted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
