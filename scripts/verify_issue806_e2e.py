"""Reconcile the real local frontend run with Grafana and write sanitized evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets

import psycopg
import requests

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if not evidence.is_relative_to(ROOT / "runs/e2e/issue806"):
        raise ValueError("Evidence must remain in the ignored task evidence directory")
    user = json.loads((ROOT / "runs/storage/issue806-user.json").read_text())
    initial = json.loads((evidence / "result.json").read_text())
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    with psycopg.connect(host="127.0.0.1", port=5432, dbname="issue806_reporting",
                         user="postgres", password="postgres") as db:
        case = db.execute("SELECT case_id FROM cases WHERE user_id=%s AND title=%s",
            (user["userId"], "Issue806 final PostgreSQL model verification")).fetchone()
        assert case
        latest = db.execute("""SELECT usage_id,provider,model,question_id,total_tokens,audit_metadata_json,
                    request_completed_at FROM ai_model_usage_ledger
                    WHERE case_id=%s ORDER BY request_completed_at DESC LIMIT 1""", (case[0],)).fetchone()
        assert latest and latest[1] == "azure_foundry" and latest[2] == "gpt-4o-mini"
        assert latest[3] and latest[4] > 0 and json.loads(latest[5]).get("model_used") is True
        expected = db.execute("""SELECT sum(input_tokens),sum(cached_input_tokens),sum(output_tokens),sum(total_tokens)
                FROM ai_model_usage_ledger WHERE user_id=%s AND request_completed_at::timestamptz >= %s
                AND request_completed_at::timestamptz < %s""", (user["userId"], start, now)).fetchone()
        expected_count = db.execute("SELECT * FROM admin_reporting.total_users()").fetchone()[0]
        activity = db.execute("SELECT count(*) FROM admin_reporting.daily_activity WHERE user_id=%s", (user["userId"],)).fetchone()[0]
        assert activity == 1
    with psycopg.connect(host="127.0.0.1", port=5433, dbname="issue806_e2e_laws",
                         user="postgres", password="postgres") as laws:
        source = laws.execute("SELECT document_id FROM law_documents WHERE document_id='issue-635-civil-code'").fetchone()
        assert source
    services = {"frontend": "http://127.0.0.1:5806", "api": "http://127.0.0.1:8806/health",
                "mcp": "http://127.0.0.1:8706/health", "grafana": "http://127.0.0.1:3806/api/health"}
    for url in services.values():
        assert requests.get(url, timeout=10).ok
    listed = requests.get("http://127.0.0.1:8806/v1/cases", params={"user_id": user["userId"]},
                          headers={"x-api-key": "aijuris"}, timeout=15)
    assert listed.ok and case[0] in listed.text
    with requests.Session() as session:
        for cookie in json.loads((ROOT / "runs/storage/grafana806-session.json").read_text())["cookies"]:
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
        payload = {"from": str(int(start.timestamp()*1000)), "to": str(int(now.timestamp()*1000)),
                   "queries": [{"refId": "A", "datasource": {"uid": "jurisdigta-user-reporting",
                       "type": "grafana-postgresql-datasource"}, "format": "table", "rawSql":
                       f"SELECT * FROM admin_reporting.user_tokens(to_timestamp({start.timestamp()}),to_timestamp({now.timestamp()}))"}]}
        response = session.post("http://127.0.0.1:3806/api/ds/query", json=payload, timeout=20)
        assert response.ok
        result = response.json()["results"]["A"]
        assert not result.get("error")
        frame = result["frames"][0]
        rows = list(zip(*frame["data"]["values"]))
        observed = next(r for r in rows if r[0] == user["userId"])
        assert tuple(observed[1:5]) == tuple(expected)
        assert observed[-1] == expected_count == 13
        # The viewer was created by this task in the fresh loopback Grafana.
        # Rotate its temporary password without exposing it, then test both paths.
        temporary_password = secrets.token_urlsafe(32)
        reset = session.put(f"http://127.0.0.1:3806/api/admin/users/{initial['viewerId']}/password",
                            json={"password": temporary_password}, timeout=15)
        assert reset.ok, "Cannot prepare the synthetic viewer for proxy verification"
        with requests.Session() as viewer:
            viewer.auth = (initial["runId"], temporary_password)
            denied_query = viewer.post("http://127.0.0.1:3806/api/ds/query", json=payload,
                headers={"X-Grafana-Org-Id": str(initial["grafanaOrg"])}, timeout=15)
            denied_proxy = viewer.get("http://127.0.0.1:3806/api/datasources/proxy/uid/jurisdigta-user-reporting/",
                headers={"X-Grafana-Org-Id": str(initial["grafanaOrg"])}, timeout=15)
            assert denied_query.status_code in (401, 403, 404)
            assert denied_proxy.status_code in (401, 403, 404)
    for filename in ("03-final-frontend.png", "04-final-grafana.png"):
        assert (evidence / filename).stat().st_size > 1000
    assert initial["unauthorizedQueryStatus"] in (401, 403, 404)
    manifest = {"runId": user["runId"], "syntheticOnly": True, "services": services,
                "databases": ["issue806_reporting", "issue806_e2e_laws"],
                "expectedProvider": "azure_foundry", "observedProvider": latest[1],
                "expectedModel": "gpt-4o-mini", "observedModel": latest[2],
                "caseId": case[0], "usageId": latest[0], "questionId": latest[3],
                "userId": user["userId"], "expectedTokens": list(expected),
                "observedTokens": list(observed[1:5]), "expectedUsers": 13, "observedUsers": observed[-1],
                "observedActivityDays": activity, "coverage": "first partial day omitted from complete-day graph",
                "expectedSourceSeed": "issue-635-civil-code", "observedSourceSeed": source[0],
                "unauthorizedQueryStatus": initial["unauthorizedQueryStatus"],
                "unauthorizedProxyStatus": denied_proxy.status_code,
                "screenshots": ["03-final-frontend.png", "04-final-grafana.png"],
                "retentionDays": 7, "status": "passed", "cleanup": "pending"}
    (evidence / "final-result.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Local real-model reporting reconciliation passed; tokens:", list(expected))
    print("Sanitized manifest:", evidence / "final-result.json")


if __name__ == "__main__":
    main()
