from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import sqlite3
from typing import Any

from aijurisdictionagents.db_migrations import apply_sql_migrations

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


@dataclass(frozen=True)
class EmailQueueConfig:
    db_option: str
    db_local: Path
    db_cloud: str

    @classmethod
    def from_env(cls) -> "EmailQueueConfig":
        raw_option = os.getenv("EMAIL_DB_OPTION", os.getenv("DB_OPTION", "local")).strip().lower()
        db_option = "postgres" if raw_option == "postgress" else raw_option
        local_value = os.getenv("EMAIL_DB_LOCAL", "./databases/email.sqlite3").strip()
        local_path = _resolve_repo_path(local_value)
        db_cloud = os.getenv("EMAIL_DB_CLOUD", os.getenv("DB_CLOUD", "")).strip()
        return cls(db_option=db_option, db_local=local_path, db_cloud=db_cloud)


@dataclass(frozen=True)
class QueuedEmail:
    email_id: str
    recipient: str
    subject: str
    body: str
    attempts: int


class EmailQueueStore:
    def __init__(self, config: EmailQueueConfig) -> None:
        self.config = config
        self.config.db_local.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "EmailQueueStore":
        return cls(EmailQueueConfig.from_env())

    def initialize(self) -> None:
        if self.config.db_option == "local":
            with self._connect_sqlite() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS email_outbox (
                        email_id TEXT PRIMARY KEY,
                        recipient TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        body TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            return

        if self.config.db_option not in {"postgres", "azure"}:
            raise ValueError("EMAIL_DB_OPTION must be one of: local, postgres, azure")
        if not self.config.db_cloud:
            raise ValueError("EMAIL_DB_CLOUD must be set when EMAIL_DB_OPTION=postgres|azure")
        apply_sql_migrations(
            project="email",
            db_option=self.config.db_option,
            target=self.config.db_cloud,
            dry_run=False,
        )

    def enqueue_email(self, *, email_id: str, recipient: str, subject: str, body: str, metadata: dict[str, Any]) -> None:
        now = _now_iso()
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        if self.config.db_option == "local":
            with self._connect_sqlite() as conn:
                conn.execute(
                    """
                    INSERT INTO email_outbox(email_id, recipient, subject, body, metadata_json, status, attempts, last_error, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, 'pending', 0, NULL, ?, ?)
                    """,
                    (email_id, recipient, subject, body, metadata_json, now, now),
                )
                conn.commit()
            return

        with self._connect_postgres() as conn:
            conn.execute(
                """
                INSERT INTO email_outbox(email_id, recipient, subject, body, metadata_json, status, attempts, last_error, created_at, updated_at)
                VALUES(%s, %s, %s, %s, %s, 'pending', 0, NULL, %s, %s)
                """,
                (email_id, recipient, subject, body, metadata_json, now, now),
            )
            conn.commit()

    def fetch_pending(self, *, limit: int = 50) -> list[QueuedEmail]:
        if self.config.db_option == "local":
            with self._connect_sqlite() as conn:
                rows = conn.execute(
                    """
                    SELECT email_id, recipient, subject, body, attempts
                    FROM email_outbox
                    WHERE status = 'pending' AND attempts < 2
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [QueuedEmail(*row) for row in rows]

        with self._connect_postgres() as conn:
            rows = conn.execute(
                """
                SELECT email_id, recipient, subject, body, attempts
                FROM email_outbox
                WHERE status = 'pending' AND attempts < 2
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [QueuedEmail(*row) for row in rows]

    def mark_sent(self, *, email_id: str) -> None:
        now = _now_iso()
        if self.config.db_option == "local":
            with self._connect_sqlite() as conn:
                conn.execute(
                    "UPDATE email_outbox SET status='sent', updated_at=?, last_error=NULL WHERE email_id=?",
                    (now, email_id),
                )
                conn.commit()
            return

        with self._connect_postgres() as conn:
            conn.execute(
                "UPDATE email_outbox SET status='sent', updated_at=%s, last_error=NULL WHERE email_id=%s",
                (now, email_id),
            )
            conn.commit()

    def mark_failed_attempt(self, *, email_id: str, error_message: str) -> None:
        now = _now_iso()
        if self.config.db_option == "local":
            with self._connect_sqlite() as conn:
                conn.execute(
                    """
                    UPDATE email_outbox
                    SET attempts = attempts + 1,
                        status = CASE WHEN attempts + 1 >= 2 THEN 'failed' ELSE 'pending' END,
                        last_error = ?,
                        updated_at = ?
                    WHERE email_id = ?
                    """,
                    (error_message, now, email_id),
                )
                conn.commit()
            return

        with self._connect_postgres() as conn:
            conn.execute(
                """
                UPDATE email_outbox
                SET attempts = attempts + 1,
                    status = CASE WHEN attempts + 1 >= 2 THEN 'failed' ELSE 'pending' END,
                    last_error = %s,
                    updated_at = %s
                WHERE email_id = %s
                """,
                (error_message, now, email_id),
            )
            conn.commit()

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.config.db_local)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _connect_postgres(self) -> Any:
        if psycopg is None:  # pragma: no cover
            raise RuntimeError("psycopg is required for postgres/azure email queue")
        return psycopg.connect(self.config.db_cloud)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / candidate
