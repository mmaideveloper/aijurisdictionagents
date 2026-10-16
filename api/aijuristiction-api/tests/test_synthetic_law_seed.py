"""Seed SQL must produce provision identities accepted by the real citation code."""
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
import re
import sqlite3

from app.chat.provision_citations import provision_evidence
from app.mcp_law_retrieval import parse_provision_anchor


def test_seed_anchor_is_citable_and_repairs_existing_test_records(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    from scripts import prepare_issue_635_langgraph_e2e as seed

    # Exercise the actual provision INSERT/upsert; other tables are outside this
    # contract. Adapt PostgreSQL placeholders/adjacent literals for offline SQLite.
    database = sqlite3.connect(":memory:")
    database.execute("CREATE TABLE law_provisions (provision_id TEXT PRIMARY KEY, "
                     "version_id TEXT, anchor TEXT, heading TEXT, body_text TEXT, "
                     "ordinal INTEGER, created_at TEXT)")

    class Cursor:
        def execute(self, statement, parameters):
            if "INSERT INTO law_provisions" in statement:
                statement = re.sub(r"'\s+'", "", statement.replace("%s", "?"))
                database.execute(statement, tuple(value.isoformat() if isinstance(value, datetime)
                                                   else value for value in parameters))

    class Connection:
        def cursor(self):
            return nullcontext(Cursor())

        def commit(self):
            database.commit()

    monkeypatch.setenv("LAWS_DB_BACKEND", "postgres")
    monkeypatch.setenv("LAWS_DB_CLOUD", "postgresql://localhost/synthetic_e2e")
    monkeypatch.setattr(seed.psycopg, "connect", lambda _target: nullcontext(Connection()))
    try:
        seed._seed_synthetic_law()
        for legacy_anchor in (None, "§ 569"):
            if legacy_anchor is not None:
                database.execute("UPDATE law_provisions SET anchor = ?", (legacy_anchor,))
                seed._seed_synthetic_law()
            row = database.execute("SELECT anchor, heading, body_text FROM law_provisions").fetchone()
            parsed = parse_provision_anchor(row[0])
            assert parsed is not None and parsed.section_number == 569
            evidence = provision_evidence([{
                "document_id": seed.SYNTHETIC_LAW_ID, "law_number": 40, "law_year": 1964,
                "version_id": "issue-635-civil-code-v1",
                "provisions": [{"anchor": row[0], "heading": row[1], "body_text": row[2]}],
            }])
            assert len(evidence) == 1
            assert evidence[0]["source_id"] == seed.SYNTHETIC_LAW_ID
            assert evidence[0]["section"] == "§ 569"
    finally:
        database.close()
