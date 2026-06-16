from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


DEFAULT_OUTPUT = "/srv/jurisdigta/runs/status/system-status.json"
DEFAULT_LAWS_LOG = "/srv/jurisdigta/runs/logs/laws-collector-daily-latest.log"
DEFAULT_APP_ROOT = "/srv/jurisdigta/app"
ERROR_PATTERN = re.compile(r"\b(error|exception|traceback|critical|failed)\b", re.IGNORECASE)
HTTP_REQUEST_PATTERN = re.compile(
    r"\|\s*(?P<logger>[A-Za-z0-9_.-]+\.http)\s*\|\s*"
    r"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+->\s+"
    r"(?P<status>\d{3})\s+\((?P<duration_ms>\d+)\s+ms\)"
)
START_PATTERN = re.compile(r"^\[(?P<timestamp>[^\]]+)\] starting laws collector daily job")
FINISH_PATTERN = re.compile(r"^\[(?P<timestamp>[^\]]+)\] laws collector daily job finished")
KEY_VALUE_PATTERN = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>\S*)")
SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|authorization|connection[_-]?string)"
)
URL_CREDENTIALS_PATTERN = re.compile(r"([a-z][a-z0-9+.-]*://[^:/\s]+:)([^@\s]+)(@)", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write safe server/app status JSON for JurisDigta monitoring."
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--laws-log", default=DEFAULT_LAWS_LOG)
    parser.add_argument("--app-root", default=DEFAULT_APP_ROOT)
    parser.add_argument("--api-container", default="jurisdigta-api")
    parser.add_argument("--mcp-container", default="jurisdigta-mcp")
    parser.add_argument("--postgres-container", default="aijurisdiction-postgres")
    parser.add_argument("--laws-container", default="jurisdigta-laws-collector-daily")
    parser.add_argument("--docker-log-since", default="60m")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_status_payload(
        app_root=Path(args.app_root),
        laws_log=Path(args.laws_log),
        api_container=args.api_container,
        mcp_container=args.mcp_container,
        postgres_container=args.postgres_container,
        laws_container=args.laws_container,
        docker_log_since=args.docker_log_since,
    )
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(output_path)
    return 0


def build_status_payload(
    *,
    app_root: Path,
    laws_log: Path,
    api_container: str,
    mcp_container: str,
    postgres_container: str,
    laws_container: str,
    docker_log_since: str,
) -> dict[str, Any]:
    api_status = _container_status(api_container, log_since=docker_log_since, include_http_metrics=True)
    mcp_status = _container_status(mcp_container, log_since=docker_log_since, include_http_metrics=True)
    postgres_status = _container_status(postgres_container, log_since=docker_log_since)
    laws_status = _container_status(laws_container, log_since=docker_log_since)
    laws_runtime = _laws_log_status(laws_log)
    laws_status.update(laws_runtime)
    if laws_status.get("status") == "stopped" and laws_status.get("last_run_finished_at"):
        laws_status["status"] = "idle"

    apps = {
        "api": api_status,
        "mcp": mcp_status,
        "postgres": postgres_status,
        "laws_collector": laws_status,
    }
    return {
        "generated_at": _utc_now(),
        "hostname": _command_text(["hostname"]).strip(),
        "git": _git_status(app_root),
        "resources": _resource_status(),
        "apps": apps,
        "business": _business_status(postgres_container),
        "status": _rollup_status([str(app.get("status", "unknown")) for app in apps.values()]),
    }


def _container_status(name: str, *, log_since: str, include_http_metrics: bool = False) -> dict[str, Any]:
    inspect = _command_json(
        [
            "docker",
            "inspect",
            name,
            "--format",
            (
                '{"name":"{{.Name}}","status":"{{.State.Status}}",'
                '"running":{{.State.Running}},"started_at":"{{.State.StartedAt}}",'
                '"finished_at":"{{.State.FinishedAt}}","image":"{{.Config.Image}}",'
                '"health":"{{if .State.Health}}{{.State.Health.Status}}{{else}}{{end}}"}'
            ),
        ]
    )
    if inspect is None:
        return {
            "container": name,
            "status": "stopped",
            "running": False,
            "error_count": 0,
            "message": "container not found",
        }

    status = str(inspect.get("status") or "unknown")
    running = bool(inspect.get("running"))
    app_status = "ok" if running and status == "running" else "stopped"
    health = str(inspect.get("health") or "").strip()
    if health and health != "healthy":
        app_status = "degraded"
    log_text = _command_text(["docker", "logs", "--since", log_since, name])
    payload = {
        "container": name,
        "status": app_status,
        "docker_status": status,
        "running": running,
        "health": health or None,
        "image": inspect.get("image"),
        "started_at": _clean_docker_timestamp(inspect.get("started_at")),
        "finished_at": _clean_docker_timestamp(inspect.get("finished_at")),
        "error_count": _count_error_lines(log_text),
    }
    if include_http_metrics:
        payload["http"] = _http_log_metrics(log_text)
    return payload


def _http_log_metrics(text: str) -> dict[str, Any]:
    requests = 0
    duration_total_ms = 0
    duration_max_ms = 0
    by_status_class: dict[str, int] = {}
    by_method: dict[str, int] = {}
    for line in text.splitlines():
        match = HTTP_REQUEST_PATTERN.search(line)
        if not match:
            continue
        requests += 1
        method = match.group("method")
        status_code = match.group("status")
        status_class = f"{status_code[0]}xx"
        duration_ms = int(match.group("duration_ms"))
        duration_total_ms += duration_ms
        duration_max_ms = max(duration_max_ms, duration_ms)
        by_status_class[status_class] = by_status_class.get(status_class, 0) + 1
        by_method[method] = by_method.get(method, 0) + 1
    return {
        "window_seconds": 3600,
        "requests": requests,
        "duration_avg_ms": round(duration_total_ms / requests, 2) if requests else 0,
        "duration_max_ms": duration_max_ms,
        "by_status_class": by_status_class,
        "by_method": by_method,
    }


def _business_status(postgres_container: str) -> dict[str, Any]:
    sql = """
    SELECT json_build_object(
      'users', json_build_object(
        'total', (SELECT COUNT(*) FROM users),
        'new_1h', (SELECT COUNT(*) FROM users WHERE created_at::timestamptz >= now() - interval '1 hour'),
        'new_24h', (SELECT COUNT(*) FROM users WHERE created_at::timestamptz >= now() - interval '24 hours')
      ),
      'cases', json_build_object(
        'total', (SELECT COUNT(*) FROM cases),
        'active', (SELECT COUNT(*) FROM cases WHERE status <> 'deleted'),
        'new_1h', (SELECT COUNT(*) FROM cases WHERE created_at::timestamptz >= now() - interval '1 hour'),
        'new_24h', (SELECT COUNT(*) FROM cases WHERE created_at::timestamptz >= now() - interval '24 hours')
      )
    );
    """
    text = _command_text(
        [
            "docker",
            "exec",
            postgres_container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "aijurisdiction",
            "-t",
            "-A",
            "-c",
            sql,
        ]
    ).strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _laws_log_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "latest_log": str(path),
            "last_run_started_at": None,
            "last_run_finished_at": None,
            "last_run_duration_seconds": None,
            "error_count": 0,
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    started = _last_timestamp(text, START_PATTERN)
    finished = _last_timestamp(text, FINISH_PATTERN)
    duration = None
    if started and finished:
        duration = max(0, int((finished - started).total_seconds()))

    collector_errors = _count_error_lines(text)
    latest_run = _latest_laws_run_summary(text)
    return {
        "latest_log": str(path),
        "last_run_started_at": _format_dt(started),
        "last_run_finished_at": _format_dt(finished),
        "last_run_duration_seconds": duration,
        "last_run_imported_laws": latest_run["imported_laws"],
        "last_run_entries_processed": latest_run["entries_processed"],
        "last_run_processed": latest_run["processed"],
        "recent_errors": _recent_error_lines(text),
        "error_count": collector_errors,
    }


def _resource_status() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    memory = _memory_status()
    return {
        "disk": {
            "path": "/",
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round((usage.used / usage.total) * 100, 2) if usage.total else None,
        },
        "memory": memory,
    }


def _memory_status() -> dict[str, Any]:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return {}
    values: dict[str, int] = {}
    for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
        key, _, raw_value = line.partition(":")
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0]) * 1024
        except ValueError:
            continue
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if total is None or available is None:
        return {}
    used = total - available
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "used_percent": round((used / total) * 100, 2) if total else None,
    }


def _git_status(app_root: Path) -> dict[str, Any]:
    commit = _command_text(["git", "-C", str(app_root), "rev-parse", "--short", "HEAD"])
    branch = _command_text(["git", "-C", str(app_root), "branch", "--show-current"])
    dirty = _command_text(["git", "-C", str(app_root), "status", "--short"])
    return {
        "branch": branch.strip() or None,
        "commit": commit.strip() or None,
        "dirty": bool(dirty.strip()),
    }


def _command_json(command: list[str]) -> dict[str, Any] | None:
    text = _command_text(command)
    if not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _command_text(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "") + (result.stderr or "")


def _last_timestamp(text: str, pattern: re.Pattern[str]) -> datetime | None:
    found: datetime | None = None
    for line in text.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        parsed = _parse_datetime(match.group("timestamp"))
        if parsed is not None:
            found = parsed
    return found


def _count_error_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if ERROR_PATTERN.search(line))


def _latest_laws_run_summary(text: str) -> dict[str, int]:
    lines = text.splitlines()
    start_index = 0
    for index, line in enumerate(lines):
        if START_PATTERN.search(line):
            start_index = index

    summary = {
        "imported_laws": 0,
        "entries_processed": 0,
        "processed": 0,
    }
    for line in lines[start_index:]:
        fields = _key_values(line)
        summary["entries_processed"] += _int_field(fields, "entries_processed")
        summary["processed"] += _int_field(fields, "processed")
        summary["imported_laws"] += _int_field(fields, "new_documents")
        summary["imported_laws"] += _int_field(fields, "laws_found")
    return summary


def _key_values(line: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in KEY_VALUE_PATTERN.finditer(line)}


def _int_field(fields: dict[str, str], key: str) -> int:
    value = fields.get(key)
    if value is None:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def _recent_error_lines(text: str, *, limit: int = 20) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not ERROR_PATTERN.search(line):
            continue
        errors.append(
            {
                "timestamp": _format_dt(_line_timestamp(line)),
                "message": _sanitize_log_line(line),
            }
        )
    return errors[-limit:]


def _line_timestamp(line: str) -> datetime | None:
    if not line.startswith("["):
        return None
    timestamp, _, _rest = line[1:].partition("]")
    return _parse_datetime(timestamp)


def _sanitize_log_line(line: str) -> str:
    sanitized = URL_CREDENTIALS_PATTERN.sub(r"\1***\3", line)
    parts: list[str] = []
    for token in sanitized.split():
        key, separator, _value = token.partition("=")
        if separator and SECRET_PATTERN.search(key):
            parts.append(f"{key}=***")
        else:
            parts.append(token)
    return " ".join(parts)[:240]


def _parse_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_docker_timestamp(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or text.startswith("0001-01-01"):
        return None
    parsed = _parse_datetime(text)
    return _format_dt(parsed) if parsed else text


def _format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rollup_status(states: list[str]) -> str:
    if any(state in {"error", "stopped"} for state in states):
        return "error"
    if any(state == "degraded" for state in states):
        return "degraded"
    if any(state not in {"ok", "idle"} for state in states):
        return "degraded"
    return "ok"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
