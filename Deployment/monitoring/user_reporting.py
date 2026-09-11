"""Build/provision the existing dashboard in a private Grafana organization.

No credentials are stored in a file or supplied as command-line arguments.
"""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA_SOURCE = {"type": "grafana-postgresql-datasource", "uid": "jurisdigta-user-reporting"}


def build_dashboard() -> dict[str, Any]:
    dashboard: dict[str, Any] = json.loads((ROOT / "Deployment/monitoring/grafana/dashboards/"
                                 "jurisdigta-application-performance.json").read_text(encoding="utf-8"))
    # Existing performance panels are retained; replace the original user panels.
    dashboard["panels"] = [p for p in dashboard["panels"]
                           if not any("jurisdigta_users_" in str(t) for t in p.get("targets", []))]
    for panel in dashboard["panels"]:
        panel["gridPos"]["y"] += 33
    panel_id = max(p["id"] for p in dashboard["panels"]) + 1
    period = "to_timestamp(${__from}/1000.0), to_timestamp(${__to}/1000.0)"
    specifications = [
        ("Total registered users", "stat", "SELECT * FROM admin_reporting.total_users()",
         "Current eligible accounts, including disabled accounts; independent of the date range."),
        ("New registrations per day", "timeseries", f"SELECT * FROM admin_reporting.registrations({period})",
         "Europe/Bratislava calendar days. Range edges may be partial days. Current retained account records."),
        ("Daily active users (complete collection days)", "timeseries", f"SELECT * FROM admin_reporting.daily_active({period})",
         "Distinct users creating a case or submitting a recorded question. Null before collection/retention coverage."),
        ("Latest 10 new users", "table", f"SELECT * FROM admin_reporting.latest_users({period})",
         "The latest registrations within the selected range. Restricted personal data: user ID and registration time."),
        ("Tokens per user", "table",
         f"SELECT * FROM admin_reporting.user_tokens({period}, (${{users_page:sqlstring}}::integer - 1)*100, 100, ${{users_sort:sqlstring}})",
         "100 users per page; total_rows gives the available count. Cached input is already included in input. "
         "estimated_entries and unspecified_entries disclose accuracy. All providers and ledger statuses; "
         "each usage_id counted once. Zero usage included. Page selector supports every page."),
        ("Token reconciliation", "table", f"SELECT * FROM admin_reporting.token_reconciliation({period})",
         "Eligible + excluded + unattributed = ledger total for the range. No excluded/orphaned IDs are exposed."),
        ("Activity coverage", "table", "SELECT * FROM admin_reporting.activity_coverage()",
         "Collection starts when the migration is installed. Daily facts expire after 90 calendar days; no historical backfill."),
    ]
    layouts = [(0, 0, 6, 8), (6, 0, 18, 8), (0, 8, 12, 8), (12, 8, 12, 8),
               (0, 16, 24, 10), (0, 26, 12, 7), (12, 26, 12, 7)]
    for i, (title, kind, query, description) in enumerate(specifications):
        x, y, width, height = layouts[i]
        dashboard["panels"].append({
            "id": panel_id + i, "title": title, "description": description, "type": kind,
            "datasource": DATA_SOURCE, "gridPos": {"x": x, "y": y, "w": width, "h": height},
            "fieldConfig": {"defaults": {"unit": "short", "noValue": "Unavailable"}, "overrides": [
                {"matcher": {"id": "byName", "options": field}, "properties": [
                    {"id": "displayName", "value": label}, {"id": "custom.width", "value": width}
                ]} for field, label, width in [
                    ("user_id", "User ID", 330), ("input_tokens", "Input", 85),
                    ("cached_input_tokens", "Cached input", 100), ("output_tokens", "Output", 85),
                    ("total_tokens", "Total", 85), ("ledger_entries", "Entries", 85),
                    ("estimated_entries", "Estimated", 90), ("unspecified_entries", "Unspecified", 105),
                    ("total_rows", "Users", 70), ("registered_at", "Registered", 200)
                ]
            ]},
            "options": {"showHeader": True, "cellHeight": "sm",
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
            "targets": [{"refId": "A", "datasource": DATA_SOURCE, "rawSql": query,
                         "format": "time_series" if kind == "timeseries" else "table", "rawQuery": True}],
        })
    dashboard.update(id=None, uid="jurisdigta-admin-users", title="JurisDigta Admin Users and Performance",
                     editable=False, timezone="Europe/Bratislava", refresh="1m",
                     time={"from": "now-30d", "to": "now"}, version=1)
    dashboard.setdefault("templating", {}).setdefault("list", []).extend([
        {"name": "users_page", "label": "Users page (100 per page)", "type": "query",
         "datasource": DATA_SOURCE, "refresh": 1, "multi": False, "includeAll": False,
         "query": "SELECT generate_series(1, greatest(1, ceil(total_users/100.0)::integer)) AS __value FROM admin_reporting.total_users()",
         "current": {"text": "1", "value": "1"}},
        {"name": "users_sort", "label": "Users sort", "type": "custom", "query": "tokens,user",
         "current": {"text": "tokens", "value": "tokens"}, "multi": False, "includeAll": False},
    ])
    return dashboard


def validate_members(members: list[dict[str, Any]]) -> None:
    if not members or any(member.get("role") != "Admin" for member in members):
        raise ValueError("Reporting organization must contain only authorized Admin members")


def provision(base_url: str, org_id: int, session: requests.Session,
              database: dict[str, Any]) -> None:
    if org_id <= 1:
        raise ValueError("Choose a dedicated reporting organization, never the default organization")
    parsed = urlsplit(base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Grafana URL must not contain credentials, query or fragment")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise ValueError("Use HTTPS or an SSH-forwarded loopback Grafana URL")
    base_url = base_url.rstrip("/")

    def call(method: str, path: str, payload: Any = None) -> Any:
        response = session.request(method, base_url + path, json=payload,
                                   headers={"X-Grafana-Org-Id": str(org_id)}, timeout=20,
                                   allow_redirects=False)
        if not 200 <= response.status_code < 300:
            # Never include response bodies or request headers in exceptions.
            raise RuntimeError(f"Grafana {method} {path}: HTTP {response.status_code}")
        return response.json()

    validate_members(call("GET", f"/api/orgs/{org_id}/users"))
    # The caller must provision equivalent aggregate sources deliberately in the
    # private organization; never copy encrypted secrets out of another org.
    sources = call("GET", "/api/datasources")
    required = {"jurisdigta-prometheus", "jurisdigta-loki"}
    if not required.issubset({source["uid"] for source in sources}):
        raise ValueError("Provision private-organization Prometheus and Loki sources first")
    data_source = dict(database, name="Admin user reporting", uid=DATA_SOURCE["uid"],
                       type=DATA_SOURCE["type"], access="proxy", isDefault=False, readOnly=True)
    existing = next((s for s in sources if s["uid"] == DATA_SOURCE["uid"]), None)
    if existing:
        call("PUT", f"/api/datasources/uid/{DATA_SOURCE['uid']}", data_source)
    else:
        call("POST", "/api/datasources", data_source)
    validate_members(call("GET", f"/api/orgs/{org_id}/users"))
    call("POST", "/api/dashboards/db", {"dashboard": build_dashboard(), "overwrite": True})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Print the credential-free dashboard JSON")
    parser.add_argument("--grafana-url", default="http://127.0.0.1:3000")
    parser.add_argument("--org-id", type=int)
    parser.add_argument("--database-host", help="PostgreSQL host:port reachable from Grafana")
    parser.add_argument("--database-name")
    args = parser.parse_args()
    if args.preview:
        print(json.dumps(build_dashboard(), indent=2))
        return
    if not args.org_id or not args.database_host or not args.database_name:
        parser.error("--org-id, --database-host and --database-name are required")
    with requests.Session() as session:
        session.auth = (input("Grafana server admin login: "), getpass.getpass("Grafana password: "))
        provision(args.grafana_url, args.org_id, session, {
            "url": args.database_host, "user": "jurisdigta_user_report",
            "jsonData": {"database": args.database_name, "sslmode": "require",
                         "postgresVersion": 1600, "timescaledb": False, "maxOpenConns": 2,
                         "maxIdleConns": 1, "connMaxLifetime": 60},
            "secureJsonData": {"password": getpass.getpass("Reporting database password: ")},
        })
    print("Private admin user dashboard provisioned. Validate authorization before rollout.")


if __name__ == "__main__":
    main()
