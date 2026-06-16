from __future__ import annotations

import os

from fastapi import FastAPI

import app.telemetry as telemetry


class _DummyTracerProvider:
    def __init__(self, resource: object) -> None:
        self.resource = resource
        self.processors: list[object] = []

    def add_span_processor(self, processor: object) -> None:
        self.processors.append(processor)


def _patch_common(
    monkeypatch,
    *,
    otlp_endpoint: str | None,
    applicationinsights_connection_string: str | None = None,
) -> dict[str, object]:
    telemetry._TELEMETRY_CONFIGURED = False
    telemetry._TELEMETRY_MODE = None

    calls: dict[str, object] = {}

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_endpoint or "")
    if not otlp_endpoint:
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        applicationinsights_connection_string or "",
    )
    if not applicationinsights_connection_string:
        monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)

    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)

    monkeypatch.setattr(telemetry, "TracerProvider", _DummyTracerProvider)
    monkeypatch.setattr(telemetry.Resource, "create", lambda attrs: attrs)

    def fake_set_tracer_provider(provider: object) -> None:
        calls["provider"] = provider

    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", fake_set_tracer_provider)
    monkeypatch.setattr(
        telemetry.FastAPIInstrumentor,
        "instrument_app",
        lambda app: calls.setdefault("instrumented", app),
    )
    monkeypatch.setattr(
        telemetry,
        "configure_azure_monitor",
        lambda **kwargs: calls.setdefault("azure_monitor", kwargs),
    )

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", lambda endpoint: ("otlp", endpoint))
    monkeypatch.setattr(telemetry, "ConsoleSpanExporter", lambda: ("console", None))
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exporter: ("batch", exporter))
    monkeypatch.setattr(telemetry, "SimpleSpanProcessor", lambda exporter: ("simple", exporter))
    return calls


def test_configure_telemetry_uses_batch_processor_for_otlp(monkeypatch) -> None:
    calls = _patch_common(monkeypatch, otlp_endpoint="http://collector:4318/v1/traces")

    mode = telemetry.configure_telemetry("svc", "0.1.0")

    provider = calls["provider"]
    assert mode == "otlp"
    assert isinstance(provider, _DummyTracerProvider)
    assert provider.processors == [("batch", ("otlp", "http://collector:4318/v1/traces"))]
    assert os.environ["OTEL_SERVICE_NAME"] == "svc"
    assert "service.version=0.1.0" in os.environ["OTEL_RESOURCE_ATTRIBUTES"]


def test_configure_telemetry_uses_simple_processor_for_console(monkeypatch) -> None:
    calls = _patch_common(monkeypatch, otlp_endpoint=None)

    mode = telemetry.configure_telemetry("svc", "0.1.0")

    provider = calls["provider"]
    assert mode == "console"
    assert isinstance(provider, _DummyTracerProvider)
    assert provider.processors == [("simple", ("console", None))]


def test_configure_telemetry_uses_azure_monitor_when_connection_string_present(monkeypatch) -> None:
    calls = _patch_common(
        monkeypatch,
        otlp_endpoint=None,
        applicationinsights_connection_string="InstrumentationKey=test-key",
    )

    mode = telemetry.configure_telemetry("svc", "0.1.0")

    assert mode == "azure-monitor"
    assert calls["azure_monitor"] == {
        "connection_string": "InstrumentationKey=test-key",
        "logger_name": "svc",
    }
    assert "provider" not in calls


def test_instrument_fastapi_skips_manual_instrumentation_for_azure_monitor(monkeypatch) -> None:
    calls = _patch_common(
        monkeypatch,
        otlp_endpoint=None,
        applicationinsights_connection_string="InstrumentationKey=test-key",
    )

    telemetry.configure_telemetry("svc", "0.1.0")
    telemetry.instrument_fastapi(FastAPI())

    assert "instrumented" not in calls


def test_instrument_fastapi_skips_manual_instrumentation_for_console(monkeypatch) -> None:
    calls = _patch_common(monkeypatch, otlp_endpoint=None)

    telemetry.configure_telemetry("svc", "0.1.0")
    telemetry.instrument_fastapi(FastAPI())

    assert "instrumented" not in calls


def test_instrument_fastapi_uses_manual_instrumentation_for_otlp(monkeypatch) -> None:
    calls = _patch_common(monkeypatch, otlp_endpoint="http://localhost:4318/v1/traces")

    app = FastAPI()
    telemetry.configure_telemetry("svc", "0.1.0")
    telemetry.instrument_fastapi(app)

    assert calls["instrumented"] is app
