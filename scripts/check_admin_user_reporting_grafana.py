"""Synthetic localhost Grafana/PostgreSQL integration check, not final model E2E.

Requires issue806_reporting on local PostgreSQL and an isolated fresh Grafana at
127.0.0.1:3806. Temporary browser cookies are runtime credentials, not evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import secrets
import time
import uuid

import psycopg
from psycopg import sql
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3806"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-dashboard", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("reporting", ROOT / "Deployment/monitoring/user_reporting.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if args.refresh_dashboard:
        with requests.Session() as session:
            for cookie in json.loads((ROOT / "runs/storage/grafana806-session.json").read_text())["cookies"]:
                session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
            response = session.post(BASE + "/api/dashboards/db", timeout=20,
                json={"dashboard": module.build_dashboard(), "overwrite": True})
            if not response.ok:
                raise RuntimeError(f"Dashboard refresh failed: {response.status_code}")
        print("Local dashboard refreshed.")
        return
    run_id = "issue806-" + uuid.uuid4().hex[:10]
    evidence = ROOT / "runs/e2e/issue806" / run_id
    evidence.mkdir(parents=True)
    private = ROOT / "runs/storage/grafana806-session.json"
    report_password = secrets.token_urlsafe(32)
    viewer_password = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(32)
    with psycopg.connect(host="127.0.0.1", port=5432, dbname="issue806_reporting",
                         user="postgres", password="postgres") as db:
        db.execute((ROOT / "databases/api/admin_reporting_access.sql").read_text())
        db.execute(sql.SQL("ALTER ROLE jurisdigta_user_report PASSWORD {}").format(sql.Literal(report_password)))
        # Owned synthetic run records; do not edit application/production accounts.
        for index in range(12):
            user_id = f"{run_id}-{index:02}"
            db.execute("""INSERT INTO users(user_id,email,full_name,password_hash,created_at)
                VALUES(%s,%s,'Synthetic Grafana acceptance','unusable',%s)""",
                (user_id, f"{user_id}@example.invalid", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    with requests.Session() as session:
        session.auth = ("admin", "admin")  # fresh loopback-only test Grafana default
        for _ in range(30):
            try:
                if session.get(BASE + "/api/health", timeout=2).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)

        def call(method, path, payload=None, org=None):
            response = session.request(method, BASE + path, json=payload,
                                       headers={"X-Grafana-Org-Id": str(org)} if org else {}, timeout=20)
            if not response.ok:
                raise RuntimeError(f"Grafana {method} {path} failed: {response.status_code}")
            return response.json()

        call("PUT", "/api/user/password", {"oldPassword": "admin", "newPassword": admin_password,
                                             "confirmNew": admin_password})
        session.auth = ("admin", admin_password)
        org = call("POST", "/api/orgs", {"name": run_id})["orgId"]
        for name, kind, uid, url in [
            ("Prometheus", "prometheus", "jurisdigta-prometheus", "http://host.docker.internal:9091"),
            ("Loki", "loki", "jurisdigta-loki", "http://host.docker.internal:3100"),
        ]:
            call("POST", "/api/datasources", {"name": name, "type": kind, "uid": uid,
                 "url": url, "access": "proxy"}, org)
        module.provision(BASE, org, session, {
            "url": "host.docker.internal:5432", "user": "jurisdigta_user_report",
            "jsonData": {"database": "issue806_reporting", "sslmode": "disable", "postgresVersion": 1600},
            "secureJsonData": {"password": report_password},
        })
        query = {"queries": [{"refId": "A", "datasource": module.DATA_SOURCE, "rawSql":
                 "SELECT * FROM admin_reporting.total_users()", "format": "table"}],
                 "from": "now-30d", "to": "now"}
        actual = call("POST", "/api/ds/query", query, org)
        result = actual["results"]["A"]
        if result.get("error"):
            raise RuntimeError("Grafana reporting SQL query failed")
        observed_total = result["frames"][0]["data"]["values"][0][0]
        assert observed_total == 12, "Synthetic total must equal seeded account count"
        viewer = call("POST", "/api/admin/users", {"name": "Synthetic Viewer", "login": run_id,
                       "email": run_id + "@example.invalid", "password": viewer_password, "OrgId": 1})
        session.auth = (run_id, viewer_password)
        denied = session.post(BASE + "/api/ds/query", json=query,
                              headers={"X-Grafana-Org-Id": str(org)}, timeout=20)
        assert denied.status_code in {401, 403, 404}
        session.auth = ("admin", admin_password)
        login = session.post(BASE + "/login", json={"user": "admin", "password": admin_password}, timeout=20)
        assert login.ok
        session.auth = None
        call("POST", f"/api/user/using/{org}")
        private.write_text(json.dumps({"cookies": [
            {"name": c.name, "value": c.value, "domain": "127.0.0.1", "path": c.path or "/",
             "expires": c.expires or -1, "httpOnly": True, "secure": False, "sameSite": "Lax"}
            for c in session.cookies], "origins": []}), encoding="utf-8")
        manifest = {"runId": run_id, "syntheticOnly": True, "stage": "grafana-postgresql-integration",
                    "finalRealModelE2E": "pending", "expectedTotal": 12, "observedTotal": observed_total,
                    "unauthorizedQueryStatus": denied.status_code, "grafanaOrg": org,
                    "grafanaUrl": BASE + f"/d/jurisdigta-admin-users?orgId={org}",
                    "database": "issue806_reporting", "viewerId": viewer["id"], "retentionDays": 7}
        (evidence / "result.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("Grafana SQL query and unauthorized organization denial passed.")
        print("Evidence:", evidence)
        print("Dashboard:", manifest["grafanaUrl"])
        print("Temporary authenticated browser state prepared; delete after browser verification.")


if __name__ == "__main__":
    main()
