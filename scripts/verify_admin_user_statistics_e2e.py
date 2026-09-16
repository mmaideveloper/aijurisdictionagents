"""Verify #815 panels against the completed synthetic local real-model #806-style run."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import psycopg
import requests

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if not evidence.is_relative_to(ROOT / "runs/e2e/issue815"):
        raise ValueError("Use the ignored #815 evidence directory")
    manifest = json.loads((evidence / "final-result.json").read_text())
    assert manifest["status"] == "passed" and manifest["syntheticOnly"] is True
    assert manifest["observedProvider"] == "azurefoundryeu" and manifest["observedModel"] == "gpt-5-mini"
    user = json.loads((ROOT / "runs/storage/issue815-user.json").read_text())
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    with psycopg.connect(host="127.0.0.1", port=5815, dbname="issue815_reporting",
                        user="postgres", password="postgres") as db:
        earliest = db.execute("SELECT min(created_at::timestamptz) FROM users").fetchone()[0]
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 13
        assert db.execute("SELECT count(*) FROM admin_reporting.deleted_users WHERE reportable").fetchone()[0] == 1
    with requests.Session() as session:
        for c in json.loads((ROOT / "runs/storage/grafana815-session.json").read_text())["cookies"]:
            session.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])

        def query(sql: str) -> list[tuple]:
            response = session.post("http://127.0.0.1:3815/api/ds/query", timeout=20,
                json={"from": str(int(start.timestamp()*1000)), "to": str(int(now.timestamp()*1000)),
                      "queries": [{"refId": "A", "datasource": {"uid": "jurisdigta-user-reporting",
                        "type": "grafana-postgresql-datasource"}, "format": "table", "rawSql": sql}]})
            assert response.ok
            result = response.json()["results"]["A"]
            assert not result.get("error")
            return list(zip(*result["frames"][0]["data"]["values"]))

        period = f"to_timestamp({start.timestamp()}),to_timestamp({now.timestamp()})"
        top = query(f"SELECT * FROM admin_reporting.top_token_users({period})")
        assert top[0] == ("Deleted user (deleted)", "deleted", 800000, 200000, 200000, 1000000, 1, 0, 0)
        active = next(row for row in top if row[0] == user["email"])
        assert list(active[2:6]) == manifest["expectedTokens"]
        latest = query(f"SELECT * FROM admin_reporting.latest_registrations({period})")
        assert len(latest) == 10 and latest[0][0] == user["email"]
        assert query(f"SELECT * FROM admin_reporting.users_at(to_timestamp({now.timestamp()}))") == [(13,)]
        assert query(f"SELECT * FROM admin_reporting.users_at(to_timestamp({earliest.timestamp()}))") == [(0,)]
        daily = query(f"SELECT * FROM admin_reporting.registrations({period})")
        assert sum(row[1] for row in daily) == 13
        totals = dict((row[0], row[1]) for row in query(f"SELECT * FROM admin_reporting.token_reconciliation({period})"))
        assert totals == {"deleted": 1000000, "eligible": manifest["expectedTokens"][3]}
        source = session.get("http://127.0.0.1:3815/api/datasources/uid/jurisdigta-user-reporting", timeout=15).json()
        assert source["jsonData"]["sslmode"] == "verify-full"
        health = session.get("http://127.0.0.1:3815/api/datasources/uid/jurisdigta-user-reporting/health", timeout=15)
        assert health.ok and health.json()["status"] == "OK"
    manifest["userStatistics"] = {"selectedEndCount": 13, "beforeSeedCount": 0,
        "registrationsInRange": 13, "latestRows": 10, "latestEmailMatched": True,
        "deletedRank": 1, "deletedTotalTokens": 1000000, "deletedEmailExposed": False,
        "activeTokensReconciled": True, "reconciliation": totals, "databaseTLS": "verify-full"}
    (evidence / "final-result.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Selected-date counts, emails, deleted-user ranking, token reconciliation and TLS passed.")


if __name__ == "__main__":
    main()
