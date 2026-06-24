from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.server.export_system_status_metrics import _merge_local_runtime, _render_metrics
from scripts.server.write_system_status import (
    _http_log_metrics,
    _latest_document_processor_run_summary,
    _latest_laws_run_summary,
    _recent_error_lines,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING_DIR = REPO_ROOT / "Deployment" / "monitoring"
DEPLOY_SCRIPT = REPO_ROOT / "Deployment" / "server" / "deploy_jurisdigta_prod.sh"


def _load_configure_monitoring_module():
    module_path = MONITORING_DIR / "configure_monitoring.py"
    spec = importlib.util.spec_from_file_location("configure_monitoring", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_monitoring_stack_includes_loki_alloy_and_datasource() -> None:
    compose = (MONITORING_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    datasources = (
        MONITORING_DIR / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
    ).read_text(encoding="utf-8")
    alloy_config = (MONITORING_DIR / "alloy" / "config.alloy").read_text(encoding="utf-8")
    loki_config = (MONITORING_DIR / "loki.yml").read_text(encoding="utf-8")

    assert "jurisdigta-loki" in compose
    assert "grafana/alloy" in compose
    assert "LOKI_RETENTION_DAYS" in compose
    assert "max-size: ${DOCKER_LOG_MAX_SIZE:-50m}" in compose
    assert "type: loki" in datasources
    assert "loki.source.docker" in alloy_config
    assert "loki.source.file" in alloy_config
    assert "retention_period: ${LOKI_RETENTION_DAYS}d" in loki_config


def test_monitoring_env_defaults_include_log_retention() -> None:
    module = _load_configure_monitoring_module()

    values = module._build_monitoring_env(
        project_values={},
        existing_values={},
        prometheus_host_port=None,
    )

    assert values["LOG_RETENTION_DAYS"] == "7"
    assert values["LOKI_RETENTION_DAYS"] == "7"
    assert values["PROMETHEUS_RETENTION_DAYS"] == "30"
    assert values["DOCKER_LOG_MAX_SIZE"] == "50m"
    assert values["DOCKER_LOG_MAX_FILE"] == "5"


def test_prod_api_container_receives_prometheus_url() -> None:
    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "prometheus_base_url=" in deploy_script
    assert "http://host.docker.internal:${PROMETHEUS_HOST_PORT:-9091}" in deploy_script
    assert "--add-host host.docker.internal:host-gateway" in deploy_script
    assert '-e PROMETHEUS_BASE_URL="$prometheus_base_url"' in deploy_script


def test_laws_run_summary_parses_latest_execution() -> None:
    log_text = "\n".join(
        [
            "[2026-06-15T01:00:00Z] starting laws collector daily job",
            "[laws-collector] import_mode=zip entries_processed=10 processed=8 new_documents=7",
            "[2026-06-15T01:05:00Z] laws collector daily job finished",
            "[2026-06-16T01:00:00Z] starting laws collector daily job",
            "[laws-collector] import_mode=zip entries_processed=4 processed=3 new_documents=2",
            "[laws-collector] import_mode=zip_tail_probe laws_found=1 failed_laws=0",
        ]
    )

    assert _latest_laws_run_summary(log_text) == {
        "imported_laws": 3,
        "entries_processed": 4,
        "processed": 3,
    }


def test_recent_error_lines_are_sanitized_and_limited() -> None:
    log_text = "\n".join(
        [
            "[2026-06-16T01:00:00Z] failed url=postgresql://user:secret@db/app token=abc123",
            "[2026-06-16T01:01:00Z] ok",
        ]
    )

    errors = _recent_error_lines(log_text)

    assert errors == [
        {
            "timestamp": "2026-06-16T01:00:00Z",
            "message": "[2026-06-16T01:00:00Z] failed url=postgresql://user:***@db/app token=***",
        }
    ]


def test_http_log_metrics_are_aggregate_only() -> None:
    log_text = "\n".join(
        [
            (
                "2026-06-16 12:52:15,804 | INFO | aijuristiction-api.http | "
                "GET /v1/system/status -> 200 (1692 ms) "
                "request_id=097387ab-79de-4c80-b734-c0250841db36"
            ),
            (
                "2026-06-16 12:52:29,059 | INFO | aijuristiction-api.http | "
                "POST /v1/cases/case-123/documents -> 201 (300 ms) "
                "request_id=978036e7-d54f-4fc5-85a3-ff8844274100"
            ),
        ]
    )

    metrics = _http_log_metrics(log_text)

    assert metrics == {
        "window_seconds": 3600,
        "requests": 2,
        "duration_avg_ms": 996.0,
        "duration_max_ms": 1692,
        "by_status_class": {"2xx": 2},
        "by_method": {"GET": 1, "POST": 1},
    }


def test_document_processor_run_summary_parses_latest_execution() -> None:
    log_text = "\n".join(
        [
            "[2026-06-16T01:00:00Z] starting document processor job",
            "[document-processor] batch_results=[{'status': 'processed'}, {'status': 'failed'}]",
            "[document-processor] document failed doc_id=doc-1 case_id=case-1 error=bad pdf",
            "[2026-06-16T01:05:00Z] document processor job finished",
            "[2026-06-16T02:00:00Z] starting document processor job",
            '[document-processor] batch_results=[{"status": "processed"}, {"status": "processed"}]',
        ]
    )

    assert _latest_document_processor_run_summary(log_text) == {
        "processed": 2,
        "failed": 0,
    }


def test_exporter_renders_laws_runtime_and_recent_error_metrics() -> None:
    metrics = _render_metrics(
        {
            "status": "ok",
            "laws_collector": {
                "status": "ok",
                "runtime": {
                    "last_run_duration_seconds": 42,
                    "last_run_imported_laws": 3,
                    "last_run_entries_processed": 4,
                    "last_run_processed": 3,
                    "recent_errors": [
                        {
                            "timestamp": "2026-06-16T01:00:00Z",
                            "message": "failed import_key=monthly",
                        }
                    ],
                },
            },
        }
    )

    assert "jurisdigta_laws_runtime_duration_seconds 42.0" in metrics
    assert "jurisdigta_laws_runtime_imported_laws 3.0" in metrics
    assert "jurisdigta_laws_runtime_entries_processed 4.0" in metrics
    assert "jurisdigta_laws_runtime_processed 3.0" in metrics
    assert (
        'jurisdigta_laws_recent_error_info{index="1",timestamp="2026-06-16T01:00:00Z",'
        'message="failed import_key=monthly"} 1'
    ) in metrics


def test_exporter_renders_http_and_business_metrics() -> None:
    metrics = _render_metrics(
        {
            "status": "ok",
            "system": {
                "status": "ok",
                "apps": {
                    "api": {
                        "http": {
                            "window_seconds": 3600,
                            "requests": 10,
                            "duration_avg_ms": 125,
                            "duration_max_ms": 500,
                            "by_status_class": {"2xx": 9, "5xx": 1},
                            "by_method": {"GET": 7, "POST": 3},
                        }
                    },
                    "mcp": {
                        "http": {
                            "window_seconds": 3600,
                            "requests": 4,
                            "duration_avg_ms": 50,
                            "duration_max_ms": 100,
                        }
                    },
                },
                "business": {
                    "users": {"total": 12, "new_1h": 1, "new_24h": 3},
                    "cases": {"total": 20, "active": 18, "new_1h": 2, "new_24h": 5},
                },
            },
        }
    )

    assert 'jurisdigta_http_requests_total_window{service="api",window_seconds="3600"} 10.0' in metrics
    assert 'jurisdigta_http_request_duration_seconds_avg{service="api",window_seconds="3600"} 0.125' in metrics
    assert 'jurisdigta_http_request_duration_seconds_max{service="api",window_seconds="3600"} 0.5' in metrics
    assert (
        'jurisdigta_http_requests_by_status_window{service="api",window_seconds="3600",status_class="5xx"} 1.0'
        in metrics
    )
    assert 'jurisdigta_users_total 12.0' in metrics
    assert 'jurisdigta_users_new_window{window="24h"} 3.0' in metrics
    assert 'jurisdigta_cases_total{state="active"} 18.0' in metrics
    assert 'jurisdigta_cases_new_window{window="1h"} 2.0' in metrics


def test_exporter_renders_email_and_document_processor_metrics() -> None:
    metrics = _render_metrics(
        {
            "status": "ok",
            "system": {
                "status": "ok",
                "apps": {
                    "email_scheduler": {
                        "status": "ok",
                        "queue_pending": 4,
                        "queue_processing": 1,
                        "sent_total": 30,
                        "sent_24h": 7,
                        "failed_total": 2,
                        "avg_send_duration_seconds_24h": 3.5,
                        "max_send_duration_seconds_24h": 10,
                    },
                    "document_processor": {
                        "status": "idle",
                        "queue_uploaded": 5,
                        "queue_failed_retryable": 1,
                        "processing": 2,
                        "processed_total": 40,
                        "processed_24h": 8,
                        "failed_total": 3,
                        "avg_processing_duration_seconds_24h": 12.5,
                        "max_processing_duration_seconds_24h": 60,
                        "last_run_duration_seconds": 15,
                        "last_run_processed": 6,
                    },
                },
            },
        }
    )

    assert "jurisdigta_email_sent_total 30.0" in metrics
    assert 'jurisdigta_email_sent_window{window="24h"} 7.0' in metrics
    assert 'jurisdigta_email_queue_total{status="pending"} 4.0' in metrics
    assert 'jurisdigta_email_send_duration_seconds_avg{window="24h"} 3.5' in metrics
    assert "jurisdigta_documents_processed_total 40.0" in metrics
    assert 'jurisdigta_documents_processed_window{window="24h"} 8.0' in metrics
    assert 'jurisdigta_document_processor_queue_total{status="uploaded"} 5.0' in metrics
    assert 'jurisdigta_document_processing_duration_seconds_avg{window="24h"} 12.5' in metrics
    assert "jurisdigta_document_processor_last_run_duration_seconds 15.0" in metrics
    assert "jurisdigta_document_processor_last_run_processed 6.0" in metrics


def test_exporter_merges_laws_runtime_from_local_status_file(monkeypatch, tmp_path) -> None:
    status_file = tmp_path / "system-status.json"
    status_file.write_text(
        json.dumps(
            {
                "apps": {
                    "laws_collector": {
                        "last_run_duration_seconds": 18,
                        "last_run_imported_laws": 2,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYSTEM_STATUS_FILE", str(status_file))

    payload = _merge_local_runtime({"laws_collector": {"status": "ok", "runtime": None}})

    assert payload["laws_collector"]["runtime"]["last_run_duration_seconds"] == 18
    assert payload["laws_collector"]["runtime"]["last_run_imported_laws"] == 2
