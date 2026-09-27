"""Database-backed checks; mocks are limited to early model/identity unit boundaries."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation, RaiseException

from laws_tests.app import create_app, digest
from laws_tests.config import Settings
from laws_tests.db import connect, migrate
from laws_tests.evaluation import Evaluation

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def cfg():
    value = Settings.load()
    assert value.environment != "production"
    return value


def test_public_content_and_auth_boundary(cfg):
    with TestClient(create_app(cfg)) as client:
        response = client.get("/api/questions/A-20")
        assert response.status_code == 200
        assert len(response.json()["subquestions"]) == 3
        assert response.json()["answer"] is None
        assert "rules" not in response.json()
        assert client.get("/api/questions/E-1").json()["subquestions"] == []
        assert client.get("/api/history").status_code == 401
        assert client.post("/api/sessions", json={"test_id": "firearms-sk-2026"}).status_code == 401
        assert (
            client.get(
                "/api/auth/start?return_path=//evil.invalid", follow_redirects=False
            ).status_code
            == 400
        )


def test_schema_enforces_mutually_exclusive_answers(cfg):
    with pytest.raises(CheckViolation), connect(cfg.database_url) as conn:
        conn.execute("UPDATE questions SET answer='invalid parent answer' WHERE id='A-20'")
    with pytest.raises(CheckViolation), connect(cfg.database_url) as conn:
        conn.execute("UPDATE questions SET answer=NULL WHERE id='E-1'")
    with pytest.raises(RaiseException), connect(cfg.database_url) as conn:
        conn.execute("DELETE FROM subquestions WHERE question_id='A-20'")
    with pytest.raises(RaiseException), connect(cfg.database_url) as conn:
        conn.execute(
            "INSERT INTO subquestions(id,question_id,sequence,body,answer) VALUES('invalid-E','E-1',1,'x','y')"
        )


def test_migration_rerun(cfg):
    migrate(cfg.database_url, ROOT)
    migrate(cfg.database_url, ROOT)


def test_score_validation():
    with pytest.raises(ValueError):
        Evaluation.model_validate(
            {
                "score": 101,
                "matchedPoints": [],
                "missingPoints": [],
                "incorrectClaims": [],
                "feedback": "x",
            }
        )
    with pytest.raises(ValueError):
        Evaluation.model_validate(
            {
                "score": True,
                "matchedPoints": [],
                "missingPoints": [],
                "incorrectClaims": [],
                "feedback": "x",
            }
        )


def test_expiry_csrf_isolation_and_retention(cfg, monkeypatch):
    # Real PostgreSQL; stub identity only for narrowly scoped unit authorization checks.
    import laws_tests.app as module
    from types import SimpleNamespace

    monkeypatch.setattr(
        module.Identity,
        "find_user_by_id",
        lambda self, **kwargs: SimpleNamespace(is_enabled=True),
    )
    token, csrf, uid = str(uuid4()), str(uuid4()), "unit-" + str(uuid4())
    with connect(cfg.database_url) as conn:
        conn.execute(
            "INSERT INTO web_sessions VALUES(%s,%s,%s,now()+interval '1 hour')",
            (digest(token), uid, csrf),
        )
    try:
        with TestClient(create_app(cfg)) as client:
            client.cookies.set("laws_session", token)
            body = {"test_id": "firearms-sk-2026", "mode": "learning", "question_id": "E-1"}
            assert client.post("/api/sessions", json=body).status_code == 403
            headers = {"origin": cfg.public_url, "x-csrf-token": csrf}
            created = client.post("/api/sessions", json=body, headers=headers)
            assert created.status_code == 200
            sid = created.json()["id"]
            assert client.get("/api/sessions/" + str(uuid4()) + "/result").status_code == 404
            with connect(cfg.database_url) as conn:
                conn.execute(
                    "UPDATE test_definitions SET expires_at=now()-interval '1 second' WHERE id=%s",
                    (body["test_id"],),
                )
            assert client.post("/api/sessions", json=body, headers=headers).status_code == 409
            result = client.post(
                "/api/attempts",
                headers=headers,
                json={
                    "session_id": sid,
                    "question_id": "E-1",
                    "answer": "test",
                    "request_id": str(uuid4()),
                },
            )
            assert result.status_code == 409
            assert client.get("/api/questions/E-1").status_code == 200
            assert client.get("/api/history").status_code == 200
            assert client.delete("/api/history", headers=headers).status_code == 200
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("UPDATE test_definitions SET expires_at=NULL WHERE id='firearms-sk-2026'")
            conn.execute("DELETE FROM test_sessions WHERE user_id=%s", (uid,))
            conn.execute("DELETE FROM web_sessions WHERE user_id=%s", (uid,))
