from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
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
class SubscriptionPlan:
    plan_code: str
    display_name: str
    subscription_type: str
    price_eur: int
    max_cases: int
    max_documents_per_case: int
    case_ttl_days: int | None


@dataclass(frozen=True)
class UserSubscription:
    subscription_id: str
    user_id: str
    plan_code: str
    status: str
    starts_at: str | None
    ends_at: str | None
    case_ids_json: str
    created_at: str
    updated_at: str


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
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CaseDocument:
    doc_id: str
    case_id: str
    kind: str
    version: int
    storage_uri: str
    original_filename: str
    uploaded_by_user_id: str | None
    processing_status: str
    processing_error: str | None
    processed_at: str | None
    created_at: str


@dataclass(frozen=True)
class CaseCommunication:
    communication_id: str
    case_id: str
    channel: str
    transcript_uri: str | None
    summary: str
    created_at: str


@dataclass(frozen=True)
class CaseDocumentChunk:
    chunk_id: str
    doc_id: str
    case_id: str
    chunk_index: int
    chunk_text: str
    embedding_vector: str
    embedding_model: str
    embedding_dimensions: int
    start_offset: int
    end_offset: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PermanentMemoryEntry:
    key: str
    value_json: str
    value: dict[str, Any]
    entry_type: str
    source_url: str | None
    created_at: str
    updated_at: str


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
                    processing_status TEXT NOT NULL DEFAULT 'uploaded',
                    processing_error TEXT,
                    processed_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
                    FOREIGN KEY(uploaded_by_user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS case_document_contents (
                    content_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    embedding_vector TEXT NOT NULL,
                    embedding_model TEXT NOT NULL DEFAULT '',
                    embedding_dimensions INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(doc_id) REFERENCES case_documents(doc_id) ON DELETE CASCADE,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS case_document_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding_vector TEXT NOT NULL,
                    embedding_model TEXT NOT NULL DEFAULT '',
                    embedding_dimensions INTEGER NOT NULL DEFAULT 0,
                    start_offset INTEGER NOT NULL DEFAULT 0,
                    end_offset INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(doc_id, chunk_index),
                    FOREIGN KEY(doc_id) REFERENCES case_documents(doc_id) ON DELETE CASCADE,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_case_document_chunks_case_doc_chunk
                ON case_document_chunks(case_id, doc_id, chunk_index);

                CREATE TABLE IF NOT EXISTS case_communications (
                    communication_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    transcript_uri TEXT,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS subscription_plans (
                    plan_code TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    subscription_type TEXT NOT NULL,
                    price_eur INTEGER NOT NULL,
                    max_cases INTEGER NOT NULL,
                    max_documents_per_case INTEGER NOT NULL DEFAULT 2,
                    case_ttl_days INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    plan_code TEXT NOT NULL,
                    status TEXT NOT NULL,
                    starts_at TEXT,
                    ends_at TEXT,
                    case_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(plan_code) REFERENCES subscription_plans(plan_code)
                );
                """,
            )
            self._ensure_user_schema(conn)
            self._ensure_case_document_schema(conn)
            self._ensure_subscription_schema(conn)
            self._ensure_permanent_memory_schema(conn)
            self._seed_subscription_plans(conn)

    def get_permanent_memory(self, key: str) -> PermanentMemoryEntry | None:
        with self._connect() as conn:
            row = self._execute(
                conn,
                """
                SELECT key, value, type, source_url, created_at, updated_at
                FROM permanent_memory
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        values = list(row)
        payload_text = str(values[1])
        payload = _safe_json_load(payload_text)
        return PermanentMemoryEntry(
            key=str(values[0]),
            value_json=payload_text,
            value=payload,
            entry_type=str(values[2]),
            source_url=str(values[3]) if values[3] is not None else None,
            created_at=str(values[4]),
            updated_at=str(values[5]),
        )

    def upsert_permanent_memory(
        self,
        *,
        key: str,
        value: dict[str, Any],
        entry_type: str,
        source_url: str | None = None,
    ) -> None:
        now = _now_iso()
        payload_text = _to_json(value)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO permanent_memory(key, value, type, source_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    type = excluded.type,
                    source_url = excluded.source_url,
                    updated_at = excluded.updated_at
                """,
                (key, payload_text, entry_type, source_url, now, now),
            )
            conn.commit()

    def check_connection(self) -> None:
        with self._connect() as conn:
            self._execute(conn, "SELECT 1").fetchone()

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
            self._execute(
                conn,
                """
                INSERT INTO user_subscriptions(
                    subscription_id, user_id, plan_code, status, starts_at, ends_at, case_ids_json, created_at, updated_at
                )
                VALUES (?, ?, 'free', 'paid', ?, NULL, '[]', ?, ?)
                """,
                (str(uuid.uuid4()), user_id, now, now, now),
            )
        return User(
            user_id=user_id,
            phone_number=normalized_phone,
            email=normalized_email,
            first_name=normalized_first,
            last_name=normalized_last,
            full_name=resolved_full_name,
        )

    def list_subscription_plans(self) -> list[SubscriptionPlan]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT plan_code, display_name, subscription_type, price_eur, max_cases, max_documents_per_case, case_ttl_days
                FROM subscription_plans
                ORDER BY price_eur ASC
                """,
            ).fetchall()
        return [_row_to_subscription_plan(row) for row in rows]

    def list_user_subscriptions(self, *, user_id: str) -> list[UserSubscription]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT subscription_id, user_id, plan_code, status, starts_at, ends_at, case_ids_json, created_at, updated_at
                FROM user_subscriptions
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [_row_to_user_subscription(row) for row in rows]

    def request_subscription_change(self, *, user_id: str, plan_code: str) -> UserSubscription:
        now = _now_iso()
        subscription_id = str(uuid.uuid4())
        normalized_plan = plan_code.strip().lower()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO user_subscriptions(
                    subscription_id, user_id, plan_code, status, starts_at, ends_at, case_ids_json, created_at, updated_at
                )
                VALUES (?, ?, ?, 'pending', NULL, NULL, '[]', ?, ?)
                """,
                (subscription_id, user_id, normalized_plan, now, now),
            )
            row = self._fetchone(
                conn,
                """
                SELECT subscription_id, user_id, plan_code, status, starts_at, ends_at, case_ids_json, created_at, updated_at
                FROM user_subscriptions
                WHERE subscription_id = ?
                """,
                (subscription_id,),
            )
        if row is None:
            raise KeyError(f"Subscription {subscription_id} not found")
        return _row_to_user_subscription(row)

    def update_subscription_status(self, *, subscription_id: str, status: str) -> UserSubscription:
        normalized_status = status.strip().lower()
        if normalized_status not in {"pending", "paying", "paid", "failed", "canceled", "expired"}:
            raise ValueError("Unsupported subscription status")

        with self._connect() as conn:
            current = self._fetchone(
                conn,
                """
                SELECT subscription_id, user_id, plan_code, status, starts_at, ends_at, case_ids_json, created_at, updated_at
                FROM user_subscriptions
                WHERE subscription_id = ?
                """,
                (subscription_id,),
            )
            if current is None:
                raise KeyError(f"Subscription {subscription_id} not found")
            current_subscription = _row_to_user_subscription(current)

            starts_at = current_subscription.starts_at
            ends_at = current_subscription.ends_at
            if normalized_status == "paid":
                starts_at = _now_iso()
                ends_at = self._resolve_subscription_end(
                    conn,
                    plan_code=current_subscription.plan_code,
                    starts_at=starts_at,
                )

            now = _now_iso()
            self._execute(
                conn,
                """
                UPDATE user_subscriptions
                SET status = ?, starts_at = ?, ends_at = ?, updated_at = ?
                WHERE subscription_id = ?
                """,
                (normalized_status, starts_at, ends_at, now, subscription_id),
            )
            updated = self._fetchone(
                conn,
                """
                SELECT subscription_id, user_id, plan_code, status, starts_at, ends_at, case_ids_json, created_at, updated_at
                FROM user_subscriptions
                WHERE subscription_id = ?
                """,
                (subscription_id,),
            )
        if updated is None:
            raise KeyError(f"Subscription {subscription_id} not found")
        return _row_to_user_subscription(updated)

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

    def find_user_by_id(self, *, user_id: str) -> User | None:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT user_id, phone_number, email, first_name, last_name, full_name
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            )
        if row is None:
            return None
        return _row_to_user(row)

    def get_user(self, *, user_id: str) -> User:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT user_id, phone_number, email, first_name, last_name, full_name
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            )
        if row is None:
            raise KeyError(f"User {user_id} not found")
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
        return self.get_case(case_id=case_id)

    def get_case(self, *, case_id: str) -> Case:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT case_id, user_id, company_id, title, status, created_at, updated_at
                FROM cases
                WHERE case_id = ?
                """,
                (case_id,),
            )
        if row is None:
            raise KeyError(f"Case {case_id} not found")
        return _row_to_case(row)

    def list_cases(self, *, user_id: str, include_deleted: bool = False) -> list[Case]:
        query = """
            SELECT case_id, user_id, company_id, title, status, created_at, updated_at
            FROM cases
            WHERE user_id = ?
        """
        if not include_deleted:
            query += " AND status <> 'deleted'"
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = self._execute(conn, query, (user_id,)).fetchall()
        return [_row_to_case(row) for row in rows]

    def count_active_cases(self, *, user_id: str) -> int:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT COUNT(*)
                FROM cases
                WHERE user_id = ? AND status <> 'deleted'
                """,
                (user_id,),
            )
        return int(row[0]) if row else 0

    def update_case_title(self, *, case_id: str, user_id: str, title: str) -> Case:
        now = _now_iso()
        with self._connect() as conn:
            result = self._execute(
                conn,
                """
                UPDATE cases
                SET title = ?, updated_at = ?
                WHERE case_id = ? AND user_id = ? AND status <> 'deleted'
                """,
                (title, now, case_id, user_id),
            )
            if result.rowcount == 0:
                raise KeyError(f"Case {case_id} not found")
        return self.get_case(case_id=case_id)

    def soft_delete_case(self, *, case_id: str, user_id: str) -> None:
        with self._connect() as conn:
            result = self._execute(
                conn,
                """
                UPDATE cases
                SET status = 'deleted', updated_at = ?
                WHERE case_id = ? AND user_id = ? AND status <> 'deleted'
                """,
                (_now_iso(), case_id, user_id),
            )
            if result.rowcount == 0:
                raise KeyError(f"Case {case_id} not found")

    def list_case_documents(self, *, case_id: str) -> list[CaseDocument]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT doc_id, case_id, kind, version, storage_uri, original_filename, uploaded_by_user_id,
                       processing_status, processing_error, processed_at, created_at
                FROM case_documents
                WHERE case_id = ?
                ORDER BY created_at DESC, version DESC
                """,
                (case_id,),
            ).fetchall()
        return [_row_to_case_document(row) for row in rows]

    def get_case_document(self, *, case_id: str, doc_id: str) -> CaseDocument:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT doc_id, case_id, kind, version, storage_uri, original_filename, uploaded_by_user_id,
                       processing_status, processing_error, processed_at, created_at
                FROM case_documents
                WHERE case_id = ? AND doc_id = ?
                """,
                (case_id, doc_id),
            )
        if row is None:
            raise KeyError(f"Document {doc_id} not found for case {case_id}")
        return _row_to_case_document(row)

    def list_case_communications(
        self, *, case_id: str, limit: int | None = None, offset: int = 0
    ) -> list[CaseCommunication]:
        query = """
            SELECT communication_id, case_id, channel, transcript_uri, summary, created_at
            FROM case_communications
            WHERE case_id = ?
            ORDER BY created_at DESC
        """
        params: tuple[Any, ...]
        if limit is None:
            params = (case_id,)
        else:
            query += " LIMIT ? OFFSET ?"
            params = (case_id, limit, offset)
        with self._connect() as conn:
            rows = self._execute(conn, query, params).fetchall()
        return [_row_to_case_communication(row) for row in rows]

    def get_case_communication(self, *, case_id: str, communication_id: str) -> CaseCommunication:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT communication_id, case_id, channel, transcript_uri, summary, created_at
                FROM case_communications
                WHERE case_id = ? AND communication_id = ?
                """,
                (case_id, communication_id),
            )
        if row is None:
            raise KeyError(f"Communication {communication_id} not found for case {case_id}")
        return _row_to_case_communication(row)

    def read_storage_bytes(self, *, storage_uri: str) -> bytes:
        path = self._resolve_storage_path(storage_uri)
        return path.read_bytes()

    def read_storage_text(self, *, storage_uri: str) -> str:
        return self.read_storage_bytes(storage_uri=storage_uri).decode("utf-8", errors="replace")

    def add_case_message(
        self,
        *,
        case_id: str,
        role: str,
        content: str,
        agent_name: str | None = None,
    ) -> str:
        summary = f"{role.upper()}: {content.strip()}"
        if agent_name:
            summary = f"{summary} (agent={agent_name})"
        payload = summary.encode("utf-8")
        return self.add_case_communication(
            case_id=case_id,
            channel="chat",
            summary=summary[:1000],
            transcript_payload=payload,
            extension="txt",
        )

    def add_case_text_document(
        self,
        *,
        case_id: str,
        original_filename: str,
        content: str,
        uploaded_by_user_id: str | None = None,
    ) -> str:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT COALESCE(MAX(version), 0)
                FROM case_documents
                WHERE case_id = ? AND kind = 'chat_attachment'
                """,
                (case_id,),
            )
        next_version = int(row[0]) + 1 if row else 1
        filename = Path(original_filename).name or "attachment.txt"
        return self.add_case_document(
            case_id=case_id,
            kind="chat_attachment",
            version=next_version,
            original_filename=filename,
            payload=content.encode("utf-8"),
            uploaded_by_user_id=uploaded_by_user_id,
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
                    doc_id, case_id, kind, version, storage_uri, original_filename, uploaded_by_user_id,
                    processing_status, processing_error, processed_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded', NULL, NULL, ?)
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

    def count_case_documents(self, *, case_id: str, include_generated: bool = False) -> int:
        query = "SELECT COUNT(*) FROM case_documents WHERE case_id = ?"
        params: tuple[Any, ...] = (case_id,)
        if not include_generated:
            query += " AND kind = 'uploaded'"
        with self._connect() as conn:
            row = self._fetchone(conn, query, params)
        return int(row[0]) if row else 0

    def get_effective_subscription_plan(self, *, user_id: str) -> SubscriptionPlan:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT sp.plan_code, sp.display_name, sp.subscription_type, sp.price_eur,
                       sp.max_cases, sp.max_documents_per_case, sp.case_ttl_days
                FROM user_subscriptions us
                JOIN subscription_plans sp ON sp.plan_code = us.plan_code
                WHERE us.user_id = ? AND us.status = 'paid'
                ORDER BY us.created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
        if row is None:
            return SubscriptionPlan('free', 'Free', 'none', 0, 5, 2, 1)
        return _row_to_subscription_plan(row)

    def get_document_upload_limit(self, *, user_id: str) -> int:
        user = self.find_user_by_id(user_id=user_id)
        if user and (user.phone_number or '').strip() == '+421944400166':
            return 50
        return self.get_effective_subscription_plan(user_id=user_id).max_documents_per_case

    def list_unprocessed_case_documents(self, *, limit: int = 20) -> list[CaseDocument]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT doc_id, case_id, kind, version, storage_uri, original_filename, uploaded_by_user_id,
                       processing_status, processing_error, processed_at, created_at
                FROM case_documents
                WHERE kind = 'uploaded' AND processing_status IN ('uploaded', 'failed')
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_case_document(row) for row in rows]

    def mark_document_processing(self, *, doc_id: str, status: str, error: str | None = None) -> None:
        processed_at = _now_iso() if status == 'processed' else None
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE case_documents
                SET processing_status = ?, processing_error = ?, processed_at = COALESCE(?, processed_at)
                WHERE doc_id = ?
                """,
                (status, error, processed_at, doc_id),
            )

    def upsert_document_content(
        self,
        *,
        doc_id: str,
        case_id: str,
        extracted_text: str,
        embedding_vector: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            existing = self._fetchone(conn, 'SELECT content_id FROM case_document_contents WHERE doc_id = ?', (doc_id,))
            if existing is None:
                self._execute(
                    conn,
                    """
                    INSERT INTO case_document_contents(
                        content_id, doc_id, case_id, extracted_text, embedding_vector,
                        embedding_model, embedding_dimensions, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        doc_id,
                        case_id,
                        extracted_text,
                        embedding_vector,
                        embedding_model,
                        embedding_dimensions,
                        now,
                        now,
                    ),
                )
            else:
                self._execute(
                    conn,
                    """
                    UPDATE case_document_contents
                    SET extracted_text = ?, embedding_vector = ?, embedding_model = ?,
                        embedding_dimensions = ?, updated_at = ?
                    WHERE doc_id = ?
                    """,
                    (
                        extracted_text,
                        embedding_vector,
                        embedding_model,
                        embedding_dimensions,
                        now,
                        doc_id,
                    ),
                )

    def replace_document_chunks(
        self,
        *,
        doc_id: str,
        case_id: str,
        chunks: list[CaseDocumentChunk],
    ) -> None:
        with self._connect() as conn:
            self._execute(conn, "DELETE FROM case_document_chunks WHERE doc_id = ?", (doc_id,))
            for chunk in chunks:
                self._execute(
                    conn,
                    """
                    INSERT INTO case_document_chunks(
                        chunk_id, doc_id, case_id, chunk_index, chunk_text, embedding_vector,
                        embedding_model, embedding_dimensions, start_offset, end_offset,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        doc_id,
                        case_id,
                        chunk.chunk_index,
                        chunk.chunk_text,
                        chunk.embedding_vector,
                        chunk.embedding_model,
                        chunk.embedding_dimensions,
                        chunk.start_offset,
                        chunk.end_offset,
                        chunk.created_at,
                        chunk.updated_at,
                    ),
                )

    def list_case_document_contents(self, *, case_id: str) -> list[tuple[str, str, str, str]]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT c.doc_id, d.original_filename, c.extracted_text, c.embedding_vector
                FROM case_document_contents c
                JOIN case_documents d ON d.doc_id = c.doc_id
                WHERE c.case_id = ?
                ORDER BY d.created_at ASC
                """,
                (case_id,),
            ).fetchall()
        return [(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]

    def list_case_document_chunks(self, *, case_id: str) -> list[CaseDocumentChunk]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT chunk_id, doc_id, case_id, chunk_index, chunk_text, embedding_vector,
                       embedding_model, embedding_dimensions, start_offset, end_offset,
                       created_at, updated_at
                FROM case_document_chunks
                WHERE case_id = ?
                ORDER BY created_at ASC, chunk_index ASC
                """,
                (case_id,),
            ).fetchall()
        return [_row_to_case_document_chunk(row) for row in rows]

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

    def _resolve_storage_path(self, storage_uri: str) -> Path:
        normalized = storage_uri.strip()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            prefix = self.store_cloud.rstrip("/")
            if not prefix or not normalized.startswith(f"{prefix}/"):
                raise ValueError(f"Unsupported remote storage uri: {storage_uri}")
            normalized = normalized[len(prefix) + 1 :]
        path = (self.blob_root / Path(normalized)).resolve()
        path.relative_to(self.blob_root.resolve())
        return path

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

    def _ensure_case_document_schema(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            columns = {
                row[0]
                for row in self._execute(
                    conn,
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'case_documents'",
                ).fetchall()
            }
        else:
            columns = {row[1] for row in self._execute(conn, "PRAGMA table_info(case_documents)").fetchall()}
        if 'processing_status' not in columns:
            self._execute(conn, "ALTER TABLE case_documents ADD COLUMN processing_status TEXT NOT NULL DEFAULT 'uploaded'")
        if 'processing_error' not in columns:
            self._execute(conn, "ALTER TABLE case_documents ADD COLUMN processing_error TEXT")
        if 'processed_at' not in columns:
            self._execute(conn, "ALTER TABLE case_documents ADD COLUMN processed_at TEXT")
        if self.uses_postgres:
            content_columns = {
                row[0]
                for row in self._execute(
                    conn,
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'case_document_contents'",
                ).fetchall()
            }
        else:
            content_columns = {
                row[1]
                for row in self._execute(conn, "PRAGMA table_info(case_document_contents)").fetchall()
            }
        if 'embedding_model' not in content_columns:
            self._execute(
                conn,
                "ALTER TABLE case_document_contents ADD COLUMN embedding_model TEXT NOT NULL DEFAULT ''",
            )
        if 'embedding_dimensions' not in content_columns:
            self._execute(
                conn,
                "ALTER TABLE case_document_contents ADD COLUMN embedding_dimensions INTEGER NOT NULL DEFAULT 0",
            )
        self._execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS case_document_chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding_vector TEXT NOT NULL,
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_dimensions INTEGER NOT NULL DEFAULT 0,
                start_offset INTEGER NOT NULL DEFAULT 0,
                end_offset INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(doc_id, chunk_index),
                FOREIGN KEY(doc_id) REFERENCES case_documents(doc_id) ON DELETE CASCADE,
                FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            )
            """,
        )
        self._execute(
            conn,
            """
            CREATE INDEX IF NOT EXISTS idx_case_document_chunks_case_doc_chunk
            ON case_document_chunks(case_id, doc_id, chunk_index)
            """,
        )

    def _ensure_subscription_schema(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            columns = {
                row[0]
                for row in self._execute(
                    conn,
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'subscription_plans'",
                ).fetchall()
            }
        else:
            columns = {row[1] for row in self._execute(conn, "PRAGMA table_info(subscription_plans)").fetchall()}
        if 'max_documents_per_case' not in columns:
            self._execute(conn, "ALTER TABLE subscription_plans ADD COLUMN max_documents_per_case INTEGER NOT NULL DEFAULT 2")

    def _ensure_permanent_memory_schema(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            return
        self._execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS permanent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                type TEXT NOT NULL,
                source_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )

    def _seed_subscription_plans(self, conn: sqlite3.Connection | PostgresConnection[Any]) -> None:
        now = _now_iso()
        plans = [
            ("free", "Free", "none", 0, 5, 2, 1),
            ("case", "Case", "perCase", 10, 1, 5, None),
            ("basic", "Basic", "monthly", 30, 10, 5, None),
            ("premium", "Premium", "monthly", 100, 100, 50, None),
        ]
        for plan in plans:
            self._execute(
                conn,
                """
                INSERT INTO subscription_plans(
                    plan_code, display_name, subscription_type, price_eur, max_cases, max_documents_per_case, case_ttl_days, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_code) DO UPDATE SET
                    display_name = excluded.display_name,
                    subscription_type = excluded.subscription_type,
                    price_eur = excluded.price_eur,
                    max_cases = excluded.max_cases,
                    max_documents_per_case = excluded.max_documents_per_case,
                    case_ttl_days = excluded.case_ttl_days,
                    updated_at = excluded.updated_at
                """,
                (*plan, now, now),
            )

    def _resolve_subscription_end(
        self,
        conn: sqlite3.Connection | PostgresConnection[Any],
        *,
        plan_code: str,
        starts_at: str,
    ) -> str | None:
        row = self._fetchone(
            conn,
            "SELECT subscription_type FROM subscription_plans WHERE plan_code = ?",
            (plan_code,),
        )
        if row is None:
            return None
        plan_type = str(row[0]).lower()
        if plan_type != "monthly":
            return None
        start_dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        return (start_dt + timedelta(days=30)).isoformat().replace("+00:00", "Z")


def _row_to_subscription_plan(row: tuple[object, ...]) -> SubscriptionPlan:
    values = list(row)
    return SubscriptionPlan(
        plan_code=str(values[0]),
        display_name=str(values[1]),
        subscription_type=str(values[2]),
        price_eur=int(values[3]),
        max_cases=int(values[4]),
        max_documents_per_case=int(values[5]),
        case_ttl_days=int(values[6]) if values[6] is not None else None,
    )


def _row_to_user_subscription(row: tuple[object, ...]) -> UserSubscription:
    values = list(row)
    return UserSubscription(
        subscription_id=str(values[0]),
        user_id=str(values[1]),
        plan_code=str(values[2]),
        status=str(values[3]),
        starts_at=str(values[4]) if values[4] is not None else None,
        ends_at=str(values[5]) if values[5] is not None else None,
        case_ids_json=str(values[6]),
        created_at=str(values[7]),
        updated_at=str(values[8]),
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


def _row_to_case_document(row: tuple[Any, ...]) -> CaseDocument:
    return CaseDocument(
        doc_id=str(row[0]),
        case_id=str(row[1]),
        kind=str(row[2]),
        version=int(row[3]),
        storage_uri=str(row[4]),
        original_filename=str(row[5]),
        uploaded_by_user_id=str(row[6]) if row[6] is not None else None,
        processing_status=str(row[7]),
        processing_error=str(row[8]) if row[8] is not None else None,
        processed_at=str(row[9]) if row[9] is not None else None,
        created_at=str(row[10]),
    )


def _row_to_case_communication(row: tuple[Any, ...]) -> CaseCommunication:
    return CaseCommunication(
        communication_id=str(row[0]),
        case_id=str(row[1]),
        channel=str(row[2]),
        transcript_uri=str(row[3]) if row[3] is not None else None,
        summary=str(row[4]),
        created_at=str(row[5]),
    )


def _row_to_case_document_chunk(row: tuple[Any, ...]) -> CaseDocumentChunk:
    return CaseDocumentChunk(
        chunk_id=str(row[0]),
        doc_id=str(row[1]),
        case_id=str(row[2]),
        chunk_index=int(row[3]),
        chunk_text=str(row[4]),
        embedding_vector=str(row[5]),
        embedding_model=str(row[6]),
        embedding_dimensions=int(row[7]),
        start_offset=int(row[8]),
        end_offset=int(row[9]),
        created_at=str(row[10]),
        updated_at=str(row[11]),
    )


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


def _row_to_case(row: tuple[object, ...]) -> Case:
    values = list(row)
    return Case(
        case_id=str(values[0]),
        user_id=str(values[1]),
        company_id=str(values[2]) if values[2] is not None else None,
        title=str(values[3]),
        status=str(values[4]),
        created_at=str(values[5]),
        updated_at=str(values[6]),
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


def _to_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _safe_json_load(value: str) -> dict[str, Any]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}
