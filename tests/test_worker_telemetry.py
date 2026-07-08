from __future__ import annotations

import logging

import aijurisdictionagents.telemetry as telemetry


def _patch_common(
    monkeypatch,
    *,
    applicationinsights_connection_string: str | None,
    azure_monitor_enabled: str | None = None,
) -> dict[str, object]:
    telemetry._TELEMETRY_CONFIGURED = False
    telemetry._TELEMETRY_MODE = None
    logging.getLogger().handlers.clear()

    if applicationinsights_connection_string is None:
        monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    else:
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", applicationinsights_connection_string)

    if azure_monitor_enabled is None:
        monkeypatch.delenv("AZURE_MONITOR_ENABLED", raising=False)
    else:
        monkeypatch.setenv("AZURE_MONITOR_ENABLED", azure_monitor_enabled)

    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)

    calls: dict[str, object] = {}
    monkeypatch.setattr(
        telemetry,
        "configure_azure_monitor",
        lambda **kwargs: calls.setdefault("azure_monitor", kwargs),
    )
    return calls


def test_worker_telemetry_defaults_to_console_even_when_applicationinsights_is_configured(monkeypatch) -> None:
    calls = _patch_common(
        monkeypatch,
        applicationinsights_connection_string="InstrumentationKey=test-key",
    )

    mode = telemetry.configure_worker_telemetry(service_name="worker", service_version="0.1.0")

    assert mode == "console"
    assert "azure_monitor" not in calls


def test_worker_telemetry_uses_azure_monitor_when_explicitly_enabled(monkeypatch) -> None:
    calls = _patch_common(
        monkeypatch,
        applicationinsights_connection_string="InstrumentationKey=test-key",
        azure_monitor_enabled="true",
    )

    mode = telemetry.configure_worker_telemetry(
        service_name="worker",
        service_version="0.1.0",
        logger_name="worker-logger",
    )

    assert mode == "azure-monitor"
    assert calls["azure_monitor"] == {
        "connection_string": "InstrumentationKey=test-key",
        "logger_name": "worker-logger",
    }

