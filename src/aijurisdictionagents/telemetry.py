from __future__ import annotations

import logging
import os
import sys
from typing import Literal

from azure.monitor.opentelemetry import configure_azure_monitor

TelemetryMode = Literal["azure-monitor", "console"]

_TELEMETRY_CONFIGURED = False
_TELEMETRY_MODE: TelemetryMode | None = None


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


def configure_worker_telemetry(
    *,
    service_name: str,
    service_version: str,
    logger_name: str | None = None,
) -> TelemetryMode:
    global _TELEMETRY_CONFIGURED
    global _TELEMETRY_MODE

    if _TELEMETRY_CONFIGURED:
        assert _TELEMETRY_MODE is not None
        return _TELEMETRY_MODE

    _set_default_resource_attributes(service_name, service_version)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)

    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if connection_string:
        configure_azure_monitor(
            connection_string=connection_string,
            logger_name=logger_name or service_name,
        )
        _TELEMETRY_MODE = "azure-monitor"
    else:
        _TELEMETRY_MODE = "console"

    _TELEMETRY_CONFIGURED = True
    return _TELEMETRY_MODE
