from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.main import app
from app.observability import (
    AzureApplicationInsightsLogService,
    ObservabilityConfigurationError,
    ObservabilityLogRecord,
    ObservabilityQueryResult,
)

client = TestClient(app)


@dataclass(frozen=True)
class _FakeColumn:
    name: str


@dataclass(frozen=True)
class _FakeTable:
    columns: tuple[_FakeColumn, ...]
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class _FakeResult:
    tables: tuple[_FakeTable, ...]


class _FakeLogsQueryClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def query_workspace(self, *, workspace_id: str, query: str, timespan: object) -> _FakeResult:
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "query": query,
                "timespan": timespan,
            }
        )
        if "summarize count=count()" in query:
            return _FakeResult(
                tables=(
                    _FakeTable(
                        columns=(
                            _FakeColumn("application"),
                            _FakeColumn("level"),
                            _FakeColumn("source"),
                            _FakeColumn("count"),
                        ),
                        rows=(
                            ("api", "error", "exception", 2),
                            ("document_processor", "info", "trace", 1),
                        ),
                    ),
                ),
            )

        return _FakeResult(
            tables=(
                _FakeTable(
                    columns=(
                        _FakeColumn("timestamp"),
                        _FakeColumn("application"),
                        _FakeColumn("level"),
                        _FakeColumn("source"),
                        _FakeColumn("message"),
                        _FakeColumn("operation_id"),
                        _FakeColumn("request_id"),
                        _FakeColumn("operation_name"),
                        _FakeColumn("result_code"),
                        _FakeColumn("success"),
                        _FakeColumn("duration_ms"),
                        _FakeColumn("exception_type"),
                        _FakeColumn("problem_id"),
                    ),
                    rows=(
                        (
                            "2026-04-03T10:00:00Z",
                            "api",
                            "error",
                            "exception",
                            "failure",
                            "op-1",
                            "req-1",
                            "GET /health",
                            "500",
                            False,
                            34.0,
                            "RuntimeError",
                            "problem-1",
                        ),
                    ),
                ),
            ),
        )


def test_observability_service_requires_connection_string(monkeypatch) -> None:
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_LOG_ANALYTICS_WORKSPACE_NAME", raising=False)
    monkeypatch.delenv("APPLICATIONINSIGHTS_LOGS_WORKSPACE_ID", raising=False)

    try:
        AzureApplicationInsightsLogService.from_env()
    except ObservabilityConfigurationError as exc:
        assert "APPLICATIONINSIGHTS_CONNECTION_STRING" in str(exc)
    else:
        raise AssertionError("Expected configuration error")


def test_observability_service_queries_workspace_and_shapes_results() -> None:
    service = AzureApplicationInsightsLogService(
        workspace_name="law-logs",
        workspace_id="workspace-123",
        connection_string="InstrumentationKey=test",
        managed_identity_name="observability-mi",
        subscription_id="sub-123",
        resource_group="rg-observability",
    )
    fake_client = _FakeLogsQueryClient()
    service._build_client = lambda: fake_client  # type: ignore[method-assign]

    result = service.query_logs(
        minutes=30,
        limit=25,
        application="api",
        level="error",
        source="exception",
    )

    assert result.total_count == 3
    assert result.by_application == {"api": 2, "document_processor": 1}
    assert result.by_level == {"error": 2, "info": 1}
    assert result.by_source == {"exception": 2, "trace": 1}
    assert result.records[0].application == "api"
    assert result.records[0].level == "error"
    assert result.records[0].source == "exception"
    assert result.records[0].exception_type == "RuntimeError"
    assert result.records[0].success is False
    assert result.records[0].duration_ms == 34.0
    assert len(fake_client.calls) == 2
    assert fake_client.calls[0]["workspace_id"] == "workspace-123"
    assert "application in ('api')" in str(fake_client.calls[0]["query"])
    assert "level == 'error'" in str(fake_client.calls[0]["query"])
    assert "source == 'exception'" in str(fake_client.calls[0]["query"])


def test_observability_service_resolves_workspace_customer_id_from_name(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_CLIENT_ID", "mi-client-id")
    service = AzureApplicationInsightsLogService(
        workspace_name="law-logs",
        workspace_id="",
        connection_string="InstrumentationKey=test",
        managed_identity_name="observability-mi",
        subscription_id="sub-123",
        resource_group="rg-observability",
    )
    service._arm_get = lambda **_: {  # type: ignore[method-assign]
        "properties": {"customerId": "workspace-789"}
    }

    assert service._resolve_workspace_id() == "workspace-789"
    assert service._resolve_workspace_id() == "workspace-789"


def test_observability_endpoint_returns_logs(monkeypatch) -> None:
    class FakeService:
        def query_logs(
            self,
            *,
            minutes: int,
            limit: int,
            application: str | None,
            level: str | None,
            source: str | None,
        ) -> ObservabilityQueryResult:
            assert minutes == 45
            assert limit == 10
            assert application == "laws_collector"
            assert level == "warning"
            assert source == "trace"
            return ObservabilityQueryResult(
                minutes=minutes,
                application="laws_collector",
                level="warning",
                source="trace",
                total_count=1,
                by_application={"laws_collector": 1},
                by_level={"warning": 1},
                by_source={"trace": 1},
                records=[
                    ObservabilityLogRecord(
                        timestamp="2026-04-03T10:00:00Z",
                        application="laws_collector",
                        level="warning",
                        source="trace",
                        message="collector warning",
                        operation_id="op-2",
                        request_id="",
                        operation_name="",
                        result_code="",
                        success=None,
                        duration_ms=None,
                        exception_type="",
                        problem_id="",
                    ),
                ],
            )

    monkeypatch.setattr(
        "app.observability_api.AzureApplicationInsightsLogService.from_env",
        lambda: FakeService(),
    )

    response = client.get(
        "/v1/observability/logs?minutes=45&limit=10&application=laws_collector&level=warning&source=trace",
        headers={"x-api-key": "aijuris"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"] == {
        "minutes": 45,
        "application": "laws_collector",
        "level": "warning",
        "source": "trace",
    }
    assert payload["summary"]["total_count"] == 1
    assert payload["records"][0]["message"] == "collector warning"


def test_observability_endpoint_reports_missing_configuration(monkeypatch) -> None:
    def raise_configuration_error() -> object:
        raise ObservabilityConfigurationError(
            "AZURE_LOG_ANALYTICS_WORKSPACE_NAME is not configured."
        )

    monkeypatch.setattr(
        "app.observability_api.AzureApplicationInsightsLogService.from_env",
        raise_configuration_error,
    )

    response = client.get(
        "/v1/observability/logs",
        headers={"x-api-key": "aijuris"},
    )

    assert response.status_code == 503
    assert "AZURE_LOG_ANALYTICS_WORKSPACE_NAME" in response.json()["detail"]


def test_observability_endpoint_requires_api_key() -> None:
    response = client.get("/v1/observability/logs")

    assert response.status_code == 401
