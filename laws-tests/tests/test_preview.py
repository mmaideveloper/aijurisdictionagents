from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.errors import CheckViolation

from laws_tests.app import create_app
from laws_tests.config import Settings
from laws_tests.db import connect, migrate


def test_preview_seed_on_empty_database():
    cfg = Settings.load()
    settings = conninfo_to_dict(cfg.database_url)
    assert cfg.environment != "production" and settings["host"] in ("127.0.0.1", "localhost")
    name = "preview_seed_" + uuid4().hex
    admin = make_conninfo(cfg.database_url, dbname="postgres")
    target = make_conninfo(cfg.database_url, dbname=name)
    root = Path(__file__).resolve().parents[2]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            psycopg.sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                psycopg.sql.Identifier(name)
            )
        )
    try:
        migrate(target, root)
        with connect(target) as conn:
            seed = (root / "databases/laws-tests/seeds/preview.sql").read_text(encoding="utf-8")
            conn.execute(seed)
            conn.execute(seed)
            row = conn.execute(
                "SELECT status,preview_notice,legal_date FROM test_definitions"
            ).fetchone()
            assert (
                row["status"] == "preview" and row["preview_notice"] and row["legal_date"] is None
            )
            assert conn.execute("SELECT count(*) AS n FROM questions").fetchone()["n"] == 5
            assert conn.execute("SELECT count(*) AS n FROM subquestions").fetchone()["n"] == 9
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(psycopg.sql.SQL("DROP DATABASE {}").format(psycopg.sql.Identifier(name)))


def test_preview_is_public_but_is_not_a_reviewed_publication():
    cfg = Settings.load()
    assert cfg.environment != "production"
    migrate(cfg.database_url, Path(__file__).resolve().parents[2])
    course = "preview-unit-" + uuid4().hex
    try:
        with pytest.raises(CheckViolation), connect(cfg.database_url) as conn:
            conn.execute(
                "INSERT INTO test_definitions(id,name,version,status,categories) VALUES(%s,'Preview','unit','preview','[\"A\"]')",
                (course,),
            )
        with connect(cfg.database_url) as conn:
            conn.execute(
                "INSERT INTO test_definitions(id,name,version,status,preview_notice,categories) VALUES(%s,'Preview','unit','preview','Incomplete, not legally reviewed','[\"A\"]')",
                (course,),
            )
        with TestClient(create_app(replace(cfg, environment="production"))) as client:
            rows = client.get("/api/tests").json()
            row = next(row for row in rows if row["id"] == course)
            assert row["status"] == "preview" and row["legal_date"] is None
            assert row["preview_notice"] == "Incomplete, not legally reviewed"
            assert not any(row["status"] == "development" for row in rows)
            assert client.get(f"/api/tests/{course}/questions").status_code == 200
        with pytest.raises(CheckViolation), connect(cfg.database_url) as conn:
            conn.execute("UPDATE test_definitions SET status='published' WHERE id=%s", (course,))
    finally:
        with connect(cfg.database_url) as conn:
            conn.execute("DELETE FROM test_definitions WHERE id=%s", (course,))
