from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.server.export_ollama_metrics import _render_ollama_metrics
from scripts.server.export_system_status_metrics import _merge_local_runtime, _render_metrics
from scripts.server.write_system_status import (
    _court_decision_log_status,
    _http_log_metrics,
    _latest_document_processor_run_summary,
    _latest_laws_run_summary,
    _recent_error_lines,
    _read_recent_log_text,
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
    prometheus_config = (MONITORING_DIR / "prometheus.yml").read_text(encoding="utf-8")
    datasources = (
        MONITORING_DIR / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
    ).read_text(encoding="utf-8")
    alloy_config = (MONITORING_DIR / "alloy" / "config.alloy").read_text(encoding="utf-8")
    loki_config = (MONITORING_DIR / "loki.yml").read_text(encoding="utf-8")

    assert "jurisdigta-loki" in compose
    assert "grafana/alloy" in compose
    assert "jurisdigta-ollama-exporter" in compose
    assert "export_ollama_metrics.py" in compose
    assert "network_mode: host" in compose
    assert "jurisdigta-ollama" in prometheus_config
    assert "host.docker.internal:9109" in prometheus_config
    assert "LOKI_RETENTION_DAYS" in compose
    assert "max-size: ${DOCKER_LOG_MAX_SIZE:-50m}" in compose
    assert "type: loki" in datasources
    assert "loki.source.docker" in alloy_config
    assert "loki.source.file" in alloy_config
    assert "retention_period: ${LOKI_RETENTION_DAYS}d" in loki_config


def test_monitoring_dashboards_include_ollama_ai_models_dashboard() -> None:
    dashboard_path = MONITORING_DIR / "grafana" / "dashboards" / "jurisdigta-ollama-models.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    panel_titles = {str(panel.get("title")) for panel in dashboard["panels"]}

    assert dashboard["uid"] == "jurisdigta-ollama-models"
    assert "Ollama API" in panel_titles
    assert "Loaded Model VRAM" in panel_titles
    assert "AI Tokens By Model And Route" in panel_titles
    assert "Local/Ollama Total Tokens" in panel_titles
    assert "Paid Model Total Tokens" in panel_titles
    assert "Top 10 Cases By Tokens (Masked)" in panel_titles
    assert any(item["name"] == "usage_window" for item in dashboard["templating"]["list"])


def test_monitoring_dashboards_include_court_decision_service_dashboard() -> None:
    dashboard_path = (
        MONITORING_DIR
        / "grafana"
        / "dashboards"
        / "jurisdigta-court-decision-service.json"
    )
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    panel_titles = {str(panel.get("title")) for panel in dashboard["panels"]}
    target_queries = {
        str(target.get("expr"))
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if isinstance(target, dict)
    }

    assert dashboard["uid"] == "jurisdigta-court-decision-service"
    assert "Collector Status" in panel_titles
    assert "Imported Decisions" in panel_titles
    assert "Latest Imported Decision" in panel_titles
    assert "Versions With Embeddings" in panel_titles
    assert "Recent Sanitized Error List" in panel_titles
    assert "Najnovší uložený dátum rozhodnutia" not in panel_titles
    assert (
        'max without(status) (last_over_time(jurisdigta_component_status{component="court_decision_collector"}[15m]))'
        in target_queries
    )
    assert "jurisdigta_court_decision_latest_imported_info" in target_queries

    latest_imported_panel = next(
        panel for panel in dashboard["panels"] if panel.get("title") == "Latest Imported Decision"
    )
    assert latest_imported_panel["type"] == "table"
    assert latest_imported_panel["targets"][0]["instant"] is True
    assert latest_imported_panel["targets"][0]["range"] is False


def test_monitoring_dashboards_include_laws_collector_corpus_panels() -> None:
    dashboard_path = MONITORING_DIR / "grafana" / "dashboards" / "jurisdigta-laws-collector.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    panel_titles = {str(panel.get("title")) for panel in dashboard["panels"]}
    target_queries = {
        str(target.get("expr"))
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if isinstance(target, dict)
    }

    assert dashboard["uid"] == "jurisdigta-laws-collector"
    assert "Total Laws Over Time" in panel_titles
    assert "Last Imported Law" in panel_titles
    assert "Last Imported Law Year" not in panel_titles
    assert 'jurisdigta_laws_total{name="laws_imported"}' in target_queries
    assert "jurisdigta_laws_last_processed_info" in target_queries

    last_imported_law_panel = next(
        panel for panel in dashboard["panels"] if panel.get("title") == "Last Imported Law"
    )
    assert last_imported_law_panel["fieldConfig"]["defaults"]["displayName"] == "${__field.labels.law}"
    assert last_imported_law_panel["options"]["textMode"] == "name"
    assert last_imported_law_panel["targets"][0]["instant"] is True
    assert last_imported_law_panel["targets"][0]["range"] is False


def test_monitoring_stack_loads_ai_model_alert_rules() -> None:
    compose = (MONITORING_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    prometheus_config = (MONITORING_DIR / "prometheus.yml").read_text(encoding="utf-8")
    alert_rules = (
        MONITORING_DIR / "prometheus-rules" / "jurisdigta-ai-models.yml"
    ).read_text(encoding="utf-8")

    assert "./prometheus-rules:/etc/prometheus/rules:ro" in compose
    assert "rule_files:" in prometheus_config
    assert "JurisDigtaOllamaExporterDown" in alert_rules
    assert "JurisDigtaPaidModelTokenSpike" in alert_rules
    assert "JurisDigtaPaidModelCostSpike" in alert_rules


def test_monitoring_env_defaults_include_log_retention() -> None:
    module = _load_configure_monitoring_module()

    module._docker_network_gateway = lambda network: ""
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
    assert values["LOCAL_LLM_BASE_URL"] == "http://127.0.0.1:11434"
    assert values["LOCAL_LLM_MODEL"] == "qwen3:1.7b"


def test_monitoring_env_uses_docker_gateway_for_loopback_ollama_url() -> None:
    module = _load_configure_monitoring_module()

    module._docker_network_gateway = lambda network: "172.18.0.1"
    values = module._build_monitoring_env(
        project_values={"LOCAL_LLM_BASE_URL": "http://127.0.0.1:11434"},
        existing_values={},
        prometheus_host_port=None,
    )

    assert values["LOCAL_LLM_BASE_URL"] == "http://172.18.0.1:11434"


def test_monitoring_env_prefers_explicit_ollama_host_bind() -> None:
    module = _load_configure_monitoring_module()

    module._docker_network_gateway = lambda network: "172.18.0.1"
    values = module._build_monitoring_env(
        project_values={"OLLAMA_HOST_BIND": "10.0.0.5:11434"},
        existing_values={"LOCAL_LLM_BASE_URL": "http://127.0.0.1:11434"},
        prometheus_host_port=None,
    )

    assert values["LOCAL_LLM_BASE_URL"] == "http://10.0.0.5:11434"


def test_prod_api_container_receives_prometheus_url() -> None:
    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "prometheus_base_url=" in deploy_script
    assert "http://jurisdigta-prometheus:9090" in deploy_script
    assert '-e PROMETHEUS_BASE_URL="$prometheus_base_url"' in deploy_script
    assert "connect_api_to_monitoring_network" in deploy_script
    assert "docker network connect \"$network\" jurisdigta-api" in deploy_script


def test_self_managed_laws_collector_supports_continuous_container_mode() -> None:
    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'LAWS_COLLECTOR_RUN_MODE="${LAWS_COLLECTOR_RUN_MODE:-continuous}"' in deploy_script
    assert 'if [ "$LAWS_COLLECTOR_RUN_MODE" = "continuous" ]; then' in deploy_script
    assert "--name jurisdigta-laws-collector" in deploy_script
    assert "--restart unless-stopped" in deploy_script
    assert "-e LAWS_COLLECTOR_RUN_MODE=continuous" in deploy_script
    assert "-e LAWS_WORKER_MAX_CYCLES=0" in deploy_script
    assert "-e LAWS_COLLECTOR_MAX_RUNNING_TIME=0" in deploy_script
    assert "grep -v 'run_laws_collector_daily.sh'" in deploy_script
    assert "--laws-container $laws_container_name" in deploy_script


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
                "last_processed_law": "179/2026",
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

    assert 'jurisdigta_laws_last_processed_info{law="179/2026",number="179",year="2026"} 1' in metrics
    assert "jurisdigta_laws_last_processed_number 179" in metrics
    assert "jurisdigta_laws_last_processed_year 2026" in metrics
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


def test_court_decision_log_status_is_aggregate_and_sanitized(tmp_path: Path) -> None:
    log_file = tmp_path / "court-decision-collector.log"
    log_file.write_text(
        "\n".join(
            [
                (
                    "[2026-06-20T01:00:00Z] court_decision_collector "
                    "processing_judicial_decision source_guid=fixture-1 number=12C/34/2024"
                ),
                (
                    "[2026-06-20T01:00:01Z] court_decision_collector "
                    "processed_judicial_decision source_guid=fixture-1 status=created"
                ),
                (
                    "[2026-06-20T01:05:00Z] court_decision_collector "
                    "waiting_for_new_judicial_decisions status=up_to_date"
                ),
                (
                    "[2026-06-20T01:06:00Z] court_decision_collector failed "
                    "url=postgresql://user:secret@db/court_decisions_sk token=abc123"
                ),
            ]
        ),
        encoding="utf-8",
    )

    payload = _court_decision_log_status(log_file)

    assert payload["processing_events"] == 1
    assert payload["processed_events"] == 1
    assert payload["idle_events"] == 1
    assert payload["last_activity_at"] == "2026-06-20T01:06:00Z"
    assert payload["recent_errors"] == [
        {
            "timestamp": "2026-06-20T01:06:00Z",
            "message": (
                "[2026-06-20T01:06:00Z] court_decision_collector failed "
                "url=postgresql://user:***@db/court_decisions_sk token=***"
            ),
        }
    ]


def test_recent_log_reader_bounds_large_runtime_logs(tmp_path: Path) -> None:
    log_file = tmp_path / "court-decision-collector.log"
    log_file.write_text(
        "old line\n"
        + ("x" * 64)
        + "\n[2026-06-20T01:06:00Z] court_decision_collector failed token=abc123\n",
        encoding="utf-8",
    )

    text = _read_recent_log_text(log_file, max_bytes=80)

    assert "old line" not in text
    assert "court_decision_collector failed token=abc123" in text


def test_exporter_renders_court_decision_metrics() -> None:
    metrics = _render_metrics(
        {
            "status": "ok",
            "system": {
                "status": "ok",
                "apps": {
                    "court_decision_collector": {
                        "status": "ok",
                        "total_decisions": 12,
                        "published_decisions": 10,
                        "total_versions": 14,
                        "versions_with_embeddings": 13,
                        "processing_events": 8,
                        "processed_events": 7,
                        "idle_events": 2,
                        "last_activity_at": "2026-06-20T01:06:00Z",
                        "latest_imported_at": "2026-06-20T01:00:01Z",
                        "latest_imported_decision": {
                            "short_name": "uznesenie - Krajsky sud",
                            "published_date": "2026-06-29",
                            "stored_at": "2026-06-20T01:00:01Z",
                        },
                        "latest_stored_issue_date": "2026-06-29",
                        "latest_update_event_at": "2026-06-20T01:00:02Z",
                        "recent_errors": [
                            {
                                "timestamp": "2026-06-20T01:06:00Z",
                                "message": "failed import_key=live_loop",
                            }
                        ],
                    },
                },
            },
        }
    )

    assert (
        'jurisdigta_component_status{component="court_decision_collector",status="ok"} 1.0'
        in metrics
    )
    assert 'jurisdigta_court_decisions_total{status="all"} 12.0' in metrics
    assert 'jurisdigta_court_decisions_total{status="published"} 10.0' in metrics
    assert "jurisdigta_court_decision_versions_total 14.0" in metrics
    assert "jurisdigta_court_decision_versions_with_embeddings_total 13.0" in metrics
    assert (
        'jurisdigta_court_decision_collector_events_total{event="processed"} 7.0'
        in metrics
    )
    assert "jurisdigta_court_decision_collector_last_activity_timestamp_seconds" in metrics
    assert "jurisdigta_court_decision_latest_stored_issue_date_timestamp_seconds" in metrics
    assert (
        'jurisdigta_court_decision_latest_imported_info{short_name="uznesenie - Krajsky sud",'
        'published_date="2026-06-29",stored_at="2026-06-20T01:00:01Z"} 1'
        in metrics
    )
    assert (
        'jurisdigta_court_decision_recent_error_info{index="1",'
        'timestamp="2026-06-20T01:06:00Z",message="failed import_key=live_loop"} 1'
        in metrics
    )


def test_ollama_exporter_renders_runtime_model_metrics(monkeypatch) -> None:
    responses = {
        "http://127.0.0.1:11434/api/tags": (
            {
                "models": [
                    {
                        "name": "qwen3:1.7b",
                        "size": 1234,
                        "modified_at": "2026-06-25T12:00:00Z",
                        "details": {
                            "family": "qwen",
                            "parameter_size": "27B",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            },
            0.02,
        ),
        "http://127.0.0.1:11434/api/ps": (
            {
                "models": [
                    {
                        "name": "qwen3:1.7b",
                        "size": 1234,
                        "size_vram": 987,
                        "processor": "gpu",
                        "expires_at": "2026-06-25T12:05:00Z",
                    }
                ]
            },
            0.03,
        ),
    }

    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen3:1.7b")
    monkeypatch.setattr(
        "scripts.server.export_ollama_metrics._fetch_json",
        lambda url, *, timeout: responses[url],
    )

    metrics = _render_ollama_metrics(base_url="http://127.0.0.1:11434", timeout=5)

    assert 'jurisdigta_ollama_up{error=""} 1' in metrics
    assert 'jurisdigta_ollama_configured_model_present{model="qwen3:1.7b"} 1' in metrics
    assert "jurisdigta_ollama_models_total 1" in metrics
    assert "jurisdigta_ollama_running_models_total 1" in metrics
    assert 'jurisdigta_ollama_model_loaded{model="qwen3:1.7b"' in metrics
    assert 'jurisdigta_ollama_running_model_vram_bytes{model="qwen3:1.7b",processor="gpu"} 987.0' in metrics


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


def test_exporter_merges_court_decision_runtime_from_local_status_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    status_file = tmp_path / "system-status.json"
    status_file.write_text(
        json.dumps(
            {
                "apps": {
                    "court_decision_collector": {
                        "status": "ok",
                        "total_decisions": 3,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYSTEM_STATUS_FILE", str(status_file))

    payload = _merge_local_runtime({"status": "ok"})

    assert payload["court_decision_collector"]["status"] == "ok"
    assert payload["court_decision_collector"]["total_decisions"] == 3
