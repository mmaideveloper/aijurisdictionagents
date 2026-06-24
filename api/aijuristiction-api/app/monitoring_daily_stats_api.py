from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
import secrets
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader

from app.auth.service import API_KEY_HEADER_NAME, validate_api_key
from app.system_status_api import (
    _api_status_payload,
    _error_counts_payload,
    _laws_collector_status_payload,
    _server_status_payload,
)

router = APIRouter(
    prefix="/v1/monitoring",
    tags=["monitoring"],
)

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


@dataclass(frozen=True)
class _SystemSpec:
    name: str
    probe_service: str | None = None
    up_query: str | None = None
    component: str | None = None
    error_application: str | None = None
    local_app: str | None = None


_SYSTEMS: tuple[_SystemSpec, ...] = (
    _SystemSpec(name="Web", probe_service="jurisdigta-web", component="web"),
    _SystemSpec(
        name="API",
        probe_service="jurisdigta-api",
        component="api",
        error_application="api",
        local_app="api",
    ),
    _SystemSpec(
        name="MCP",
        probe_service="jurisdigta-mcp",
        component="mcp",
        local_app="mcp",
    ),
    _SystemSpec(
        name="Admin/Grafana",
        probe_service="jurisdigta-grafana",
        component="monitoring",
    ),
    _SystemSpec(name="System", up_query='up{job="node-exporter"}'),
    _SystemSpec(
        name="Laws Collector",
        component="laws_collector",
        error_application="laws_collector",
        local_app="laws_collector",
    ),
    _SystemSpec(
        name="Document Processor",
        component="document_processor",
        error_application="document_processor",
        local_app="document_processor",
    ),
    _SystemSpec(
        name="Email Scheduler",
        component="email_scheduler",
        local_app="email_scheduler",
    ),
)


def _require_daily_stats_access(
    x_daily_stats_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    api_key: str | None = Security(_api_key_header),
) -> None:
    configured_token = os.getenv("JURISDIGTA_DAILY_STATS_TOKEN", "").strip()
    if configured_token:
        supplied = _bearer_token(authorization) or (x_daily_stats_token or "").strip()
        if secrets.compare_digest(supplied, configured_token):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid daily stats token.",
        )

    validate_api_key(api_key)


@router.get("/daily-stats")
def get_daily_stats(
    window_hours: int = Query(24, ge=1, le=24 * 7),
    window: str | None = Query(default=None),
    _: None = Depends(_require_daily_stats_access),
) -> dict[str, Any]:
    window_hours = _resolve_window_hours(window_hours=window_hours, window=window)
    window_minutes = window_hours * 60
    status_payload = _status_payload(window_minutes=window_minutes)
    errors = _dict(status_payload.get("errors"))
    error_counts = _dict(errors.get("by_application"))
    server_apps = _dict(_nested(status_payload, "system", "apps"))

    systems = [
        _system_row(
            spec=spec,
            window_hours=window_hours,
            window_minutes=window_minutes,
            status_payload=status_payload,
            error_counts=error_counts,
            server_apps=server_apps,
        )
        for spec in _SYSTEMS
    ]
    incidents = [
        {
            "system": row["system"],
            "status": row["status"],
            "minutes_down": row["minutes_down"],
            "error_count": row["error_count"],
            "notes": row["notes"],
        }
        for row in systems
        if row["status"] == "error"
        or _positive_number(row["minutes_down"])
        or _positive_number(row["error_count"])
    ]

    return {
        "generated_at": _utc_now(),
        "window": f"{window_hours}h",
        "window_hours": window_hours,
        "status": "error" if any(row["status"] == "error" for row in systems) else "ok",
        "systems": systems,
        "incidents": incidents,
        "sources": {
            "status": "system_status",
            "downtime": "prometheus" if _prometheus_configured() else "unavailable",
            "errors": errors.get("source") or "unavailable",
        },
    }


def _resolve_window_hours(*, window_hours: int, window: str | None) -> int:
    if window is None:
        return window_hours
    normalized = window.strip().lower()
    if not normalized.endswith("h"):
        raise HTTPException(
            status_code=422,
            detail='window must use an hour value such as "24h".',
        )
    try:
        parsed = int(normalized[:-1])
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail='window must use an hour value such as "24h".',
        ) from exc
    if parsed < 1 or parsed > 24 * 7:
        raise HTTPException(
            status_code=422,
            detail="window must be between 1h and 168h.",
        )
    return parsed


def _status_payload(*, window_minutes: int) -> dict[str, Any]:
    return {
        "api": _api_status_payload(),
        "system": _server_status_payload(),
        "laws_collector": _laws_collector_status_payload(),
        "errors": _error_counts_payload(minutes=window_minutes),
    }


def _system_row(
    *,
    spec: _SystemSpec,
    window_hours: int,
    window_minutes: int,
    status_payload: dict[str, Any],
    error_counts: dict[str, Any],
    server_apps: dict[str, Any],
) -> dict[str, Any]:
    status_text, status_notes = _system_status(spec, status_payload, server_apps)
    down_minutes, downtime_notes = _minutes_down(spec, window_hours, window_minutes)
    error_count, error_notes = _error_count(spec, error_counts, server_apps)
    if error_count == "unknown" and isinstance(down_minutes, int):
        error_count = down_minutes
        error_notes = [note for note in error_notes if note != "error count source unavailable"]
        error_notes.append("error count uses failed health probes")
    notes = [*status_notes, *downtime_notes, *error_notes]

    return {
        "system": spec.name,
        "status": "ok" if status_text in {"ok", "idle", "local_only"} else "error",
        "minutes_down": down_minutes,
        "error_count": error_count,
        "notes": "; ".join(dict.fromkeys(note for note in notes if note)) or "Healthy",
    }


def _system_status(
    spec: _SystemSpec,
    status_payload: dict[str, Any],
    server_apps: dict[str, Any],
) -> tuple[str, list[str]]:
    if spec.name == "API":
        return str(_nested(status_payload, "api", "status") or "unknown"), []
    if spec.name == "Laws Collector":
        return str(_nested(status_payload, "laws_collector", "status") or "unknown"), []
    if spec.name == "System":
        value = _prometheus_query_value(spec.up_query or "")
        if value is not None:
            return ("ok" if value >= 1 else "error"), []
        resources = _dict(_nested(status_payload, "system", "resources"))
        if resources:
            return "ok", ["live host resource status available"]
        return "unknown", ["live host status source unavailable"]
    if spec.local_app:
        app_payload = _dict(server_apps.get(spec.local_app))
        message = str(app_payload.get("message") or "")
        status_text = str(app_payload.get("status") or "unknown")
        notes = []
        if message and not (status_text in {"ok", "idle"} and message == "container not found"):
            notes.append(message)
        return status_text, notes
    if spec.probe_service:
        value = _prometheus_query_value(
            f'probe_success{{job="jurisdigta-http-probes",service="{spec.probe_service}"}}'
        )
        if value is None:
            return "unknown", ["live probe status unavailable"]
        return ("ok" if value >= 1 else "error"), []
    return "unknown", ["live status source unavailable"]


def _minutes_down(
    spec: _SystemSpec,
    window_hours: int,
    window_minutes: int,
) -> tuple[int | str, list[str]]:
    if spec.probe_service:
        expression = (
            "sum(sum_over_time(("
            f'probe_success{{job="jurisdigta-http-probes",service="{spec.probe_service}"}} == bool 0'
            f")[{window_hours}h:1m]))"
        )
    elif spec.up_query:
        expression = (
            "sum(sum_over_time(("
            f"{spec.up_query} == bool 0"
            f")[{window_hours}h:1m]))"
        )
    elif spec.component:
        expression = (
            "sum(sum_over_time(("
            f'jurisdigta_component_status{{component="{spec.component}"}} == bool 0'
            f")[{window_hours}h:1m]))"
        )
    else:
        return "unknown", ["downtime source unavailable"]

    value = _prometheus_query_value(expression)
    if value is None:
        return "unknown", ["historical Prometheus downtime unavailable"]

    minutes = max(0, min(window_minutes, int(round(value))))
    return minutes, []


def _error_count(
    spec: _SystemSpec,
    error_counts: dict[str, Any],
    server_apps: dict[str, Any],
) -> tuple[int | str, list[str]]:
    if spec.error_application and spec.error_application in error_counts:
        return _int(error_counts.get(spec.error_application), 0), []

    if spec.local_app:
        local_error_count = _dict(server_apps.get(spec.local_app)).get("error_count")
        if local_error_count is not None:
            return _int(local_error_count, 0), ["error count uses local status window"]

    return "unknown", ["error count source unavailable"]


def _prometheus_query_value(expression: str) -> float | None:
    base_url = os.getenv("PROMETHEUS_BASE_URL", "http://127.0.0.1:9091").strip().rstrip("/")
    if not base_url:
        return None
    url = f"{base_url}/api/v1/query?{urlencode({'query': expression})}"
    try:
        with urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    if payload.get("status") != "success":
        return None
    results = _dict(payload.get("data")).get("result")
    if not isinstance(results, list) or not results:
        return 0.0

    total = 0.0
    for result in results:
        value = _dict(result).get("value")
        if not isinstance(value, list) or len(value) < 2:
            continue
        total += _float(value[1], 0.0)
    return total if math.isfinite(total) else None


def _prometheus_configured() -> bool:
    return bool(os.getenv("PROMETHEUS_BASE_URL", "http://127.0.0.1:9091").strip())


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.strip().partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and value > 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
