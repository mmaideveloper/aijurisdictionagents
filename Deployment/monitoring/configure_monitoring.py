from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import stat
import subprocess
import sys


DEFAULT_PROJECT_ENV = Path("/srv/jurisdigta/secrets/jurisdigta.env")
DEFAULT_PROMETHEUS_HOST_PORT = "9091"
DEFAULT_GRAFANA_DOMAIN = "admin.jurisdigta.eu"
DEFAULT_GRAFANA_ROOT_URL = "https://admin.jurisdigta.eu/grafana/"
DEFAULT_ALERT_EMAIL_TO = "info@jurisdigta.eu"


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

    return {
        "PROMETHEUS_HOST_PORT": (
            prometheus_host_port
            or _first(project_values, existing_values, "PROMETHEUS_HOST_PORT")
            or DEFAULT_PROMETHEUS_HOST_PORT
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
