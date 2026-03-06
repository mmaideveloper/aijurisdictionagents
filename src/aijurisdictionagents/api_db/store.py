from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import uuid

from .config import ApiDataConfig


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
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
        storage_option: str = "local",
        store_cloud: str = "",
    ) -> None:
        self.db_path = db_path
        self.blob_root = blob_root
        self.storage_option = storage_option
        self.store_cloud = store_cloud
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "ApiDatabaseStore":
        config = ApiDataConfig.from_env()
        config.validate()
        return cls(
            db_path=config.db_path,
            blob_root=config.blob_root,
            storage_option=config.storage_option,
            store_cloud=config.store_cloud,
        )

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
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
                """
            )

    def create_user(self, *, email: str, full_name: str, password: str) -> User:
        user_id = str(uuid.uuid4())
        now = _now_iso()
        password_hash = _hash_password(password)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(user_id, email, full_name, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, email.lower(), full_name, password_hash, now),
            )
        return User(user_id=user_id, email=email.lower(), full_name=full_name)

    def authenticate_user(self, *, email: str, password: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, email, full_name, password_hash FROM users WHERE email = ?",
                (email.lower(),),
            ).fetchone()

        if row is None:
            return None
        if not _verify_password(password, row[3]):
            return None
        return User(user_id=row[0], email=row[1], full_name=row[2])

    def create_company(self, *, legal_name: str, profile_json: str = "{}") -> Company:
        company_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO companies(company_id, legal_name, profile_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (company_id, legal_name, profile_json, _now_iso()),
            )
        return Company(company_id=company_id, legal_name=legal_name)

    def add_user_to_company(self, *, user_id: str, company_id: str, role: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO company_users(company_id, user_id, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (company_id, user_id, role, _now_iso()),
            )

    def create_case(self, *, user_id: str, company_id: str | None, title: str) -> Case:
        case_id = str(uuid.uuid4())
        now = _now_iso()
        self._ensure_case_root(case_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cases(case_id, user_id, company_id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?)
                """,
                (case_id, user_id, company_id, title, now, now),
            )
        return Case(case_id=case_id, user_id=user_id, company_id=company_id, title=title)

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
            conn.execute(
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
            conn.execute(
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
            relative_uri = Path(case_id) / "communications" / f"{communication_id}.{extension}"
            transcript_uri = self._store_payload(relative_uri=relative_uri, payload=transcript_payload)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO case_communications(
                    communication_id, case_id, channel, transcript_uri, summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (communication_id, case_id, channel, transcript_uri, summary, _now_iso()),
            )
            conn.execute(
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

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
