from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


STATUS_VALUES = {
    "ok": 1.0,
    "idle": 1.0,
    "local_only": 1.0,
    "degraded": 0.5,
    "unknown": 0.0,
    "error": 0.0,
}


def main() -> None:
    args = _parse_args()
    server = ThreadingHTTPServer((args.host, args.port), _handler(args))
    print(f"serving JurisDigta Prometheus metrics on http://{args.host}:{args.port}/metrics")
    server.serve_forever()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expose /v1/system/status as Prometheus text metrics.",
    )
    parser.add_argument("--host", default=os.getenv("JURISDIGTA_METRICS_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("JURISDIGTA_METRICS_PORT", "9108")),
    )
    parser.add_argument(
        "--status-url",
        default=os.getenv(
            "JURISDIGTA_STATUS_URL",
            "http://127.0.0.1:8080/v1/system/status?minutes=60",
        ),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("API_KEY", os.getenv("JURISDIGTA_API_KEY", "aijuris")),
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def _handler(args: argparse.Namespace) -> type[BaseHTTPRequestHandler]:
    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/metrics", "/"):
                self.send_error(404)
                return

            try:
                payload = _fetch_status(args.status_url, args.api_key, args.timeout)
                payload = _merge_local_runtime(payload)
                body = _render_metrics(payload)
                status = 200
            except Exception as exc:
                body = _render_exporter_error(exc)
                status = 500

            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return MetricsHandler


def _fetch_status(status_url: str, api_key: str, timeout: float) -> dict[str, Any]:
    request = Request(status_url, headers={"x-api-key": api_key})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"failed to fetch system status: {exc.reason}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("system status response was not a JSON object")
    return data


def _merge_local_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    laws = payload.get("laws_collector")
    if not isinstance(laws, dict) or isinstance(laws.get("runtime"), dict):
        return payload

    local_runtime = _local_laws_runtime()
    if not local_runtime:
        return payload

    merged = json.loads(json.dumps(payload))
    merged_laws = merged.setdefault("laws_collector", {})
    if isinstance(merged_laws, dict):
        merged_laws["runtime"] = local_runtime
    return merged


def _local_laws_runtime() -> dict[str, Any]:
    value = os.getenv("SYSTEM_STATUS_FILE", "").strip()
    if not value:
        return {}
    path = Path(value)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    apps = payload.get("apps") if isinstance(payload, dict) else None
    if not isinstance(apps, dict):
        return {}
    laws = apps.get("laws_collector")
    return laws if isinstance(laws, dict) else {}


def _render_metrics(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    _append_help(
        lines,
        "jurisdigta_component_status",
        "Component health mapped to numeric values: ok/idle/local_only=1, degraded=0.5, unknown/error=0.",
        "gauge",
    )
    components = {
        "overall": payload.get("status"),
        "api": _nested(payload, "api", "status"),
        "database": _nested(payload, "api", "database", "status"),
        "llm": _nested(payload, "api", "llm", "status"),
        "system": _nested(payload, "system", "status"),
        "laws_collector": _nested(payload, "laws_collector", "status"),
        "errors": _nested(payload, "errors", "status"),
    }
    for component, status in components.items():
        status_text = str(status or "unknown")
        lines.append(
            "jurisdigta_component_status"
            f'{{component="{_label(component)}",status="{_label(status_text)}"}} '
            f"{_status_value(status_text)}"
        )

    window_minutes = _number(payload.get("window_minutes"), 60)
    _append_help(
        lines,
        "jurisdigta_errors_window",
        "Error count by application for the current status query window.",
        "gauge",
    )
    errors = _nested(payload, "errors", "by_application")
    if isinstance(errors, dict):
        for app_name, count in sorted(errors.items()):
            lines.append(
                "jurisdigta_errors_window"
                f'{{application="{_label(str(app_name))}",window_minutes="{int(window_minutes)}"}} '
                f"{_number(count, 0)}"
            )

    laws = payload.get("laws_collector")
    if isinstance(laws, dict):
        _append_laws_metrics(lines, laws)

    system = payload.get("system")
    if isinstance(system, dict):
        _append_resource_metrics(lines, system)

    generated_at = _timestamp(payload.get("generated_at"))
    if generated_at is not None:
        _append_help(
            lines,
            "jurisdigta_status_generated_timestamp_seconds",
            "Unix timestamp when /v1/system/status generated the payload.",
            "gauge",
        )
        lines.append(f"jurisdigta_status_generated_timestamp_seconds {generated_at}")

    lines.append("")
    return "\n".join(lines)


def _append_laws_metrics(lines: list[str], laws: dict[str, Any]) -> None:
    last_number, last_year = _split_law_number(str(laws.get("last_processed_law") or ""))
    next_number, next_year = _split_law_number(str(laws.get("next_law_to_check") or ""))
    if last_number is not None:
        _append_help(lines, "jurisdigta_laws_last_processed_number", "Last processed law number.", "gauge")
        lines.append(f"jurisdigta_laws_last_processed_number {last_number}")
    if last_year is not None:
        _append_help(lines, "jurisdigta_laws_last_processed_year", "Year of the last processed law.", "gauge")
        lines.append(f"jurisdigta_laws_last_processed_year {last_year}")
    if next_number is not None:
        _append_help(lines, "jurisdigta_laws_next_number", "Next law number to check.", "gauge")
        lines.append(f"jurisdigta_laws_next_number {next_number}")
    if next_year is not None:
        _append_help(lines, "jurisdigta_laws_next_year", "Year of the next law to check.", "gauge")
        lines.append(f"jurisdigta_laws_next_year {next_year}")

    for key in ("last_collector_run_at", "last_processed_at"):
        timestamp = _timestamp(laws.get(key))
        if timestamp is not None:
            metric_name = f"jurisdigta_laws_{key}_timestamp_seconds"
            _append_help(lines, metric_name, f"Unix timestamp for laws collector {key}.", "gauge")
            lines.append(f"{metric_name} {timestamp}")

    runtime = laws.get("runtime")
    if isinstance(runtime, dict):
        for key in ("last_run_started_at", "last_run_finished_at"):
            timestamp = _timestamp(runtime.get(key))
            if timestamp is not None:
                metric_name = f"jurisdigta_laws_runtime_{key}_timestamp_seconds"
                _append_help(lines, metric_name, f"Unix timestamp for laws collector runtime {key}.", "gauge")
                lines.append(f"{metric_name} {timestamp}")
        duration = runtime.get("last_run_duration_seconds")
        if duration is not None:
            _append_help(lines, "jurisdigta_laws_runtime_duration_seconds", "Latest laws collector run duration.", "gauge")
            lines.append(f"jurisdigta_laws_runtime_duration_seconds {_number(duration, 0)}")
        imported_laws = runtime.get("last_run_imported_laws")
        if imported_laws is not None:
            _append_help(lines, "jurisdigta_laws_runtime_imported_laws", "Imported laws in the latest collector run.", "gauge")
            lines.append(f"jurisdigta_laws_runtime_imported_laws {_number(imported_laws, 0)}")
        entries_processed = runtime.get("last_run_entries_processed")
        if entries_processed is not None:
            _append_help(lines, "jurisdigta_laws_runtime_entries_processed", "Entries processed in the latest collector run.", "gauge")
            lines.append(f"jurisdigta_laws_runtime_entries_processed {_number(entries_processed, 0)}")
        processed = runtime.get("last_run_processed")
        if processed is not None:
            _append_help(lines, "jurisdigta_laws_runtime_processed", "Documents processed in the latest collector run.", "gauge")
            lines.append(f"jurisdigta_laws_runtime_processed {_number(processed, 0)}")
        recent_errors = runtime.get("recent_errors")
        if isinstance(recent_errors, list):
            _append_help(lines, "jurisdigta_laws_recent_error_info", "Recent sanitized laws collector error lines.", "gauge")
            for index, error in enumerate(recent_errors[-20:], start=1):
                if not isinstance(error, dict):
                    continue
                timestamp = str(error.get("timestamp") or "")
                message = str(error.get("message") or "")
                lines.append(
                    "jurisdigta_laws_recent_error_info"
                    f'{{index="{index}",timestamp="{_label(timestamp)}",message="{_label(message)}"}} 1'
                )

    totals = laws.get("totals")
    if isinstance(totals, dict):
        _append_help(lines, "jurisdigta_laws_total", "Laws collector total counters from status payload.", "gauge")
        for name, value in sorted(totals.items()):
            lines.append(f'jurisdigta_laws_total{{name="{_label(str(name))}"}} {_number(value, 0)}')


def _append_resource_metrics(lines: list[str], system: dict[str, Any]) -> None:
    resources = system.get("resources")
    if not isinstance(resources, dict):
        return
    disk = resources.get("disk")
    if isinstance(disk, dict):
        _append_help(lines, "jurisdigta_system_disk_used_percent", "Server disk used percentage.", "gauge")
        lines.append(f"jurisdigta_system_disk_used_percent {_number(disk.get('used_percent'), 0)}")
    memory = resources.get("memory")
    if isinstance(memory, dict):
        _append_help(lines, "jurisdigta_system_memory_used_percent", "Server memory used percentage.", "gauge")
        lines.append(f"jurisdigta_system_memory_used_percent {_number(memory.get('used_percent'), 0)}")


def _render_exporter_error(exc: Exception) -> str:
    message = _label(str(exc))
    return "\n".join(
        [
            "# HELP jurisdigta_status_exporter_up Whether the status exporter could fetch status.",
            "# TYPE jurisdigta_status_exporter_up gauge",
            f'jurisdigta_status_exporter_up{{error="{message}"}} 0',
            "",
        ]
    )


def _append_help(lines: list[str], name: str, help_text: str, metric_type: str) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {metric_type}")


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _split_law_number(value: str) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d{4})\s*", value)
    if match is None:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _timestamp(value: object) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp())


def _number(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_value(status: str) -> float:
    return STATUS_VALUES.get(status.strip().lower(), 0.0)


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace('"', '\\"')


if __name__ == "__main__":
    main()
