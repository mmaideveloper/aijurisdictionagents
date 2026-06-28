from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.laws_api import _laws_db_config, _read_laws_statistics
from app.observability import (
    ApplicationName,
    AzureApplicationInsightsLogService,
    ObservabilityConfigurationError,
)
from app.security import require_api_key
from app.versioning import get_api_version, get_core_version

router = APIRouter(
    prefix="/v1/system",
    tags=["system-status"],
    dependencies=[Depends(require_api_key)],
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APPLICATIONS: tuple[ApplicationName, ...] = ("api", "laws_collector", "document_processor")
_AI_USAGE_WINDOWS_MINUTES = (60, 24 * 60, 7 * 24 * 60, 30 * 24 * 60)


@router.get("/status")
def get_system_status(
    minutes: int = Query(60, ge=1, le=24 * 60),
) -> dict[str, Any]:
    api_status = _api_status_payload()
    laws_status = _laws_collector_status_payload()
    server_status = _server_status_payload()
    errors = _error_counts_payload(minutes=minutes)
    ai_model_usage = _ai_model_usage_payload(minutes=minutes)

    component_states = [
        str(api_status.get("status", "unknown")),
        str(laws_status.get("status", "unknown")),
        str(server_status.get("status", "unknown")),
        str(errors.get("status", "unknown")),
        str(ai_model_usage.get("status", "unknown")),
    ]
    return {
        "generated_at": _utc_now(),
        "window_minutes": minutes,
        "status": _rollup_status(component_states),
        "api": api_status,
        "system": server_status,
        "laws_collector": laws_status,
        "errors": errors,
        "ai_model_usage": ai_model_usage,
    }


def _api_status_payload() -> dict[str, Any]:
    llm_payload = _llm_health_payload()
    database_backend = _configured_db_backend()
    database_status = "ok"
    database_message = ""
    try:
        from aijurisdictionagents.api_db import ApiDatabaseStore

        store = ApiDatabaseStore.from_env()
        database_backend = store.db_option
        store.check_connection()
    except Exception as exc:
        database_status = "error"
        database_message = str(exc)

    return {
        "status": "ok" if database_status == "ok" and llm_payload["status"] == "ok" else "error",
        "service": "aijuristiction-api",
        "api_version": get_api_version(),
        "core_version": get_core_version(),
        "llm": {
            "status": llm_payload["status"],
            "provider": _configured_llm_provider(),
        },
        "database": {
            "status": database_status,
            "backend": database_backend,
            "message": database_message or None,
        },
    }


def _configured_db_backend() -> str:
    raw_value = os.getenv("DB_OPTION", "local").strip().lower()
    if raw_value == "postgress":
        return "postgres"
    return raw_value or "local"


def _configured_llm_provider() -> str:
    raw_value = os.getenv("LLM_PROVIDER", "").strip().lower()
    if raw_value == "mock":
        return "mock"
    return "model_routing"


def _llm_health_payload() -> dict[str, str]:
    provider = _configured_llm_provider()
    return {
        "status": "ok",
        "provider": provider,
    }


def _laws_collector_status_payload() -> dict[str, Any]:
    try:
        statistics = _read_laws_statistics(config=_laws_db_config(), country_code="SK")
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Laws collector status unavailable: {exc}",
        }

    collector = dict(statistics.get("collector", {}))
    current_import = dict(statistics.get("current_import", {}))
    totals = dict(statistics.get("totals", {}))
    coverage = dict(statistics.get("coverage", {}))
    last_run_at = _optional_str(collector.get("last_collector_run_at"))
    runtime = _laws_collector_runtime_from_server_file()

    return {
        "status": _freshness_status(last_run_at, warning_hours=36),
        "country_code": statistics.get("country_code"),
        "db_backend": statistics.get("db_backend"),
        "last_collector_run_at": last_run_at,
        "last_processed_at": collector.get("last_processed_at"),
        "last_processed_law": collector.get("last_processed_law"),
        "next_law_to_check": collector.get("next_law_to_check"),
        "current_import": current_import,
        "totals": totals,
        "coverage": coverage,
        "runtime": runtime,
    }


def _server_status_payload() -> dict[str, Any]:
    path = _server_status_path()
    if not path.exists():
        return {
            "status": "unknown",
            "message": f"Server status file not found: {path}",
            "path": str(path),
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Server status file could not be read: {exc}",
            "path": str(path),
        }

    if not isinstance(payload, dict):
        return {
            "status": "error",
            "message": "Server status file must contain a JSON object.",
            "path": str(path),
        }

    payload = _redact_server_status(payload)
    payload.setdefault("path", str(path))
    payload.setdefault("status", _server_payload_status(payload))
    return payload


def _error_counts_payload(*, minutes: int) -> dict[str, Any]:
    try:
        service = AzureApplicationInsightsLogService.from_env()
    except ObservabilityConfigurationError as exc:
        local_counts = _local_error_counts_from_server_file()
        return {
            "status": "local_only" if local_counts else "unknown",
            "window_minutes": minutes,
            "source": "server_status_file" if local_counts else "not_configured",
            "message": str(exc),
            "by_application": local_counts,
        }

    counts: dict[str, int] = {}
    failures: dict[str, str] = {}
    for application in _APPLICATIONS:
        count = 0
        for level in ("error", "critical"):
            try:
                result = service.query_logs(
                    minutes=minutes,
                    limit=1,
                    application=application,
                    level=level,
                    source=None,
                )
            except Exception as exc:
                failures[application] = str(exc)
                continue
            count += result.total_count
        counts[application] = count

    return {
        "status": "degraded" if failures else "ok",
        "window_minutes": minutes,
        "source": "application_insights",
        "by_application": counts,
        "failures": failures,
    }


def _ai_model_usage_payload(*, minutes: int) -> dict[str, Any]:
    try:
        from aijurisdictionagents.api_db import ApiDatabaseStore

        store = ApiDatabaseStore.from_env()
        windows = _ai_usage_windows(minutes)
        summaries = [
            (window, item)
            for window in windows
            for item in store.summarize_ai_model_usage(minutes=window)
        ]
        top_cases = [
            (window, item)
            for window in windows
            for item in store.summarize_top_ai_model_cases(minutes=window, limit=10)
        ]
    except Exception as exc:
        return {
            "status": "error",
            "window_minutes": minutes,
            "message": str(exc),
            "summaries": [],
            "top_cases": [],
        }

    return {
        "status": "ok",
        "window_minutes": minutes,
        "available_windows_minutes": windows,
        "summaries": [
            {
                "window_minutes": window,
                "plan_code": item.plan_code,
                "task_type": item.task_type,
                "provider": item.provider,
                "model": item.model,
                "route_type": item.route_type,
                "route_class": _ai_usage_route_class(
                    provider=item.provider,
                    route_type=item.route_type,
                ),
                "status": item.status,
                "fallback_reason": item.fallback_reason,
                "input_tokens": item.input_tokens,
                "cached_input_tokens": item.cached_input_tokens,
                "output_tokens": item.output_tokens,
                "total_tokens": item.total_tokens,
                "estimated_cost_eur": item.estimated_cost_eur,
                "request_count": item.request_count,
            }
            for window, item in summaries
        ],
        "top_cases": [
            {
                "window_minutes": window,
                "case_ref": _masked_case_ref(item.case_id),
                "plan_code": item.plan_code,
                "provider": item.provider,
                "model": item.model,
                "route_type": item.route_type,
                "route_class": _ai_usage_route_class(
                    provider=item.provider,
                    route_type=item.route_type,
                ),
                "input_tokens": item.input_tokens,
                "cached_input_tokens": item.cached_input_tokens,
                "output_tokens": item.output_tokens,
                "total_tokens": item.total_tokens,
                "estimated_cost_eur": item.estimated_cost_eur,
                "request_count": item.request_count,
            }
            for window, item in top_cases
        ],
    }


def _ai_usage_windows(requested_minutes: int) -> list[int]:
    windows = list(_AI_USAGE_WINDOWS_MINUTES)
    if requested_minutes not in windows:
        windows.insert(0, requested_minutes)
    return windows


def _ai_usage_route_class(*, provider: str, route_type: str) -> str:
    normalized_provider = provider.strip().lower()
    normalized_route = route_type.strip().lower()
    if normalized_route in {"local", "local_only"} or "ollama" in normalized_provider:
        return "local"
    if normalized_route in {"external", "external_ack_required"}:
        return "paid"
    return normalized_route or "unknown"


def _masked_case_ref(case_id: str) -> str:
    normalized = case_id.strip()
    if not normalized:
        return "case-unknown"
    compact = normalized.replace("-", "")
    if len(compact) >= 8:
        return f"case-{compact[:4]}...{compact[-4:]}"
    return f"case-...{compact[-4:]}"


def _laws_collector_runtime_from_server_file() -> dict[str, Any] | None:
    server_status = _server_status_payload_without_recursion()
    apps = server_status.get("apps")
    if not isinstance(apps, dict):
        return None
    collector = apps.get("laws_collector")
    return collector if isinstance(collector, dict) else None


def _local_error_counts_from_server_file() -> dict[str, int]:
    server_status = _server_status_payload_without_recursion()
    apps = server_status.get("apps")
    if not isinstance(apps, dict):
        return {}

    counts: dict[str, int] = {}
    for app_name, payload in apps.items():
        if not isinstance(app_name, str) or not isinstance(payload, dict):
            continue
        errors = payload.get("error_count")
        if isinstance(errors, int):
            counts[app_name] = errors
    return counts


def _server_status_payload_without_recursion() -> dict[str, Any]:
    path = _server_status_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return _redact_server_status(payload) if isinstance(payload, dict) else {}


def _server_status_path() -> Path:
    value = os.getenv("SYSTEM_STATUS_FILE", "./runs/status/system-status.json").strip()
    candidate = Path(value)
    return candidate if candidate.is_absolute() else _REPO_ROOT / candidate


def _redact_server_status(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(payload))
    if not isinstance(redacted, dict):
        return {}
    redacted.pop("environment", None)
    return redacted


def _server_payload_status(payload: dict[str, Any]) -> str:
    apps = payload.get("apps")
    if not isinstance(apps, dict):
        return "unknown"
    states: list[str] = []
    for value in apps.values():
        if isinstance(value, dict):
            states.append(str(value.get("status", "unknown")))
    return _rollup_status(states)


def _freshness_status(timestamp: str | None, *, warning_hours: int) -> str:
    if not timestamp:
        return "unknown"
    parsed = _parse_datetime(timestamp)
    if parsed is None:
        return "unknown"
    age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
    return "ok" if age_seconds <= warning_hours * 3600 else "degraded"


def _parse_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rollup_status(states: list[str]) -> str:
    normalized = {state for state in states if state}
    if "error" in normalized:
        return "error"
    if normalized & {"degraded", "unknown"}:
        return "degraded"
    return "ok"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
