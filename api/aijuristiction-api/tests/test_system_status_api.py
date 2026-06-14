from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
import app.system_status_api as system_status_api

AUTH_HEADERS = {"x-api-key": "aijuris"}
client = TestClient(app)


def test_system_status_endpoint_requires_api_key() -> None:
    response = client.get("/v1/system/status")

    assert response.status_code == 401


def test_system_status_endpoint_combines_api_system_laws_and_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    status_file = tmp_path / "system-status.json"
    status_file.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-14T14:20:00Z",
                "hostname": "jurisdigta-server",
                "resources": {
                    "disk": {"used_percent": 42.5},
                    "memory": {"used_percent": 61.0},
                },
                "apps": {
                    "api": {
                        "status": "ok",
                        "running": True,
                        "error_count": 2,
                    },
                    "laws_collector": {
                        "status": "ok",
                        "last_run_started_at": "2026-06-14T14:12:54Z",
                        "last_run_finished_at": "2026-06-14T14:13:20Z",
                        "last_run_duration_seconds": 26,
                        "error_count": 0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYSTEM_STATUS_FILE", str(status_file))
    monkeypatch.setattr(
        system_status_api,
        "_api_status_payload",
        lambda: {
            "status": "ok",
            "service": "aijuristiction-api",
            "api_version": "1.0.260449",
            "core_version": "0.1.0",
        },
    )
    monkeypatch.setattr(
        system_status_api,
        "_laws_collector_status_payload",
        lambda: {
            "status": "ok",
            "last_collector_run_at": "2026-06-14T14:13:20Z",
            "last_processed_law": "120/2026",
            "next_law_to_check": "121/2026",
            "runtime": {
                "last_run_duration_seconds": 26,
                "error_count": 0,
            },
        },
    )
    monkeypatch.setattr(
        system_status_api,
        "_error_counts_payload",
        lambda *, minutes: {
            "status": "ok",
            "window_minutes": minutes,
            "source": "application_insights",
            "by_application": {
                "api": 2,
                "laws_collector": 0,
                "document_processor": 1,
            },
        },
    )

    response = client.get("/v1/system/status?minutes=30", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["window_minutes"] == 30
    assert payload["api"]["api_version"] == "1.0.260449"
    assert payload["system"]["hostname"] == "jurisdigta-server"
    assert payload["system"]["apps"]["laws_collector"]["last_run_duration_seconds"] == 26
    assert payload["laws_collector"]["last_processed_law"] == "120/2026"
    assert payload["laws_collector"]["next_law_to_check"] == "121/2026"
    assert payload["errors"]["by_application"]["api"] == 2


def test_error_counts_uses_local_status_file_when_azure_is_not_configured(
    monkeypatch,
    tmp_path: Path,
) -> None:
    status_file = tmp_path / "system-status.json"
    status_file.write_text(
        json.dumps(
            {
                "apps": {
                    "api": {"error_count": 3},
                    "laws_collector": {"error_count": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYSTEM_STATUS_FILE", str(status_file))

    def raise_configuration_error() -> object:
        raise system_status_api.ObservabilityConfigurationError("not configured")

    monkeypatch.setattr(
        system_status_api.AzureApplicationInsightsLogService,
        "from_env",
        raise_configuration_error,
    )

    payload = system_status_api._error_counts_payload(minutes=15)

    assert payload == {
        "status": "local_only",
        "window_minutes": 15,
        "source": "server_status_file",
        "message": "not configured",
        "by_application": {
            "api": 3,
            "laws_collector": 1,
        },
    }


def test_rollup_status_does_not_degrade_for_local_only_telemetry() -> None:
    assert system_status_api._rollup_status(["ok", "local_only"]) == "ok"


def test_server_status_redacts_environment_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    status_file = tmp_path / "system-status.json"
    status_file.write_text(
        json.dumps(
            {
                "environment": {"LAWS_DB_CLOUD": "postgresql://user:secret@host/db"},
                "apps": {"api": {"status": "ok"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYSTEM_STATUS_FILE", str(status_file))

    payload: dict[str, Any] = system_status_api._server_status_payload()

    assert "environment" not in payload
    assert payload["apps"]["api"]["status"] == "ok"
