from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_PROJECT_ENV = Path("/srv/jurisdigta/secrets/jurisdigta.env")
DEFAULT_PROMETHEUS_HOST_PORT = "9091"
DEFAULT_LOKI_HOST_PORT = "3100"
DEFAULT_ALLOY_HOST_PORT = "12345"
DEFAULT_LOG_RETENTION_DAYS = "7"
DEFAULT_PROMETHEUS_RETENTION_DAYS = "30"
DEFAULT_DOCKER_LOG_MAX_SIZE = "50m"
DEFAULT_DOCKER_LOG_MAX_FILE = "5"
DEFAULT_GRAFANA_DOMAIN = "admin.jurisdigta.eu"
DEFAULT_GRAFANA_ROOT_URL = "https://admin.jurisdigta.eu/grafana/"
DEFAULT_ALERT_EMAIL_TO = "info@jurisdigta.eu"
DEFAULT_APP_DOCKER_NETWORK = "aijuristiction-api_default"
DEFAULT_HOME_DASHBOARD_PATH = "/var/lib/grafana/dashboards/jurisdigta-application-performance.json"
DEFAULT_LOCAL_LLM_MODEL = "qwen3:1.7b"
DEFAULT_LOCAL_LLM_BASE_URL = "http://127.0.0.1:11434"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure the JurisDigta Prometheus and Grafana monitoring stack."
    )
    parser.add_argument(
        "--project-env",
        type=Path,
        default=DEFAULT_PROJECT_ENV,
        help="Project/server env file to read shared secrets from.",
    )
    parser.add_argument(
        "--monitoring-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Deployment/monitoring directory containing docker-compose.yml.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Monitoring env file to create/update. Defaults to <monitoring-dir>/.env.",
    )
    parser.add_argument(
        "--prometheus-host-port",
        default=None,
        help="Host port for Prometheus. Defaults to project/env value or 9091.",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start or recreate the monitoring stack after writing .env.",
    )
    parser.add_argument(
        "--reset-grafana-password",
        action="store_true",
        help="Reset Grafana's persisted admin password to GRAFANA_ADMIN_PASSWORD.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate docker compose config and dashboard JSON.",
    )
    args = parser.parse_args()

    monitoring_dir = args.monitoring_dir.resolve()
    target_env = (args.env_file or monitoring_dir / ".env").resolve()
    project_values = _read_env(args.project_env)
    existing_values = _read_env(target_env)
    values = _build_monitoring_env(
        project_values=project_values,
        existing_values=existing_values,
        prometheus_host_port=args.prometheus_host_port,
    )

    _write_env(target_env, values)
    print(f"Wrote monitoring env: {target_env}")

    if args.validate:
        _validate(monitoring_dir)
        print("Monitoring configuration validated.")

    if args.start:
        _run(["docker", "compose", "up", "-d"], cwd=monitoring_dir)
        print("Monitoring stack started.")
        _set_grafana_home_dashboard(values)

    if args.reset_grafana_password:
        _run(
            [
                "docker",
                "exec",
                "jurisdigta-grafana",
                "grafana",
                "cli",
                "admin",
                "reset-admin-password",
                values["GRAFANA_ADMIN_PASSWORD"],
            ],
            cwd=monitoring_dir,
            redact=values["GRAFANA_ADMIN_PASSWORD"],
        )
        print("Grafana admin password reset to the monitoring env value.")
        _set_grafana_home_dashboard(values)

    return 0


def _build_monitoring_env(
    *,
    project_values: dict[str, str],
    existing_values: dict[str, str],
    prometheus_host_port: str | None,
) -> dict[str, str]:
    smtp_host = _first(project_values, existing_values, "GRAFANA_SMTP_HOST", "EMAIL_SMTP_HOST")
    smtp_port = _first(project_values, existing_values, "EMAIL_SMTP_PORT") or "587"
    if smtp_host and ":" not in smtp_host:
        smtp_host = f"{smtp_host}:{smtp_port}"

    smtp_user = _first(project_values, existing_values, "GRAFANA_SMTP_USER", "EMAIL_SMTP_USERNAME")
    smtp_password = _first(
        project_values,
        existing_values,
        "GRAFANA_SMTP_PASSWORD",
        "EMAIL_SMTP_PASSWORD",
    )
    sender = (
        _first(project_values, existing_values, "GRAFANA_SMTP_FROM_ADDRESS", "EMAIL_SENDER")
        or smtp_user
        or "no-reply@jurisdigta.eu"
    )
    admin_password = (
        _first(project_values, existing_values, "GRAFANA_ADMIN_PASSWORD")
        or secrets.token_urlsafe(32)
    )
    app_network = (
        _first(project_values, existing_values, "MONITORING_APP_DOCKER_NETWORK")
        or DEFAULT_APP_DOCKER_NETWORK
    )
    local_llm_base_url = _monitoring_local_llm_base_url(
        project_values=project_values,
        existing_values=existing_values,
        app_network=app_network,
    )

    return {
        "PROMETHEUS_HOST_PORT": (
            prometheus_host_port
            or _first(project_values, existing_values, "PROMETHEUS_HOST_PORT")
            or DEFAULT_PROMETHEUS_HOST_PORT
        ),
        "LOKI_HOST_PORT": (
            _first(project_values, existing_values, "LOKI_HOST_PORT") or DEFAULT_LOKI_HOST_PORT
        ),
        "ALLOY_HOST_PORT": (
            _first(project_values, existing_values, "ALLOY_HOST_PORT") or DEFAULT_ALLOY_HOST_PORT
        ),
        "LOG_RETENTION_DAYS": (
            _first(project_values, existing_values, "LOG_RETENTION_DAYS")
            or DEFAULT_LOG_RETENTION_DAYS
        ),
        "LOKI_RETENTION_DAYS": (
            _first(project_values, existing_values, "LOKI_RETENTION_DAYS", "LOG_RETENTION_DAYS")
            or DEFAULT_LOG_RETENTION_DAYS
        ),
        "PROMETHEUS_RETENTION_DAYS": (
            _first(project_values, existing_values, "PROMETHEUS_RETENTION_DAYS")
            or DEFAULT_PROMETHEUS_RETENTION_DAYS
        ),
        "DOCKER_LOG_MAX_SIZE": (
            _first(project_values, existing_values, "DOCKER_LOG_MAX_SIZE")
            or DEFAULT_DOCKER_LOG_MAX_SIZE
        ),
        "DOCKER_LOG_MAX_FILE": (
            _first(project_values, existing_values, "DOCKER_LOG_MAX_FILE")
            or DEFAULT_DOCKER_LOG_MAX_FILE
        ),
        "MONITORING_APP_DOCKER_NETWORK": (
            app_network
        ),
        "LOCAL_LLM_BASE_URL": local_llm_base_url,
        "LOCAL_LLM_MODEL": (
            _first(project_values, existing_values, "LOCAL_LLM_MODEL") or DEFAULT_LOCAL_LLM_MODEL
        ),
        "JURISDIGTA_API_KEY": _first(project_values, existing_values, "JURISDIGTA_API_KEY", "API_KEY"),
        "GRAFANA_SERVER_DOMAIN": (
            _first(project_values, existing_values, "GRAFANA_SERVER_DOMAIN")
            or DEFAULT_GRAFANA_DOMAIN
        ),
        "GRAFANA_ROOT_URL": (
            _first(project_values, existing_values, "GRAFANA_ROOT_URL")
            or DEFAULT_GRAFANA_ROOT_URL
        ),
        "GRAFANA_SERVE_FROM_SUB_PATH": (
            _first(project_values, existing_values, "GRAFANA_SERVE_FROM_SUB_PATH") or "true"
        ),
        "GRAFANA_DEFAULT_HOME_DASHBOARD_PATH": (
            _first(project_values, existing_values, "GRAFANA_DEFAULT_HOME_DASHBOARD_PATH")
            or DEFAULT_HOME_DASHBOARD_PATH
        ),
        "GRAFANA_ADMIN_USER": _first(project_values, existing_values, "GRAFANA_ADMIN_USER") or "admin",
        "GRAFANA_ADMIN_PASSWORD": admin_password,
        "GRAFANA_SMTP_ENABLED": (
            _first(project_values, existing_values, "GRAFANA_SMTP_ENABLED")
            or ("true" if smtp_host and smtp_password else "false")
        ),
        "GRAFANA_SMTP_HOST": smtp_host,
        "GRAFANA_SMTP_USER": smtp_user,
        "GRAFANA_SMTP_PASSWORD": smtp_password,
        "GRAFANA_SMTP_FROM_ADDRESS": sender,
        "GRAFANA_SMTP_FROM_NAME": (
            _first(project_values, existing_values, "GRAFANA_SMTP_FROM_NAME")
            or "JurisDigta Grafana"
        ),
        "GRAFANA_SMTP_STARTTLS_POLICY": (
            _first(project_values, existing_values, "GRAFANA_SMTP_STARTTLS_POLICY")
            or "OpportunisticStartTLS"
        ),
        "GRAFANA_ALERT_EMAIL_TO": (
            _first(project_values, existing_values, "GRAFANA_ALERT_EMAIL_TO")
            or DEFAULT_ALERT_EMAIL_TO
        ),
    }


def _monitoring_local_llm_base_url(
    *,
    project_values: dict[str, str],
    existing_values: dict[str, str],
    app_network: str,
) -> str:
    explicit_bind = _first(project_values, existing_values, "OLLAMA_HOST_BIND")
    if explicit_bind:
        return _ollama_bind_to_base_url(explicit_bind)

    configured = _first(project_values, existing_values, "LOCAL_LLM_BASE_URL")
    if configured and not _is_loopback_url(configured):
        return configured.rstrip("/")

    gateway = _docker_network_gateway(app_network)
    if gateway:
        return f"http://{gateway}:11434"

    return (configured or DEFAULT_LOCAL_LLM_BASE_URL).rstrip("/")


def _ollama_bind_to_base_url(bind: str) -> str:
    normalized = bind.strip()
    if not normalized:
        return DEFAULT_LOCAL_LLM_BASE_URL
    if normalized.startswith(("http://", "https://")):
        return normalized.rstrip("/")
    return f"http://{normalized.rstrip('/')}"


def _is_loopback_url(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized.startswith("http://127.0.0.1:")
        or normalized.startswith("http://localhost:")
        or normalized.startswith("https://127.0.0.1:")
        or normalized.startswith("https://localhost:")
    )


def _docker_network_gateway(network: str) -> str:
    try:
        result = subprocess.run(
            ["docker", "network", "inspect", network, "--format", "{{(index .IPAM.Config 0).Gateway}}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    gateway = result.stdout.strip()
    return "" if not gateway or gateway == "<no value>" else gateway


def _first(
    project_values: dict[str, str],
    existing_values: dict[str, str],
    *keys: str,
) -> str:
    for key in keys:
        for source in (project_values, existing_values):
            value = source.get(key, "")
            if value:
                return value
    return ""


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _validate(monitoring_dir: Path) -> None:
    _run(["docker", "compose", "config", "--quiet"], cwd=monitoring_dir)
    dashboard_dir = monitoring_dir / "grafana" / "dashboards"
    for dashboard in sorted(dashboard_dir.glob("*.json")):
        json.loads(dashboard.read_text(encoding="utf-8"))


def _set_grafana_home_dashboard(values: dict[str, str]) -> None:
    admin_user = values.get("GRAFANA_ADMIN_USER") or "admin"
    admin_password = values.get("GRAFANA_ADMIN_PASSWORD") or ""
    if not admin_password:
        return
    auth = base64.b64encode(f"{admin_user}:{admin_password}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }
    body = json.dumps(
        {
            "homeDashboardUID": "jurisdigta-application-performance",
            "theme": "",
            "timezone": "",
        }
    ).encode("utf-8")
    for _attempt in range(12):
        for base_url in ("http://127.0.0.1:3000/grafana", "http://127.0.0.1:3000"):
            request = Request(
                f"{base_url}/api/org/preferences",
                data=body,
                headers=headers,
                method="PUT",
            )
            try:
                with urlopen(request, timeout=5):
                    print("Grafana home dashboard set to JurisDigta Application Performance.")
                    return
            except (OSError, URLError):
                continue
        time.sleep(2)
    print("Warning: Grafana home dashboard preference could not be updated.", file=sys.stderr)


def _run(
    command: list[str],
    *,
    cwd: Path,
    redact: str | None = None,
) -> None:
    printable = " ".join(command)
    if redact:
        printable = printable.replace(redact, "***")
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {printable}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    raise SystemExit(main())
