"""Provision reporting on the self-managed host after exact-commit deployment gates.

Uses existing container credentials in memory; never prints passwords or report rows.
Database TLS must already be configured. See docs/manual_infrastucture_setup.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str], *, data: str | None = None) -> str:
    result = subprocess.run(command, input=data, capture_output=True, text=True, timeout=60)
    if result.returncode:
        # Child stderr may contain credentials/SQL. Keep failures deliberately redacted.
        raise RuntimeError(f"{command[0]} operation failed (exit {result.returncode}); inspect securely on host")
    return result.stdout.strip()


def validate_settings(settings: dict) -> None:
    required = {"auth.anonymous": {"enabled": "false"},
                "users": {"auto_assign_org": "false", "allow_sign_up": "false"},
                "snapshots": {"enabled": "false", "external_enabled": "false"},
                "public_dashboards": {"enabled": "false"}, "server": {"router_logging": "true"}}
    for section, values in required.items():
        for key, value in values.items():
            if str(settings.get(section, {}).get(key)).lower() != value:
                raise ValueError(f"Grafana prerequisite: {section}.{key} must be {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--admin-user-id", type=int, action="append", required=True)
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--database-host", default="aijurisdiction-postgres:5432")
    parser.add_argument("--ca-file", type=Path, required=True)
    parser.add_argument("--grafana-url", default="http://127.0.0.1:3000/grafana")
    parser.add_argument("--grafana-container", default="jurisdigta-grafana")
    parser.add_argument("--postgres-container", default="aijurisdiction-postgres")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_sha):
        raise ValueError("Use the full successfully validated deployment SHA")
    if run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]) != args.expected_sha:
        raise ValueError("Checkout differs from the validated deployment commit")
    if run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"]):
        raise ValueError("Tracked deployment files must be clean")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", args.database_name):
        raise ValueError("Invalid database name")
    certificate = args.ca_file.read_text(encoding="utf-8")
    if "-----BEGIN CERTIFICATE-----" not in certificate or "PRIVATE KEY" in certificate:
        raise ValueError("Provide a public CA certificate only")
    spec = importlib.util.spec_from_file_location("user_reporting", ROOT / "Deployment/monitoring/user_reporting.py")
    assert spec and spec.loader
    reporting = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reporting)
    container = json.loads(run(["docker", "inspect", args.grafana_container]))[0]
    env = dict(item.split("=", 1) for item in container["Config"]["Env"] if "=" in item)
    base = args.grafana_url.rstrip("/")
    # Credentials may only go to the local forwarded Grafana service.
    from urllib.parse import urlsplit
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("Server provisioner requires loopback Grafana HTTP")
    with requests.Session() as session:
        session.auth = (env.get("GF_SECURITY_ADMIN_USER", "admin"), env["GF_SECURITY_ADMIN_PASSWORD"])

        def call(method: str, path: str, payload=None, org: int | None = None):
            response = session.request(method, base + path, json=payload,
                headers={"X-Grafana-Org-Id": str(org)} if org else {}, timeout=20, allow_redirects=False)
            if not response.ok:
                raise RuntimeError(f"Grafana {method} {path}: HTTP {response.status_code}")
            return response.json()

        validate_settings(call("GET", "/api/admin/settings"))
        original_members = call("GET", "/api/orgs/1/users")
        authorized = {int(member["userId"]): member for member in original_members if member["role"] == "Admin"}
        if not set(args.admin_user_id).issubset(authorized):
            raise ValueError("Selected reporting members must already be organization-1 administrators")
        orgs = call("GET", "/api/orgs")
        name = "JurisDigta Private Reporting"
        org = next((int(item["id"]) for item in orgs if item["name"] == name), None)
        if org is None:
            org = int(call("POST", "/api/orgs", {"name": name})["orgId"])
        members = call("GET", f"/api/orgs/{org}/users")
        if any(int(member["userId"]) not in args.admin_user_id for member in members):
            raise ValueError("Private reporting organization contains an unselected member")
        present = {int(member["userId"]) for member in members}
        for user_id in args.admin_user_id:
            if user_id not in present:
                call("POST", f"/api/orgs/{org}/users", {"loginOrEmail": authorized[user_id]["login"], "role": "Admin"})
        reporting.validate_members(call("GET", f"/api/orgs/{org}/users"))
        sources = call("GET", "/api/datasources", org=1)
        existing = {s["uid"] for s in call("GET", "/api/datasources", org=org)}
        for uid in ("jurisdigta-prometheus", "jurisdigta-loki"):
            source = next(s for s in sources if s["uid"] == uid)
            if uid not in existing:
                call("POST", "/api/datasources", {k: source[k] for k in ("name", "type", "uid", "url", "access")}, org)
        psql = ["docker", "exec", "-i", args.postgres_container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", args.database_name, "-At"]
        if run(psql, data="SHOW ssl;") != "on":
            raise ValueError("PostgreSQL TLS is not enabled")
        # Apply the least-privilege contract atomically; rotating a generated password
        # avoids transferring the production database administrator credential to Grafana.
        password = secrets.token_urlsafe(48)
        access = (ROOT / "databases/api/admin_reporting_access.sql").read_text()
        run(psql + ["--single-transaction"], data=access +
            "\nSET LOCAL log_statement='none';\n" +
            f"ALTER ROLE jurisdigta_user_report PASSWORD '{password}';\n")
        reporting.provision(base, org, session, {
            "url": args.database_host, "user": "jurisdigta_user_report",
            "jsonData": {"database": args.database_name, "sslmode": "verify-full",
                         "tlsConfigurationMethod": "file-content", "postgresVersion": 1600,
                         "maxOpenConns": 2, "maxIdleConns": 1, "connMaxLifetime": 60},
            "secureJsonData": {"password": password, "tlsCACert": certificate},
        })
        healthy = False
        for attempt in range(6):
            response = session.get(base + "/api/datasources/uid/jurisdigta-user-reporting/health",
                headers={"X-Grafana-Org-Id": str(org)}, timeout=20, allow_redirects=False)
            if response.ok and response.json().get("status") == "OK":
                healthy = True
                break
            if attempt < 5:
                time.sleep(2)
        if not healthy:
            raise RuntimeError("Reporting data source health failed; no rows were logged")
        for user_id in args.admin_user_id:
            call("POST", f"/api/users/{user_id}/using/{org}")
        print(json.dumps({"status": "provisioned", "commit": args.expected_sha, "orgId": org,
                          "dashboardPath": f"/grafana/d/jurisdigta-admin-users?orgId={org}"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Even HTTP/OS exceptions can contain credentials; only explicit safe failures escape.
        if isinstance(error, (ValueError, RuntimeError)):
            print(str(error), file=sys.stderr)
        else:
            print(f"Reporting provisioning failed: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
