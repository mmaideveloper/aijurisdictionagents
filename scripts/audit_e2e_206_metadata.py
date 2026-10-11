"""Controlled metadata changes in the isolated synthetic #206 acceptance database."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
TARGET = "postgresql://postgres:postgres@127.0.0.1:5432/juris_audit_e2e_206"


def main() -> None:
    request = json.load(sys.stdin)
    fixture = json.loads((ROOT / "runs/e2e/issue864/input-manifest.json").read_text(encoding="utf-8"))
    if fixture.get("syntheticOnly") is not True:
        raise ValueError("Synthetic fixture required")
    with psycopg.connect(TARGET) as connection:
        row = connection.execute("SELECT title,user_id FROM cases WHERE case_id=%s", (request["case_id"],)).fetchone()
        if row != (fixture["caseTitle"], fixture["workflowUser"]["userId"]):
            raise ValueError("This run's exact synthetic case required")
        if request["action"] == "policy":
            count = connection.execute("UPDATE ai_task_route_policies SET priority=priority+1,updated_at=%s WHERE policy_id IN ('issue864:default:case','issue864:chat_reply:case')", (datetime.now(timezone.utc).isoformat(),)).rowcount
            if count != 2:
                raise ValueError("Expected isolated fixture policies")
        elif request["action"] == "expire":
            correlations = connection.execute("SELECT DISTINCT correlation_id FROM debug_trace_sessions WHERE case_id=%s AND user_id=%s", (request["case_id"], fixture["workflowUser"]["userId"])).fetchall()
            past = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            for (correlation,) in correlations:
                for table, field in (("session_debug_events", "expires_at"), ("debug_trace_sessions", "expires_at"), ("orchestration_decision_traces", "created_at"), ("case_workflow_runs", "created_at"), ("case_workflow_events", "created_at")):
                    connection.execute(sql.SQL("UPDATE {} SET {}=%s WHERE correlation_id=%s").format(sql.Identifier(table), sql.Identifier(field)), (past, correlation))
            count = len(correlations)
        else:
            raise ValueError("Unknown action")
    print(json.dumps({"changed": count, "syntheticOnly": True}))


if __name__ == "__main__":
    main()
