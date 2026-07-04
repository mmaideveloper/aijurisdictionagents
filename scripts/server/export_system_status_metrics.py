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
    local_apps = _local_apps_runtime()
    if isinstance(laws, dict) and not isinstance(laws.get("runtime"), dict):
        local_laws = local_apps.get("laws_collector")
        if isinstance(local_laws, dict):
            payload = json.loads(json.dumps(payload))
            merged_laws = payload.setdefault("laws_collector", {})
            if isinstance(merged_laws, dict):
                merged_laws["runtime"] = local_laws

    if not isinstance(payload.get("court_decision_collector"), dict):
        local_court_decision = local_apps.get("court_decision_collector")
        if isinstance(local_court_decision, dict):
            payload = json.loads(json.dumps(payload))
            payload["court_decision_collector"] = local_court_decision
    return payload


def _local_apps_runtime() -> dict[str, Any]:
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
    return apps


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
        "court_decision_collector": (
            _nested(payload, "court_decision_collector", "status")
            or _nested(payload, "system", "apps", "court_decision_collector", "status")
        ),
        "email_scheduler": _nested(payload, "system", "apps", "email_scheduler", "status"),
        "document_processor": _nested(payload, "system", "apps", "document_processor", "status"),
        "errors": _nested(payload, "errors", "status"),
        "ai_model_usage": _nested(payload, "ai_model_usage", "status"),
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
        _append_http_metrics(lines, system)
        _append_email_metrics(lines, system)
        _append_document_processor_metrics(lines, system)
        _append_court_decision_collector_metrics(lines, system)

    court_decision_collector = payload.get("court_decision_collector")
    has_system_court_decision = isinstance(
        _nested(payload, "system", "apps", "court_decision_collector"),
        dict,
    )
    if isinstance(court_decision_collector, dict) and not has_system_court_decision:
        _append_court_decision_collector_metrics(
            lines,
            {"apps": {"court_decision_collector": court_decision_collector}},
        )

    business = payload.get("business")
    if not isinstance(business, dict) and isinstance(system, dict):
        business = system.get("business")
    if isinstance(business, dict):
        _append_business_metrics(lines, business)

    ai_model_usage = payload.get("ai_model_usage")
    if isinstance(ai_model_usage, dict):
        _append_ai_model_usage_metrics(lines, ai_model_usage)

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
    last_processed_law = str(laws.get("last_processed_law") or "")
    last_number, last_year = _split_law_number(last_processed_law)
    next_number, next_year = _split_law_number(str(laws.get("next_law_to_check") or ""))
    if last_number is not None and last_year is not None:
        _append_help(
            lines,
            "jurisdigta_laws_last_processed_info",
            "Latest processed law identifier as labels for display panels.",
            "gauge",
        )
        lines.append(
            "jurisdigta_laws_last_processed_info"
            f'{{law="{_label(last_processed_law)}",number="{last_number}",year="{last_year}"}} 1'
        )
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


def _append_http_metrics(lines: list[str], system: dict[str, Any]) -> None:
    apps = system.get("apps")
    if not isinstance(apps, dict):
        return
    _append_help(lines, "jurisdigta_http_requests_total_window", "Total HTTP request count in the local monitoring window.", "gauge")
    _append_help(lines, "jurisdigta_http_requests_by_status_window", "HTTP request count by status class in the local monitoring window.", "gauge")
    _append_help(lines, "jurisdigta_http_requests_by_method_window", "HTTP request count by method in the local monitoring window.", "gauge")
    _append_help(lines, "jurisdigta_http_request_duration_seconds_avg", "Average HTTP request duration in the local monitoring window.", "gauge")
    _append_help(lines, "jurisdigta_http_request_duration_seconds_max", "Maximum HTTP request duration in the local monitoring window.", "gauge")
    for service in ("api", "mcp"):
        app_payload = apps.get(service)
        if not isinstance(app_payload, dict):
            continue
        http = app_payload.get("http")
        if not isinstance(http, dict):
            continue
        window_seconds = int(_number(http.get("window_seconds"), 3600))
        labels = f'service="{_label(service)}",window_seconds="{window_seconds}"'
        lines.append(
            f"jurisdigta_http_requests_total_window{{{labels}}} {_number(http.get('requests'), 0)}"
        )
        lines.append(
            "jurisdigta_http_request_duration_seconds_avg"
            f"{{{labels}}} {_number(http.get('duration_avg_ms'), 0) / 1000}"
        )
        lines.append(
            "jurisdigta_http_request_duration_seconds_max"
            f"{{{labels}}} {_number(http.get('duration_max_ms'), 0) / 1000}"
        )
        for status_class, count in sorted(_dict(http.get("by_status_class")).items()):
            lines.append(
                "jurisdigta_http_requests_by_status_window"
                f'{{{labels},status_class="{_label(str(status_class))}"}} {_number(count, 0)}'
            )
        for method, count in sorted(_dict(http.get("by_method")).items()):
            lines.append(
                "jurisdigta_http_requests_by_method_window"
                f'{{{labels},method="{_label(str(method))}"}} {_number(count, 0)}'
            )


def _append_email_metrics(lines: list[str], system: dict[str, Any]) -> None:
    apps = system.get("apps")
    if not isinstance(apps, dict):
        return
    email = apps.get("email_scheduler")
    if not isinstance(email, dict):
        return
    _append_help(lines, "jurisdigta_email_sent_total", "Total sent emails in the outbox.", "gauge")
    lines.append(f"jurisdigta_email_sent_total {_number(email.get('sent_total'), 0)}")
    _append_help(lines, "jurisdigta_email_sent_window", "Sent emails in the local monitoring window.", "gauge")
    lines.append(f'jurisdigta_email_sent_window{{window="24h"}} {_number(email.get("sent_24h"), 0)}')
    _append_help(lines, "jurisdigta_email_queue_total", "Email outbox queue count by status.", "gauge")
    lines.append(f'jurisdigta_email_queue_total{{status="pending"}} {_number(email.get("queue_pending"), 0)}')
    lines.append(f'jurisdigta_email_queue_total{{status="processing"}} {_number(email.get("queue_processing"), 0)}')
    lines.append(f'jurisdigta_email_queue_total{{status="failed"}} {_number(email.get("failed_total"), 0)}')
    _append_help(lines, "jurisdigta_email_send_duration_seconds_avg", "Average email queue-to-sent duration.", "gauge")
    lines.append(
        f'jurisdigta_email_send_duration_seconds_avg{{window="24h"}} '
        f'{_number(email.get("avg_send_duration_seconds_24h"), 0)}'
    )
    _append_help(lines, "jurisdigta_email_send_duration_seconds_max", "Maximum email queue-to-sent duration.", "gauge")
    lines.append(
        f'jurisdigta_email_send_duration_seconds_max{{window="24h"}} '
        f'{_number(email.get("max_send_duration_seconds_24h"), 0)}'
    )


def _append_document_processor_metrics(lines: list[str], system: dict[str, Any]) -> None:
    apps = system.get("apps")
    if not isinstance(apps, dict):
        return
    processor = apps.get("document_processor")
    if not isinstance(processor, dict):
        return
    _append_help(lines, "jurisdigta_documents_processed_total", "Total processed uploaded case documents.", "gauge")
    lines.append(f"jurisdigta_documents_processed_total {_number(processor.get('processed_total'), 0)}")
    _append_help(lines, "jurisdigta_documents_processed_window", "Processed uploaded case documents in the local monitoring window.", "gauge")
    lines.append(
        f'jurisdigta_documents_processed_window{{window="24h"}} '
        f'{_number(processor.get("processed_24h"), 0)}'
    )
    _append_help(lines, "jurisdigta_document_processor_queue_total", "Document processor queue count by status.", "gauge")
    lines.append(
        f'jurisdigta_document_processor_queue_total{{status="uploaded"}} '
        f'{_number(processor.get("queue_uploaded"), 0)}'
    )
    lines.append(
        f'jurisdigta_document_processor_queue_total{{status="failed_retryable"}} '
        f'{_number(processor.get("queue_failed_retryable"), 0)}'
    )
    lines.append(
        f'jurisdigta_document_processor_queue_total{{status="processing"}} '
        f'{_number(processor.get("processing"), 0)}'
    )
    lines.append(
        f'jurisdigta_document_processor_queue_total{{status="failed"}} '
        f'{_number(processor.get("failed_total"), 0)}'
    )
    _append_help(lines, "jurisdigta_document_processing_duration_seconds_avg", "Average document upload-to-processed duration.", "gauge")
    lines.append(
        f'jurisdigta_document_processing_duration_seconds_avg{{window="24h"}} '
        f'{_number(processor.get("avg_processing_duration_seconds_24h"), 0)}'
    )
    _append_help(lines, "jurisdigta_document_processing_duration_seconds_max", "Maximum document upload-to-processed duration.", "gauge")
    lines.append(
        f'jurisdigta_document_processing_duration_seconds_max{{window="24h"}} '
        f'{_number(processor.get("max_processing_duration_seconds_24h"), 0)}'
    )
    duration = processor.get("last_run_duration_seconds")
    if duration is not None:
        _append_help(lines, "jurisdigta_document_processor_last_run_duration_seconds", "Latest document processor run duration.", "gauge")
        lines.append(f"jurisdigta_document_processor_last_run_duration_seconds {_number(duration, 0)}")
    last_run_processed = processor.get("last_run_processed")
    if last_run_processed is not None:
        _append_help(lines, "jurisdigta_document_processor_last_run_processed", "Documents processed in the latest document processor run.", "gauge")
        lines.append(f"jurisdigta_document_processor_last_run_processed {_number(last_run_processed, 0)}")


def _append_court_decision_collector_metrics(lines: list[str], system: dict[str, Any]) -> None:
    apps = system.get("apps")
    if not isinstance(apps, dict):
        return
    collector = apps.get("court_decision_collector")
    if not isinstance(collector, dict):
        return

    _append_help(
        lines,
        "jurisdigta_court_decisions_total",
        "Total imported court decisions by status class.",
        "gauge",
    )
    lines.append(
        f'jurisdigta_court_decisions_total{{status="all"}} '
        f'{_number(collector.get("total_decisions"), 0)}'
    )
    lines.append(
        f'jurisdigta_court_decisions_total{{status="published"}} '
        f'{_number(collector.get("published_decisions"), 0)}'
    )

    _append_help(
        lines,
        "jurisdigta_court_decision_versions_total",
        "Total imported court decision text versions.",
        "gauge",
    )
    lines.append(
        "jurisdigta_court_decision_versions_total "
        f"{_number(collector.get('total_versions'), 0)}"
    )

    _append_help(
        lines,
        "jurisdigta_court_decision_versions_with_embeddings_total",
        "Total court decision versions with stored embedding vectors.",
        "gauge",
    )
    lines.append(
        "jurisdigta_court_decision_versions_with_embeddings_total "
        f"{_number(collector.get('versions_with_embeddings'), 0)}"
    )

    _append_help(
        lines,
        "jurisdigta_court_decision_collector_events_total",
        "Court decision collector operational event counts parsed from sanitized logs.",
        "gauge",
    )
    for event_name, field in (
        ("processing", "processing_events"),
        ("processed", "processed_events"),
        ("idle", "idle_events"),
    ):
        lines.append(
            "jurisdigta_court_decision_collector_events_total"
            f'{{event="{event_name}"}} {_number(collector.get(field), 0)}'
        )

    for key, metric_name, help_text in (
        (
            "last_activity_at",
            "jurisdigta_court_decision_collector_last_activity_timestamp_seconds",
            "Unix timestamp for latest court decision collector log activity.",
        ),
        (
            "latest_imported_at",
            "jurisdigta_court_decision_latest_imported_timestamp_seconds",
            "Unix timestamp for latest imported court decision.",
        ),
        (
            "latest_stored_issue_date",
            "jurisdigta_court_decision_latest_stored_issue_date_timestamp_seconds",
            "Unix timestamp for newest stored court decision issue date.",
        ),
        (
            "latest_update_event_at",
            "jurisdigta_court_decision_latest_update_event_timestamp_seconds",
            "Unix timestamp for latest court decision update event.",
        ),
    ):
        timestamp = _timestamp(collector.get(key))
        if timestamp is not None:
            _append_help(lines, metric_name, help_text, "gauge")
            lines.append(f"{metric_name} {timestamp}")

    recent_errors = collector.get("recent_errors")
    if isinstance(recent_errors, list):
        _append_help(
            lines,
            "jurisdigta_court_decision_recent_error_info",
            "Recent sanitized court decision collector error lines.",
            "gauge",
        )
        for index, error in enumerate(recent_errors[-20:], start=1):
            if not isinstance(error, dict):
                continue
            timestamp = str(error.get("timestamp") or "")
            message = str(error.get("message") or "")
            lines.append(
                "jurisdigta_court_decision_recent_error_info"
                f'{{index="{index}",timestamp="{_label(timestamp)}",'
                f'message="{_label(message)}"}} 1'
            )


def _append_business_metrics(lines: list[str], business: dict[str, Any]) -> None:
    users = _dict(business.get("users"))
    cases = _dict(business.get("cases"))
    _append_help(lines, "jurisdigta_users_total", "Total registered users.", "gauge")
    lines.append(f"jurisdigta_users_total {_number(users.get('total'), 0)}")
    _append_help(lines, "jurisdigta_users_new_window", "New registered users in the local monitoring window.", "gauge")
    lines.append(f'jurisdigta_users_new_window{{window="1h"}} {_number(users.get("new_1h"), 0)}')
    lines.append(f'jurisdigta_users_new_window{{window="24h"}} {_number(users.get("new_24h"), 0)}')

    _append_help(lines, "jurisdigta_cases_total", "Total cases.", "gauge")
    lines.append(f'jurisdigta_cases_total{{state="all"}} {_number(cases.get("total"), 0)}')
    lines.append(f'jurisdigta_cases_total{{state="active"}} {_number(cases.get("active"), 0)}')
    _append_help(lines, "jurisdigta_cases_new_window", "New cases in the local monitoring window.", "gauge")
    lines.append(f'jurisdigta_cases_new_window{{window="1h"}} {_number(cases.get("new_1h"), 0)}')
    lines.append(f'jurisdigta_cases_new_window{{window="24h"}} {_number(cases.get("new_24h"), 0)}')


def _append_ai_model_usage_metrics(lines: list[str], ai_model_usage: dict[str, Any]) -> None:
    summaries = ai_model_usage.get("summaries")
    _append_help(lines, "jurisdigta_ai_model_requests_window", "AI model request count in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_input_tokens_window", "AI input tokens in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_cached_input_tokens_window", "AI cached input tokens in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_output_tokens_window", "AI output tokens in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_total_tokens_window", "AI total tokens in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_estimated_cost_eur_window", "Estimated AI model cost in EUR in the status query window.", "gauge")
    if isinstance(summaries, list):
        for summary in summaries:
            if not isinstance(summary, dict):
                continue
            labels = _ai_model_usage_labels(
                summary,
                default_window_minutes=int(_number(ai_model_usage.get("window_minutes"), 60)),
            )
            lines.append(f"jurisdigta_ai_model_requests_window{{{labels}}} {_number(summary.get('request_count'), 0)}")
            lines.append(f"jurisdigta_ai_model_input_tokens_window{{{labels}}} {_number(summary.get('input_tokens'), 0)}")
            lines.append(
                "jurisdigta_ai_model_cached_input_tokens_window"
                f"{{{labels}}} {_number(summary.get('cached_input_tokens'), 0)}"
            )
            lines.append(f"jurisdigta_ai_model_output_tokens_window{{{labels}}} {_number(summary.get('output_tokens'), 0)}")
            lines.append(f"jurisdigta_ai_model_total_tokens_window{{{labels}}} {_number(summary.get('total_tokens'), 0)}")
            lines.append(
                "jurisdigta_ai_model_estimated_cost_eur_window"
                f"{{{labels}}} {_number(summary.get('estimated_cost_eur'), 0)}"
            )

    top_cases = ai_model_usage.get("top_cases")
    _append_help(lines, "jurisdigta_ai_model_top_case_requests_window", "Top case AI request count in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_top_case_total_tokens_window", "Top case AI total tokens in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_top_case_input_tokens_window", "Top case AI input tokens in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_top_case_output_tokens_window", "Top case AI output tokens in the status query window.", "gauge")
    _append_help(lines, "jurisdigta_ai_model_top_case_estimated_cost_eur_window", "Top case estimated AI model cost in EUR in the status query window.", "gauge")
    if isinstance(top_cases, list):
        for item in top_cases:
            if not isinstance(item, dict):
                continue
            labels = _ai_model_usage_labels(
                item,
                default_window_minutes=int(_number(ai_model_usage.get("window_minutes"), 60)),
                case_ref=str(item.get("case_ref") or "case-unknown"),
            )
            lines.append(
                "jurisdigta_ai_model_top_case_requests_window"
                f"{{{labels}}} {_number(item.get('request_count'), 0)}"
            )
            lines.append(
                "jurisdigta_ai_model_top_case_total_tokens_window"
                f"{{{labels}}} {_number(item.get('total_tokens'), 0)}"
            )
            lines.append(
                "jurisdigta_ai_model_top_case_input_tokens_window"
                f"{{{labels}}} {_number(item.get('input_tokens'), 0)}"
            )
            lines.append(
                "jurisdigta_ai_model_top_case_output_tokens_window"
                f"{{{labels}}} {_number(item.get('output_tokens'), 0)}"
            )
            lines.append(
                "jurisdigta_ai_model_top_case_estimated_cost_eur_window"
                f"{{{labels}}} {_number(item.get('estimated_cost_eur'), 0)}"
            )


def _ai_model_usage_labels(
    item: dict[str, Any],
    *,
    default_window_minutes: int,
    case_ref: str | None = None,
) -> str:
    labels = [
        f'provider="{_label(str(item.get("provider") or ""))}"',
        f'model="{_label(str(item.get("model") or ""))}"',
        f'route_type="{_label(str(item.get("route_type") or ""))}"',
        f'route_class="{_label(str(item.get("route_class") or ""))}"',
        f'plan_code="{_label(str(item.get("plan_code") or ""))}"',
        f'status="{_label(str(item.get("status") or "ok"))}"',
        f'fallback_reason="{_label(str(item.get("fallback_reason") or ""))}"',
        f'window_minutes="{int(_number(item.get("window_minutes"), default_window_minutes))}"',
    ]
    task_type = item.get("task_type")
    if task_type is not None:
        labels.insert(2, f'task_type="{_label(str(task_type or ""))}"')
    if case_ref is not None:
        labels.insert(0, f'case_ref="{_label(case_ref)}"')
    return ",".join(labels)


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


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status_value(status: str) -> float:
    return STATUS_VALUES.get(status.strip().lower(), 0.0)


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace('"', '\\"')


if __name__ == "__main__":
    main()
