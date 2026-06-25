from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app
import app.monitoring_daily_stats_api as daily_stats_api

AUTH_HEADERS = {"x-api-key": "aijuris"}
client = TestClient(app)


def test_daily_stats_endpoint_requires_auth() -> None:
    response = client.get("/v1/monitoring/daily-stats")

    assert response.status_code == 401


def test_daily_stats_endpoint_accepts_dedicated_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("JURISDIGTA_DAILY_STATS_TOKEN", "daily-token")
    _stub_status_sources(monkeypatch)
    monkeypatch.setattr(daily_stats_api, "_prometheus_query_value", _healthy_prometheus)

    rejected = client.get("/v1/monitoring/daily-stats", headers=AUTH_HEADERS)
    accepted = client.get(
        "/v1/monitoring/daily-stats",
        headers={"Authorization": "Bearer daily-token"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200


def test_daily_stats_endpoint_returns_simple_system_rows(monkeypatch) -> None:
    monkeypatch.delenv("JURISDIGTA_DAILY_STATS_TOKEN", raising=False)
    _stub_status_sources(monkeypatch)

    def prometheus_value(expression: str) -> float:
        if 'service="jurisdigta-api"' in expression and "== bool 0" in expression:
            return 2.0
        if 'component="document_processor"' in expression and "== bool 0" in expression:
            return 5.0
        return 1.0 if "== bool 0" not in expression else 0.0

    monkeypatch.setattr(daily_stats_api, "_prometheus_query_value", prometheus_value)

    response = client.get("/v1/monitoring/daily-stats?window=24h", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    rows = {row["system"]: row for row in payload["systems"]}
    assert payload["window"] == "24h"
    assert rows["API"] == {
        "system": "API",
        "status": "ok",
        "minutes_down": 2,
        "error_count": 3,
        "notes": "Healthy",
    }
    assert rows["MCP"]["status"] == "ok"
    assert rows["MCP"]["error_count"] == 1
    assert rows["MCP"]["notes"] == "error count uses local status window"
    assert rows["Document Processor"]["minutes_down"] == 5
    assert rows["Document Processor"]["error_count"] == 1
    assert rows["Web"]["error_count"] == 0
    assert rows["Web"]["notes"] == "error count uses failed health probes"
    assert any(incident["system"] == "API" for incident in payload["incidents"])


def test_daily_stats_rejects_invalid_window_alias(monkeypatch) -> None:
    monkeypatch.delenv("JURISDIGTA_DAILY_STATS_TOKEN", raising=False)

    response = client.get("/v1/monitoring/daily-stats?window=24d", headers=AUTH_HEADERS)

    assert response.status_code == 422


def test_daily_stats_reports_unknown_when_history_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("JURISDIGTA_DAILY_STATS_TOKEN", raising=False)
    monkeypatch.setenv("PROMETHEUS_BASE_URL", "")
    _stub_status_sources(monkeypatch)
    monkeypatch.setattr(daily_stats_api, "_prometheus_query_value", lambda _expression: None)

    response = client.get("/v1/monitoring/daily-stats", headers=AUTH_HEADERS)

    assert response.status_code == 200
    rows = {row["system"]: row for row in response.json()["systems"]}
    assert rows["Web"]["status"] == "error"
    assert rows["Web"]["minutes_down"] == "unknown"
    assert rows["Web"]["error_count"] == "unknown"
    assert "live probe status unavailable" in rows["Web"]["notes"]
    assert "historical Prometheus downtime unavailable" in rows["Web"]["notes"]


def _stub_status_sources(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        daily_stats_api,
        "_api_status_payload",
        lambda: {"status": "ok"},
    )
    monkeypatch.setattr(
        daily_stats_api,
        "_laws_collector_status_payload",
        lambda: {"status": "ok"},
    )
    monkeypatch.setattr(
        daily_stats_api,
        "_server_status_payload",
        lambda: {
            "status": "ok",
            "apps": {
                "mcp": {"status": "ok", "error_count": 1},
                "email_scheduler": {"status": "ok", "error_count": 0},
                "document_processor": {"status": "ok", "error_count": 4},
            },
        },
    )
    monkeypatch.setattr(
        daily_stats_api,
        "_error_counts_payload",
        lambda *, minutes: {
            "status": "ok",
            "window_minutes": minutes,
            "source": "application_insights",
            "by_application": {
                "api": 3,
                "laws_collector": 0,
                "document_processor": 1,
            },
        },
    )


def _healthy_prometheus(expression: str) -> float:
    return 1.0 if "== bool 0" not in expression else 0.0
