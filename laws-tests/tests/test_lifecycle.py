from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation

import laws_tests.app as module
from laws_tests.config import Settings
from laws_tests.db import connect, purge
from laws_tests.evaluation import Evaluation


@pytest.fixture
def signed(monkeypatch):
    cfg = Settings.load()
    assert cfg.environment != "production"
    uid, token, csrf = "unit-" + str(uuid4()), str(uuid4()), str(uuid4())
    monkeypatch.setattr(
        module.Identity, "find_user_by_id", lambda self, **kw: SimpleNamespace(is_enabled=True)
    )
    with connect(cfg.database_url) as conn:
        conn.execute(
            "INSERT INTO web_sessions VALUES(%s,%s,%s,now()+interval '1 hour')",
            (module.digest(token), uid, csrf),
        )
    try:
        with TestClient(module.create_app(cfg)) as client:
            client.cookies.set("laws_session", token)
            yield cfg, client, {"origin": cfg.public_url, "x-csrf-token": csrf}, uid
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("DELETE FROM test_sessions WHERE user_id=%s", (uid,))
            conn.execute("DELETE FROM web_sessions WHERE user_id=%s", (uid,))


def test_grouped_exam_scoring_idempotency_and_retention(signed, monkeypatch):
    cfg, client, headers, uid = signed
    calls = []

    def evaluator(*args):
        calls.append(1)
        return Evaluation(
            score=70,
            matchedPoints=["synthetic"],
            missingPoints=[],
            incorrectClaims=[],
            feedback="synthetic",
        )

    monkeypatch.setattr(module, "evaluate", evaluator)
    session = client.post(
        "/api/sessions", headers=headers, json={"test_id": "firearms-sk-2026", "mode": "exam"}
    ).json()
    assert session["question_ids"] == ["A-20", "B-1", "C-1", "D-1", "E-1"]
    payload = {
        "session_id": session["id"],
        "question_id": "A-20",
        "answer": "synthetic answer",
        "request_id": str(uuid4()),
    }
    assert client.post("/api/attempts", headers=headers, json=payload).status_code == 422
    for qid in session["question_ids"]:
        q = client.get("/api/questions/" + qid).json()
        for item in q["subquestions"] or [q]:
            payload = {
                **payload,
                "question_id": qid,
                "subquestion_id": item["id"] if q["subquestions"] else None,
                "request_id": str(uuid4()),
            }
            result = client.post("/api/attempts", headers=headers, json=payload)
            assert result.status_code == 200, result.text
            assert result.json()["passed"] is True
    assert len(calls) == 11
    assert (
        client.post("/api/attempts", headers=headers, json=payload).json()["id"]
        == result.json()["id"]
    )
    assert len(calls) == 11
    assert (
        client.post(
            "/api/attempts", headers=headers, json={**payload, "answer": "changed"}
        ).status_code
        == 409
    )
    aggregate = client.get("/api/sessions/" + session["id"] + "/result").json()
    assert aggregate == {"complete": True, "score": 70.0, "passed": True}
    progress = client.get("/api/progress").json()
    assert sum(p["answered"] for p in progress) == 11
    with connect(cfg.database_url) as conn:
        conn.execute(
            "UPDATE attempts SET created_at=now()-interval '12 months 1 day' WHERE user_id=%s",
            (uid,),
        )
        purge(conn)
        assert (
            conn.execute("SELECT count(*) AS n FROM attempts WHERE user_id=%s", (uid,)).fetchone()[
                "n"
            ]
            == 0
        )
    assert sum(p["answered"] for p in client.get("/api/progress").json()) == 0
    assert client.get("/api/history").json() == []


def test_other_user_cannot_submit_read_or_erase_session(signed):
    cfg, client, headers, uid = signed
    other = str(uuid4())
    with connect(cfg.database_url) as conn:
        conn.execute(
            "INSERT INTO test_sessions(id,user_id,test_id,mode,question_ids) VALUES(%s,%s,'firearms-sk-2026','learning','[\"E-1\"]')",
            (other, uid + "-other"),
        )
    try:
        assert client.get(f"/api/sessions/{other}/result").status_code == 404
        assert (
            client.post(
                "/api/attempts",
                headers=headers,
                json={
                    "session_id": other,
                    "question_id": "E-1",
                    "answer": "x",
                    "request_id": str(uuid4()),
                },
            ).status_code
            == 404
        )
        assert client.delete("/api/history", headers=headers).status_code == 200
        with connect(cfg.database_url) as conn:
            assert conn.execute("SELECT id FROM test_sessions WHERE id=%s", (other,)).fetchone()
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("DELETE FROM test_sessions WHERE id=%s", (other,))


def test_published_requires_review_and_production_hides_dev():
    cfg = Settings.load()
    with pytest.raises(CheckViolation), connect(cfg.database_url) as conn:
        conn.execute("UPDATE test_definitions SET status='published' WHERE id='firearms-sk-2026'")
    with TestClient(module.create_app(replace(cfg, environment="production"))) as client:
        assert client.get("/api/tests").json() == []
        assert client.get("/api/questions/E-1").status_code == 404


def test_multiple_certifications_do_not_share_question_selection(signed):
    cfg, client, headers, _ = signed
    tid, qid = "unit-test-" + str(uuid4()), "unit-question-" + str(uuid4())
    with connect(cfg.database_url) as conn:
        conn.execute(
            "INSERT INTO test_definitions(id,name,version,status,categories,exam_categories) VALUES(%s,'Synthetic second certification','1','development','[\"X\"]','[\"X\"]')",
            (tid,),
        )
        conn.execute(
            "INSERT INTO questions(id,test_id,category,number,title,body,structure,answer) VALUES(%s,%s,'X',1,'Synthetic','Synthetic question','direct','Synthetic answer')",
            (qid, tid),
        )
    try:
        assert len(client.get("/api/tests").json()) == 2
        result = client.post(
            "/api/sessions", headers=headers, json={"test_id": tid, "mode": "exam"}
        )
        assert result.json()["question_ids"] == [qid]
        assert (
            client.post(
                "/api/sessions", headers=headers, json={"test_id": tid, "question_id": "E-1"}
            ).status_code
            == 404
        )
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("DELETE FROM test_sessions WHERE test_id=%s", (tid,))
            conn.execute("DELETE FROM questions WHERE test_id=%s", (tid,))
            conn.execute("DELETE FROM test_definitions WHERE id=%s", (tid,))


def test_auth_exchange_is_browser_bound_and_single_use(monkeypatch):
    cfg = Settings.load()
    monkeypatch.setattr(
        module.Identity,
        "authenticate_user_device_auth_token",
        lambda self, **kw: SimpleNamespace(user_id="auth-unit", is_enabled=True),
    )
    with TestClient(module.create_app(cfg)) as browser, TestClient(module.create_app(cfg)) as other:
        start = browser.get("/api/auth/start", follow_redirects=False)
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        body = {
            "state": state,
            "user_id": "auth-unit",
            "device_id": "synthetic",
            "device_token": "synthetic",
        }
        assert browser.post("/api/auth/authorize", json=body).status_code == 403
        auth = browser.post("/api/auth/authorize", headers={"origin": cfg.auth_origin}, json=body)
        callback = urlsplit(auth.json()["redirect"])
        callback = callback.path + "?" + callback.query
        assert other.get(callback).status_code == 400
        assert browser.get(callback, follow_redirects=False).status_code == 303
        assert browser.get(callback).status_code == 400
        assert (
            browser.post(
                "/api/auth/authorize", headers={"origin": cfg.auth_origin}, json=body
            ).status_code
            == 400
        )
    with connect(cfg.database_url) as conn:
        conn.execute("DELETE FROM web_sessions WHERE user_id='auth-unit'")


def test_deployment_gate_rejects_latest_failure_pending_and_missing():
    path = Path(__file__).resolve().parents[1] / "deploy/verify_checks.py"
    spec = importlib.util.spec_from_file_location("gate", path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    good = {
        "name": "build",
        "id": 1,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://example.invalid/run",
    }
    assert gate.check_runs([good], ["build"]) == [good["html_url"]]
    for conclusion in ["failure", "cancelled", "skipped", None]:
        with pytest.raises(ValueError):
            gate.check_runs([good, {**good, "id": 2, "conclusion": conclusion}], ["build"])
    with pytest.raises(ValueError):
        gate.check_runs([good], ["missing"])
    with pytest.raises(ValueError):
        gate.check_runs([good], [])
