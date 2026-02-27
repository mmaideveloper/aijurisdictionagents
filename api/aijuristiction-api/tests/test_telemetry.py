from __future__ import annotations

from fastapi import FastAPI

import app.telemetry as telemetry


class _DummyTracerProvider:
    def __init__(self, resource: object) -> None:
        self.resource = resource
        self.processors: list[object] = []

    def add_span_processor(self, processor: object) -> None:
        self.processors.append(processor)


def _patch_common(monkeypatch, *, otlp_endpoint: str | None) -> dict[str, object]:
    telemetry._TELEMETRY_CONFIGURED = False

    calls: dict[str, object] = {}

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_endpoint or "")
    if not otlp_endpoint:
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

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

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", lambda endpoint: ("otlp", endpoint))
    monkeypatch.setattr(telemetry, "ConsoleSpanExporter", lambda: ("console", None))
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exporter: ("batch", exporter))
    monkeypatch.setattr(telemetry, "SimpleSpanProcessor", lambda exporter: ("simple", exporter))
    return calls


def test_configure_telemetry_uses_batch_processor_for_otlp(monkeypatch) -> None:
    calls = _patch_common(monkeypatch, otlp_endpoint="http://collector:4318/v1/traces")

    app = FastAPI()
    telemetry.configure_telemetry(app, "svc", "0.1.0")

    provider = calls["provider"]
    assert isinstance(provider, _DummyTracerProvider)
    assert provider.processors == [("batch", ("otlp", "http://collector:4318/v1/traces"))]


def test_configure_telemetry_uses_simple_processor_for_console(monkeypatch) -> None:
    calls = _patch_common(monkeypatch, otlp_endpoint=None)

    app = FastAPI()
    telemetry.configure_telemetry(app, "svc", "0.1.0")

    provider = calls["provider"]
    assert isinstance(provider, _DummyTracerProvider)
    assert provider.processors == [("simple", ("console", None))]
