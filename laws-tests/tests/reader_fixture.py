"""Isolated real PostgreSQL fixtures for the public reader; no model or route mocks."""

from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import hashlib
import json
import sys

from dotenv import set_key
from psycopg import ClientCursor
from psycopg.types.json import Jsonb

from laws_tests.config import Settings
from laws_tests.db import connect

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "runs/issue840/reader-fixture.json"


def prepare():
    cfg = Settings.load()
    assert cfg.environment in {"development", "test"}
    uri = urlsplit(cfg.database_url)
    assert uri.hostname in {"127.0.0.1", "localhost"}
    url = uri._replace(path="/laws_tests_sources_840").geturl()
    with connect(uri._replace(path="/postgres").geturl()) as conn:
        conn.autocommit = True
        if not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname='laws_tests_sources_840'"
        ).fetchone():
            conn.execute(
                "CREATE DATABASE \"laws_tests_sources_840\" TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'"
            )
    with connect(url) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS reader_fixture_migrations(name text PRIMARY KEY, checksum text NOT NULL)"
        )
        for path in sorted((ROOT / "databases/laws-collector/migrations").glob("*.sql")):
            source = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(source.encode()).hexdigest()
            previous = conn.execute(
                "SELECT checksum FROM reader_fixture_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if previous:
                assert previous["checksum"] == digest
            else:
                conn.execute(source)
                conn.execute(
                    "INSERT INTO reader_fixture_migrations VALUES(%s,%s)", (path.name, digest)
                )
    # The local DSN uses the approved local-only credential; never output it.
    set_key(ROOT / ".env-laws-test", "LAWS_TEST_LAWS_DATABASE_URL", url)
    if MANIFEST.exists():
        cleanup()
    run = "reader-840-" + uuid4().hex
    with connect(url) as conn:
        ClientCursor(conn).execute(
            (ROOT / "databases/laws-collector/seeds/issue840/reader.sql").read_text(
                encoding="utf-8"
            ),
            {"run": run},
        )
    annotations = [
        {
            "field": field,
            "quote": "§ 4 ods. 2 písm. j)",
            "law_number": 9998,
            "law_year": 2026,
            "section": "4",
            "paragraph": "2",
            "letter": "j",
        }
        for field in ("body", "answer")
    ]
    with connect(cfg.database_url) as conn:
        conn.execute(
            "INSERT INTO test_definitions(id,name,version,legal_date,status,categories,exam_categories) VALUES(%s,'Syntetická skúška odkazov','fixture','2026-06-01','development','[\"A\"]','[\"A\"]')",
            (run,),
        )
        conn.execute(
            "INSERT INTO questions(id,test_id,category,number,title,body,structure,answer,legal_references) VALUES(%s,%s,'A',1,'Overenie odkazu na zákon',%s,'direct',%s,%s)",
            (
                run,
                run,
                "Čo stanovuje § 4 ods. 2 písm. j) predpisu č. 9998/2026 Z. z.?",
                "Podľa § 4 ods. 2 písm. j) sa overuje totožnosť a doklady. Syntetická odpoveď.",
                Jsonb(annotations),
            ),
        )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"run_id": run, "source_id": run, "version_id": run + "-20260101"}),
        encoding="utf-8",
    )
    print("Synthetic reader fixtures prepared; values redacted.")


def cleanup():
    if not MANIFEST.exists():
        return
    cfg = Settings.load()
    assert cfg.environment != "production"
    run = json.loads(MANIFEST.read_text())["run_id"]
    assert run.startswith("reader-840-")
    with connect(cfg.database_url) as conn:
        conn.execute("DELETE FROM questions WHERE test_id=%s", (run,))
        conn.execute("DELETE FROM test_definitions WHERE id=%s", (run,))
    with connect(cfg.laws_database_url) as conn:
        conn.execute("DELETE FROM law_documents WHERE document_id=%s", (run,))
    MANIFEST.unlink()
    print("Synthetic reader fixtures removed.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        cleanup()
    else:
        prepare()
