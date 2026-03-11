from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
from typing import Any
import uuid

try:
    import psycopg
    from psycopg import Connection as PostgresConnection
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None
    PostgresConnection = Any  # type: ignore[assignment]

from .config import ApiDataConfig


@dataclass(frozen=True)
class User:
    user_id: str
    phone_number: str | None
    email: str
    first_name: str | None
    last_name: str | None
    full_name: str


@dataclass(frozen=True)
class Company:
    company_id: str
    legal_name: str


@dataclass(frozen=True)
class Case:
    case_id: str
    user_id: str
    company_id: str | None
    title: str


class ApiDatabaseStore:
    """Local-first API metadata store using SQLite + external blob storage references.

    Storage backend supports local path writes and Azure URI prefixes while keeping
    a case-scoped folder layout (`<case_id>/...`) for every stored artifact.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        blob_root: Path,
        db_option: str = "local",
        db_cloud: str = "",
        storage_option: str = "local",
        store_cloud: str = "",
    ) -> None:
        self.db_path = db_path
        self.blob_root = blob_root
        self.db_option = db_option
        self.db_cloud = db_cloud
        self.storage_option = storage_option
        self.store_cloud = store_cloud
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_root.mkdir(parents=True, exist_ok=True)

    @property
    def uses_postgres(self) -> bool:
        return self.db_option in {"postgres", "azure"}

    @classmethod
    def from_env(cls) -> "ApiDatabaseStore":
        config = ApiDataConfig.from_env()
        config.validate()
        return cls(
            db_path=config.db_path,
            blob_root=config.blob_root,
            db_option=config.db_option,
            db_cloud=config.db_connection_uri,
            storage_option=config.storage_option,
            store_cloud=config.store_cloud,
        )

    def initialize(self) -> None:
        with self._connect() as conn:
            self._execute_script(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    phone_number TEXT UNIQUE,
                    email TEXT UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS companies (
                    company_id TEXT PRIMARY KEY,
                    legal_name TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS company_users (
                    company_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(company_id, user_id),
                    FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    company_id TEXT,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(company_id) REFERENCES companies(company_id)
                );

                CREATE TABLE IF NOT EXISTS case_documents (
                    doc_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    storage_uri TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    uploaded_by_user_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
                    FOREIGN KEY(uploaded_by_user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS case_communications (
                    communication_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    transcript_uri TEXT,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );
                """,
            )
            self._ensure_user_schema(conn)

    def create_user(
        self,
        *,
        email: str,
        password: str,
        phone_number: str | None = None,
        full_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user_id = str(uuid.uuid4())
        now = _now_iso()
        password_hash = _hash_password(password)
        normalized_email = email.strip().lower()
        normalized_phone = _normalize_phone(phone_number)
        normalized_first = _normalize_optional_text(first_name)
        normalized_last = _normalize_optional_text(last_name)
        resolved_full_name = _resolve_full_name(
            full_name=full_name,
            first_name=normalized_first,
            last_name=normalized_last,
            phone_number=normalized_phone,
            email=normalized_email,
        )
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO users(
                    user_id, phone_number, email, first_name, last_name, full_name, password_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    normalized_phone,
                    normalized_email,
                    normalized_first,
                    normalized_last,
                    resolved_full_name,
                    password_hash,
                    now,
                ),
            )
        return User(
            user_id=user_id,
            phone_number=normalized_phone,
            email=normalized_email,
            first_name=normalized_first,
            last_name=normalized_last,
            full_name=resolved_full_name,
        )

    def authenticate_user(self, *, email: str, password: str) -> User | None:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT user_id, phone_number, email, first_name, last_name, full_name, password_hash
                FROM users
                WHERE email = ?
                """,
                (email.strip().lower(),),
            )
        if row is None:
            return None
        if not _verify_password(password, row[6]):
            return None
        return _row_to_user(row)

    def find_user_by_phone(self, *, phone_number: str) -> User | None:
        normalized_phone = _normalize_phone(phone_number)
        if normalized_phone is None:
            return None
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT user_id, phone_number, email, first_name, last_name, full_name
                FROM users
                WHERE phone_number = ?
                """,
                (normalized_phone,),
            )
        if row is None:
            return None
        return _row_to_user(row)

    def update_user(
        self,
        *,
        user_id: str,
        phone_number: str | None,
        first_name: str | None,
        last_name: str | None,
        password: str | None = None,
    ) -> User:
        normalized_phone = _normalize_phone(phone_number)
        normalized_first = _normalize_optional_text(first_name)
        normalized_last = _normalize_optional_text(last_name)
        normalized_password = _normalize_optional_text(password)
        with self._connect() as conn:
            current = self._fetchone(
                conn,
                """
                SELECT user_id, phone_number, email, first_name, last_name, full_name
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            )
            if current is None:
                raise KeyError(f"User {user_id} not found")
            current_user = _row_to_user(current)
            resolved_full_name = _resolve_full_name(
                full_name=current_user.full_name,
                first_name=normalized_first,
                last_name=normalized_last,
                phone_number=normalized_phone,
                email=current_user.email,
            )
            if normalized_password:
                self._execute(
                    conn,
                    """
                    UPDATE users
                    SET phone_number = ?, first_name = ?, last_name = ?, full_name = ?, password_hash = ?
                    WHERE user_id = ?
                    """,
                    (
                        normalized_phone,
                        normalized_first,
                        normalized_last,
                        resolved_full_name,
                        _hash_password(normalized_password),
                        user_id,
                    ),
                )
            else:
                self._execute(
                    conn,
                    """
                    UPDATE users
                    SET phone_number = ?, first_name = ?, last_name = ?, full_name = ?
                    WHERE user_id = ?
                    """,
                    (
                        normalized_phone,
                        normalized_first,
                        normalized_last,
                        resolved_full_name,
                        user_id,
                    ),
                )
        return User(
            user_id=user_id,
            phone_number=normalized_phone,
            email=current_user.email,
            first_name=normalized_first,
            last_name=normalized_last,
            full_name=resolved_full_name,
        )

    def create_company(self, *, legal_name: str, profile_json: str = "{}") -> Company:
        company_id = str(uuid.uuid4())
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO companies(company_id, legal_name, profile_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (company_id, legal_name, profile_json, _now_iso()),
            )
        return Company(company_id=company_id, legal_name=legal_name)

    def add_user_to_company(self, *, user_id: str, company_id: str, role: str) -> None:
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO company_users(company_id, user_id, role, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(company_id, user_id)
                DO UPDATE SET role = excluded.role, created_at = excluded.created_at
                """,
                (company_id, user_id, role, _now_iso()),
            )

    def create_case(self, *, user_id: str, company_id: str | None, title: str) -> Case:
        case_id = str(uuid.uuid4())
        now = _now_iso()
        self._ensure_case_root(case_id)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO cases(case_id, user_id, company_id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?)
                """,
                (case_id, user_id, company_id, title, now, now),
            )
        return Case(
            case_id=case_id, user_id=user_id, company_id=company_id, title=title
        )

    def add_case_document(
        self,
        *,
        case_id: str,
        kind: str,
        version: int,
        original_filename: str,
        payload: bytes,
        uploaded_by_user_id: str | None = None,
    ) -> str:
        doc_id = str(uuid.uuid4())
        relative_uri = Path(case_id) / kind / f"v{version}_{original_filename}"
        storage_uri = self._store_payload(relative_uri=relative_uri, payload=payload)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO case_documents(
                    doc_id, case_id, kind, version, storage_uri, original_filename, uploaded_by_user_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    case_id,
                    kind,
                    version,
                    storage_uri,
                    original_filename,
                    uploaded_by_user_id,
                    _now_iso(),
                ),
            )
            self._execute(
                conn,
                "UPDATE cases SET updated_at = ? WHERE case_id = ?",
                (_now_iso(), case_id),
            )
        return doc_id

    def add_case_communication(
        self,
        *,
        case_id: str,
        channel: str,
        summary: str,
        transcript_payload: bytes | None = None,
        extension: str = "txt",
    ) -> str:
        communication_id = str(uuid.uuid4())
        transcript_uri: str | None = None
        if transcript_payload is not None:
            relative_uri = (
                Path(case_id) / "communications" / f"{communication_id}.{extension}"
            )
            transcript_uri = self._store_payload(
                relative_uri=relative_uri, payload=transcript_payload
            )
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO case_communications(
                    communication_id, case_id, channel, transcript_uri, summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    communication_id,
                    case_id,
                    channel,
                    transcript_uri,
                    summary,
                    _now_iso(),
                ),
            )
            self._execute(
                conn,
                "UPDATE cases SET updated_at = ? WHERE case_id = ?",
                (_now_iso(), case_id),
            )
        return communication_id

    def _ensure_case_root(self, case_id: str) -> None:
        (self.blob_root / case_id).mkdir(parents=True, exist_ok=True)

    def _store_payload(self, *, relative_uri: Path, payload: bytes) -> str:
        case_id = relative_uri.parts[0]
        self._ensure_case_root(case_id)
        local_destination = self.blob_root / relative_uri
        local_destination.parent.mkdir(parents=True, exist_ok=True)
        local_destination.write_bytes(payload)
        if self.storage_option == "azure":
            if not self.store_cloud:
                raise ValueError("STORE_CLOUD is required when storage_option=azure")
            prefix = self.store_cloud.rstrip("/")
            return f"{prefix}/{relative_uri.as_posix()}"
        return relative_uri.as_posix()

    def _connect(self) -> sqlite3.Connection | PostgresConnection[Any]:
        if self.uses_postgres:
            if psycopg is None:
                raise RuntimeError("psycopg is required for DB_OPTION=postgres|azure")
            return psycopg.connect(self.db_cloud)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _execute_script(
        self, conn: sqlite3.Connection | PostgresConnection[Any], script: str
    ) -> None:
        statements = [stmt.strip() for stmt in script.split(";") if stmt.strip()]
        for statement in statements:
            self._execute(conn, statement)

    def _execute(
        self,
        conn: sqlite3.Connection | PostgresConnection[Any],
        query: str,
        params: tuple[Any, ...] = (),
    ) -> Any:
        return conn.execute(self._query(query), params)

    def _fetchone(
        self,
        conn: sqlite3.Connection | PostgresConnection[Any],
        query: str,
        params: tuple[Any, ...],
    ) -> tuple[Any, ...] | None:
        return self._execute(conn, query, params).fetchone()

    def _query(self, query: str) -> str:
        if self.uses_postgres:
            return query.replace("?", "%s")
        return query

    def _ensure_user_schema(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            columns = {
                row[0]
                for row in self._execute(
                    conn,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'users'
                    """,
                ).fetchall()
            }
        else:
            columns = {
                row[1]
                for row in self._execute(conn, "PRAGMA table_info(users)").fetchall()
            }

        if "phone_number" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN phone_number TEXT")
        if "first_name" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN first_name TEXT")
        if "last_name" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN last_name TEXT")
        self._execute(
            conn,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_number
            ON users(phone_number)
            WHERE phone_number IS NOT NULL
            """,
        )
        self._execute(
            conn,
            """
            UPDATE users
            SET full_name = COALESCE(NULLIF(TRIM(full_name), ''), email)
            WHERE full_name IS NULL OR TRIM(full_name) = ''
            """,
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_phone(phone_number: str | None) -> str | None:
    if phone_number is None:
        return None
    normalized = "".join(phone_number.strip().split())
    return normalized or None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_full_name(
    *,
    full_name: str | None,
    first_name: str | None,
    last_name: str | None,
    phone_number: str | None,
    email: str,
) -> str:
    joined = " ".join(part for part in (first_name, last_name) if part)
    if joined:
        return joined
    normalized_full_name = _normalize_optional_text(full_name)
    if normalized_full_name:
        return normalized_full_name
    if phone_number:
        return phone_number
    return email


def _row_to_user(row: tuple[object, ...]) -> User:
    values = list(row)
    return User(
        user_id=str(values[0]),
        phone_number=str(values[1]) if values[1] is not None else None,
        email=str(values[2]),
        first_name=str(values[3]) if values[3] is not None else None,
        last_name=str(values[4]) if values[4] is not None else None,
        full_name=str(values[5]),
    )


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}:{digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    salt_hex, digest_hex = encoded.split(":", maxsplit=1)
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return hmac.compare_digest(candidate, expected)
