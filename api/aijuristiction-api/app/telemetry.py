from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

_TELEMETRY_CONFIGURED = False
_TELEMETRY_MODE: TelemetryMode | None = None
TelemetryMode = Literal["azure-monitor", "otlp", "console"]


def _has_resource_attribute(resource_attributes: str, key: str) -> bool:
    for item in resource_attributes.split(","):
        name, _, _ = item.partition("=")
        if name.strip() == key:
            return True
    return False


def _set_default_resource_attributes(service_name: str, service_version: str) -> None:
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)

    existing = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "").strip()
    additions: list[str] = []
    if not _has_resource_attribute(existing, "service.version"):
        additions.append(f"service.version={service_version}")

    if additions:
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(filter(None, [existing, *additions]))


def configure_telemetry(service_name: str, service_version: str) -> TelemetryMode:
    global _TELEMETRY_CONFIGURED
    global _TELEMETRY_MODE

    if _TELEMETRY_CONFIGURED:
        assert _TELEMETRY_MODE is not None
        return _TELEMETRY_MODE

    _set_default_resource_attributes(service_name, service_version)

    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if connection_string:
        configure_azure_monitor(
            connection_string=connection_string,
            logger_name=service_name,
        )
        _TELEMETRY_MODE = "azure-monitor"
        _TELEMETRY_CONFIGURED = True
        return _TELEMETRY_MODE

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }
    )
    tracer_provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    exporter: SpanExporter
    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        _TELEMETRY_MODE = "otlp"
    else:
        exporter = ConsoleSpanExporter()
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        _TELEMETRY_MODE = "console"
    trace.set_tracer_provider(tracer_provider)
    _TELEMETRY_CONFIGURED = True
    return _TELEMETRY_MODE


def instrument_fastapi(app: FastAPI) -> None:
    if _TELEMETRY_MODE == "azure-monitor":
        return
    FastAPIInstrumentor.instrument_app(app)
