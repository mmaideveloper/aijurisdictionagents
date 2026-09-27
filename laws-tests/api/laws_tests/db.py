import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def connect(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def migrate(url: str, root: Path) -> None:
    with connect(url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(840001)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS laws_test_migrations(name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz DEFAULT now())"
        )
        for path in sorted((root / "databases/laws-tests").glob("[0-9]*.sql")):
            source = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(source.encode()).hexdigest()
            previous = conn.execute(
                "SELECT checksum FROM laws_test_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if previous:
                if previous["checksum"] != checksum:
                    raise ValueError("Applied migration checksum mismatch")
                continue
            conn.execute(source)
            conn.execute(
                "INSERT INTO laws_test_migrations(name,checksum) VALUES(%s,%s)", (path.name, checksum)
            )


def purge(conn) -> None:
    conn.execute("DELETE FROM attempts WHERE created_at <= now() - interval '12 months'")
    conn.execute(
        "DELETE FROM test_sessions s WHERE s.created_at <= now() - interval '12 months' AND NOT EXISTS(SELECT 1 FROM attempts a WHERE a.session_id=s.id)"
    )
    conn.execute("DELETE FROM web_sessions WHERE expires_at<=now()")
    conn.execute("DELETE FROM login_requests WHERE expires_at<=now()")
