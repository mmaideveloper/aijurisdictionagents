"""Reporting contract checks; integration uses only the dedicated local synthetic DB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import uuid

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("user_reporting", ROOT / "Deployment/monitoring/user_reporting.py")
assert spec and spec.loader
reporting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporting)


@pytest.fixture
def db():
    try:
        conn = psycopg.connect(host="127.0.0.1", port=5432, dbname="issue806_reporting_tests",
                               user="postgres", password="postgres", connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("Dedicated local issue806_reporting_tests PostgreSQL is required")
    try:
        conn.execute((ROOT / "databases/api/migrations/806_admin_user_reporting.sql").read_text())
        conn.execute((ROOT / "databases/api/admin_reporting_access.sql").read_text())
        yield conn
    finally:
        conn.rollback()
        conn.close()


def add_user(db, created="2026-03-28T12:00:00Z"):
    uid = "synthetic-806-" + uuid.uuid4().hex
    db.execute("INSERT INTO users(user_id,email,full_name,password_hash,created_at) VALUES(%s,%s,%s,%s,%s)",
               (uid, uid + "@example.invalid", "Synthetic", "unusable", created))
    return uid


def add_usage(db, uid, *, start="2026-03-29T10:00:00Z", question="", metadata="{}"):
    db.execute("""INSERT INTO ai_model_usage_ledger(usage_id,user_id,provider,model,route_type,
        input_tokens,cached_input_tokens,output_tokens,total_tokens,request_started_at,
        request_completed_at,created_at,question_id,audit_metadata_json)
        VALUES(%s,%s,'synthetic','synthetic','test',100,40,25,125,%s,%s,%s,%s,%s)""",
        (str(uuid.uuid4()), uid, start, start, start, question, metadata))


def test_dashboard_has_private_sql_sources_and_all_pages():
    dashboard = reporting.build_dashboard()
    assert dashboard["timezone"] == "Europe/Bratislava"
    sql_panels = [p for p in dashboard["panels"] if p.get("datasource") == reporting.DATA_SOURCE]
    assert len(sql_panels) == 7
    assert sum(p["title"] == "Total registered users" for p in dashboard["panels"]) == 1
    assert not any("jurisdigta_users_" in str(p) for p in dashboard["panels"])
    assert "generate_series" in next(v["query"] for v in dashboard["templating"]["list"] if v["name"] == "users_page")


@pytest.mark.parametrize("members", [[], [{"role": "Viewer"}], [{"role": "Admin"}, {"role": "Editor"}]])
def test_members_fail_closed(members):
    with pytest.raises(ValueError):
        reporting.validate_members(members)


def test_calendar_days_and_latest_limit(db):
    for _ in range(11):
        add_user(db)
    bounds = ("2026-03-28T00:00:00+01:00", "2026-03-31T00:00:00+02:00")
    rows = db.execute("SELECT * FROM admin_reporting.registrations(%s,%s)", bounds).fetchall()
    assert [r[1] for r in rows] == [11, 0, 0]
    assert rows[2][0] - rows[1][0] == timedelta(hours=23)
    latest = db.execute("SELECT * FROM admin_reporting.latest_users(%s,%s)", bounds).fetchall()
    assert len(latest) == 10
    assert [r[0] for r in latest] == sorted(r[0] for r in latest)


def test_autumn_dst_and_empty_results(db):
    rows = db.execute("SELECT * FROM admin_reporting.registrations(%s,%s)",
                      ("2026-10-24T00:00:00+02:00", "2026-10-27T00:00:00+01:00")).fetchall()
    assert [r[1] for r in rows] == [0, 0, 0]
    assert rows[2][0] - rows[1][0] == timedelta(hours=25)
    assert db.execute("SELECT * FROM admin_reporting.latest_users('2026-01-01','2026-02-01')").fetchall() == []


def test_background_usage_is_not_activity_and_restriction_removes_identified_rows(db):
    uid = add_user(db)
    now = datetime.now(timezone.utc)
    db.execute("UPDATE admin_reporting.coverage SET started_at=%s", (now-timedelta(days=2),))
    add_usage(db, uid, start=now.isoformat())
    assert db.execute("SELECT count(*) FROM admin_reporting.daily_activity").fetchone()[0] == 0
    add_usage(db, uid, start=now.isoformat(), question="synthetic-question")
    db.execute("INSERT INTO admin_reporting.excluded_users VALUES(%s,'restricted')", (uid,))
    assert db.execute("SELECT * FROM admin_reporting.total_users()").fetchone()[0] == 0
    db.execute("SELECT admin_reporting.prune_activity()")
    assert db.execute("SELECT count(*) FROM admin_reporting.daily_activity").fetchone()[0] == 0


def test_tokens_zero_usage_estimation_reconciliation_and_exclusions(db):
    uid = add_user(db)
    zero = add_user(db)
    excluded = add_user(db)
    db.execute("INSERT INTO admin_reporting.excluded_users VALUES(%s,'synthetic')", (excluded,))
    add_usage(db, uid, metadata='{"token_counting":"estimated_characters_div_4"}')
    add_usage(db, uid)
    add_usage(db, excluded)
    add_usage(db, "")
    bounds = ("2026-03-01T00:00:00Z", "2026-04-01T00:00:00Z")
    rows = db.execute("SELECT * FROM admin_reporting.user_tokens(%s,%s)", bounds).fetchall()
    by_user = {r[0]: r for r in rows}
    assert by_user[uid][1:8] == (200, 80, 50, 250, 2, 1, 1)
    assert by_user[zero][1:6] == (0, 0, 0, 0, 0)
    assert excluded not in by_user
    summary = db.execute("SELECT * FROM admin_reporting.token_reconciliation(%s,%s)", bounds).fetchall()
    assert sum(r[1] for r in summary) == 500
    first = db.execute("SELECT * FROM admin_reporting.user_tokens(%s,%s,0,1,'tokens')", bounds).fetchone()
    assert first[0] == uid and first[-1] == 2
    second = db.execute("SELECT * FROM admin_reporting.user_tokens(%s,%s,1,1,'tokens')", bounds).fetchone()
    assert second[0] == zero


def test_read_role_cannot_query_raw_tables_or_capture_activity(db):
    db.execute("SET LOCAL ROLE jurisdigta_user_report")
    assert db.execute("SELECT * FROM admin_reporting.total_users()").fetchone() is not None
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("SELECT email,password_hash FROM public.users")


def test_public_cannot_execute_reports(db):
    db.execute("CREATE ROLE issue806_unauthorized NOLOGIN")
    db.execute("SET LOCAL ROLE issue806_unauthorized")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("SELECT * FROM admin_reporting.total_users()")


@pytest.mark.parametrize("query", [
    "SELECT * FROM admin_reporting.registrations('2026-01-01','2028-01-01')",
    "SELECT * FROM admin_reporting.latest_users('infinity','infinity')",
    "SELECT * FROM admin_reporting.user_tokens('2026-01-01','2026-02-01',0,101,'tokens')",
    "SELECT * FROM admin_reporting.user_tokens('2026-01-01','2026-02-01',-1,10,'tokens')",
    "SELECT * FROM admin_reporting.user_tokens('2026-01-01','2026-02-01',0,10,'invalid')",
])
def test_invalid_parameters_fail(db, query):
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute(query)


def test_activity_deduplicated_retained_and_deleted(db):
    uid = add_user(db)
    now = datetime.now(timezone.utc)
    db.execute("UPDATE admin_reporting.coverage SET started_at=%s", (now-timedelta(days=2),))
    for _ in range(2):
        add_usage(db, uid, start=now.isoformat(), question=str(uuid.uuid4()))
    add_usage(db, uid, start=now.isoformat())  # background usage cannot add an active user
    assert db.execute("SELECT count(*) FROM admin_reporting.daily_activity WHERE user_id=%s", (uid,)).fetchone()[0] == 1
    db.execute("INSERT INTO admin_reporting.daily_activity VALUES(%s,CURRENT_DATE-100)", (uid,))
    db.execute("SELECT admin_reporting.prune_activity()")
    assert db.execute("SELECT count(*) FROM admin_reporting.daily_activity WHERE user_id=%s", (uid,)).fetchone()[0] == 1
    rows = db.execute("SELECT * FROM admin_reporting.daily_active(%s,%s)", (now-timedelta(days=5),now)).fetchall()
    assert rows[0][1] is None and rows[-1][1] == 1
    db.execute("DELETE FROM users WHERE user_id=%s", (uid,))
    assert db.execute("SELECT count(*) FROM admin_reporting.daily_activity WHERE user_id=%s", (uid,)).fetchone()[0] == 0
