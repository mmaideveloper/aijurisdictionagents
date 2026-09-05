from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import random
import secrets
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
from ..model_parameters import (
    ModelParameters,
    deserialize_model_parameters,
    serialize_model_parameters,
)

DEFAULT_UNLIMITED_ACCESS_EMAILS = ("mmaideveloper@gmail.com",)
DEFAULT_ADMIN_EMAILS = ("mmaideveloper@gmail.com",)
USER_ROLE_ADMIN = "admin"
USER_ROLE_USER = "user"
UNLIMITED_ACCESS_LIMIT = 2_147_483_647
CASE_WRITE_WINDOW_EXPIRED_CODE = "case_write_window_expired"


@dataclass(frozen=True)
class CaseWriteBlockReason:
    code: str
    message: str
    plan_display_name: str
    ttl_days: int

    def to_api_detail(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "params": {
                "plan": self.plan_display_name,
                "days": self.ttl_days,
            },
        }


@dataclass(frozen=True)
class User:
    user_id: str
    phone_number: str | None
    email: str
    first_name: str | None
    last_name: str | None
    full_name: str
    address: str | None
    city: str | None
    country: str | None
    zip_code: str | None
    tax_number: str | None
    identity_card_number: str | None
    date_of_birth: str | None
    social_security_number: str | None
    data_processing_consent_at: str | None
    data_processing_consent_version: str | None
    mcp_api_key_hash: str | None
    mcp_api_key_expires_at: str | None
    created_at: str | None
    role: str = USER_ROLE_USER
    is_enabled: bool = True


@dataclass(frozen=True)
class AdminUser:
    user_id: str
    phone_number: str | None
    email: str
    full_name: str
    role: str
    is_enabled: bool
    created_at: str | None


@dataclass(frozen=True)
class AdminCaseUser:
    user_id: str
    email: str
    full_name: str
    role: str
    is_enabled: bool
    created_at: str | None


@dataclass(frozen=True)
class UserMfaSettings:
    user_id: str
    totp_enabled: bool
    totp_pending: bool
    totp_secret_protected: str | None
    pending_totp_secret_protected: str | None
    totp_enabled_at: str | None
    updated_at: str


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
class CaseCatalogSelection:
    selection_id: str
    selection_scope: str
    entity_id: str
    case_id: str
    session_id: str
    case_type_id: str
    case_type_key: str
    case_type_name: str
    prompt_ids: tuple[str, ...]
    template_ids: tuple[str, ...]
    template_keys: tuple[str, ...]
    status: str
    confidence_score: float
    confidence_gap: float
    source: str
    first_message_preview: str
    first_message_sha256: str
    clarification_question: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CaseCatalogEvent:
    event_id: str
    case_id: str
    session_id: str
    event_type: str
    status: str
    severity: str
    summary: str
    details: dict[str, Any]
    created_at: str


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
class CaseDocumentDeletionEvent:
    event_id: str
    case_id: str
    doc_id: str
    document_kind: str
    actor_user_id: str
    correlation_id: str
    outcome: str
    deleted_at: str
    communication_id: str


@dataclass(frozen=True)
class DocumentShare:
    share_id: str
    token_hash: str
    case_id: str
    doc_id: str
    sender_user_id: str
    recipient_email: str
    locale: str
    status: str
    expires_at: str
    code_hash: str
    code_expires_at: str | None
    code_attempts: int
    last_code_sent_at: str | None
    session_token_hash: str
    session_expires_at: str | None
    last_accessed_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CaseCommunication:
    communication_id: str
    case_id: str
    channel: str
    transcript_uri: str | None
    summary: str
    created_at: str
    presentation: dict[str, Any]


@dataclass(frozen=True)
class CaseCitation:
    citation_id: str
    case_id: str
    question_message_id: str | None
    answer_message_id: str | None
    source_type: str
    source_id: str | None
    source_url: str | None
    title: str
    citation_label: str | None
    law_number: str | None
    section: str | None
    effective_from: str | None
    court: str | None
    ecli: str | None
    file_number: str | None
    decision_date: str | None
    snippet: str | None
    retrieval_tool: str | None
    relevance_score: float | None
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


@dataclass(frozen=True)
class AIModelProvider:
    provider_id: str
    provider_code: str
    provider_type: str
    display_name: str
    base_url: str
    api_version: str
    region: str
    data_zone: str
    is_external: bool
    is_local: bool
    health_check_url: str
    model_parameters: ModelParameters
    enabled: bool
    created_at: str
    updated_at: str
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


@dataclass(frozen=True)
class AIModelProfile:
    model_profile_id: str
    provider_id: str
    model_code: str
    deployment_name: str
    model_parameters: ModelParameters
    context_window_tokens: int
    input_price_per_1m: float
    cached_input_price_per_1m: float
    output_price_per_1m: float
    billing_currency: str
    effective_from: str | None
    effective_to: str | None
    eu_data_zone_capable: bool
    is_default_for_free: bool
    enabled: bool
    created_at: str
    updated_at: str
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


@dataclass(frozen=True)
class AIModelCredential:
    credential_id: str
    provider_id: str
    credential_name: str
    secret_type: str
    protected_secret: str
    secret_preview: str
    secret_value: str | None
    enabled: bool
    created_at: str
    updated_at: str
    last_revealed_at: str | None


@dataclass(frozen=True)
class AITaskRoutePolicy:
    policy_id: str
    task_type: str
    plan_code: str
    model_group_id: str | None
    preferred_external_model_profile_id: str | None
    preferred_local_model_profile_id: str | None
    allow_external: bool
    require_external_ack: bool
    require_eu_data_zone: bool
    fallback_local_on_error: bool
    fallback_local_on_budget: bool
    max_cost_eur: float
    priority: int
    enabled: bool
    created_at: str
    updated_at: str
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


@dataclass(frozen=True)
class AIModelGroup:
    model_group_id: str
    group_code: str
    display_name: str
    priority: int
    enabled: bool
    created_at: str
    updated_at: str
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


@dataclass(frozen=True)
class AIModelGroupMembership:
    model_group_id: str
    user_id: str
    email: str
    full_name: str
    created_at: str


@dataclass(frozen=True)
class AIModelUserOverride:
    override_id: str
    user_id: str
    model_profile_id: str
    enabled: bool
    created_by_admin_user_id: str
    updated_by_admin_user_id: str
    disabled_by_admin_user_id: str
    created_reason: str
    updated_reason: str
    disabled_reason: str
    created_at: str
    updated_at: str
    disabled_at: str | None


@dataclass(frozen=True)
class AIModelAdminAuditEvent:
    audit_event_id: str
    admin_user_id: str
    admin_email: str
    action: str
    entity_type: str
    entity_id: str
    old_value_summary: str
    new_value_summary: str
    reason: str
    correlation_id: str
    created_at: str


@dataclass(frozen=True)
class AIModelRouteSelection:
    policy: AITaskRoutePolicy | None
    provider: AIModelProvider | None
    model_profile: AIModelProfile | None
    route_type: str
    task_type: str
    plan_code: str
    requires_external_ack: bool
    reason: str


@dataclass(frozen=True)
class AIModelUsageSummary:
    case_id: str
    user_id: str
    subscription_id: str
    plan_code: str
    task_type: str
    provider: str
    model: str
    route_type: str
    status: str
    fallback_reason: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_eur: float
    request_count: int


@dataclass(frozen=True)
class AIModelTopCaseUsage:
    case_id: str
    plan_code: str
    provider: str
    model: str
    route_type: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_eur: float
    request_count: int


@dataclass(frozen=True)
class AIModelUsageAuditEntry:
    usage_id: str
    case_id: str
    user_id: str
    subscription_id: str
    plan_code: str
    task_type: str
    model_group_id: str
    provider: str
    model: str
    route_type: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_provider_currency: float
    estimated_cost_eur: float
    provider_currency: str
    exchange_rate_used: float
    request_started_at: str
    request_completed_at: str
    latency_ms: int
    status: str
    fallback_reason: str
    confidentiality_warning_ack_id: str
    session_id: str
    question_id: str
    question_preview: str
    question_sha256: str
    answer_id: str
    audit_metadata: dict[str, Any]
    created_at: str


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
        if self.db_option == "local":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.storage_option == "local":
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
                    address TEXT,
                    city TEXT,
                    country TEXT,
                    zip_code TEXT,
                    tax_number TEXT,
                    identity_card_number TEXT,
                    date_of_birth TEXT,
                    social_security_number TEXT,
                    data_processing_consent_at TEXT,
                    data_processing_consent_version TEXT,
                    mcp_api_key_hash TEXT,
                    mcp_api_key_expires_at TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_enabled INTEGER NOT NULL DEFAULT 1,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS registration_codes (
                    email TEXT PRIMARY KEY,
                    code_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS device_auth_tokens (
                    user_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, device_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS mcp_pending_signups (
                    pending_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mcp_oauth_authorization_codes (
                    code TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    resource TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT 'mcp:laws',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS mcp_otp_verifications (
                    user_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    verified_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, purpose),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_mfa_settings (
                    user_id TEXT PRIMARY KEY,
                    totp_secret_protected TEXT,
                    pending_totp_secret_protected TEXT,
                    totp_enabled_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS mfa_login_challenges (
                    challenge_token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
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

                CREATE TABLE IF NOT EXISTS case_catalog_selections (
                    selection_id TEXT PRIMARY KEY,
                    selection_scope TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    case_id TEXT DEFAULT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    case_type_id TEXT NOT NULL DEFAULT '',
                    case_type_key TEXT NOT NULL DEFAULT '',
                    case_type_name TEXT NOT NULL DEFAULT '',
                    prompt_ids_json TEXT NOT NULL DEFAULT '[]',
                    template_ids_json TEXT NOT NULL DEFAULT '[]',
                    template_keys_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'unclassified',
                    confidence_score REAL NOT NULL DEFAULT 0,
                    confidence_gap REAL NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    first_message_preview TEXT NOT NULL DEFAULT '',
                    first_message_sha256 TEXT NOT NULL DEFAULT '',
                    clarification_question TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(selection_scope, entity_id),
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS case_catalog_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT DEFAULT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'info',
                    summary TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
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

                CREATE TABLE IF NOT EXISTS document_shares (
                    share_id TEXT PRIMARY KEY,
                    token_hash TEXT UNIQUE NOT NULL,
                    case_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    sender_user_id TEXT NOT NULL,
                    recipient_email_protected TEXT NOT NULL,
                    locale TEXT NOT NULL DEFAULT 'en',
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at TEXT NOT NULL,
                    code_hash TEXT NOT NULL DEFAULT '',
                    code_expires_at TEXT,
                    code_attempts INTEGER NOT NULL DEFAULT 0,
                    last_code_sent_at TEXT,
                    session_token_hash TEXT NOT NULL DEFAULT '',
                    session_expires_at TEXT,
                    last_accessed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
                    FOREIGN KEY(doc_id) REFERENCES case_documents(doc_id) ON DELETE CASCADE,
                    FOREIGN KEY(sender_user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_document_shares_sender_document
                ON document_shares(sender_user_id, case_id, doc_id, created_at);

                CREATE TABLE IF NOT EXISTS document_share_audit_events (
                    audit_event_id TEXT PRIMARY KEY,
                    share_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(share_id) REFERENCES document_shares(share_id) ON DELETE CASCADE
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
                    presentation_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS case_document_deletion_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    document_kind TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    deleted_at TEXT NOT NULL,
                    communication_id TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
                    FOREIGN KEY(actor_user_id) REFERENCES users(user_id),
                    FOREIGN KEY(communication_id) REFERENCES case_communications(communication_id)
                );

                CREATE INDEX IF NOT EXISTS idx_case_document_deletion_events_case_deleted
                ON case_document_deletion_events(case_id, deleted_at DESC);

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
            self._ensure_mcp_oauth_schema(conn)
            self._ensure_case_document_schema(conn)
            self._ensure_case_citation_schema(conn)
            self._ensure_subscription_schema(conn)
            self._ensure_permanent_memory_schema(conn)
            self._ensure_ai_model_routing_schema(conn)
            self._seed_subscription_plans(conn)
            self._seed_ai_model_routing(conn)

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

    def upsert_ai_model_provider(
        self,
        *,
        provider_code: str,
        provider_type: str,
        display_name: str,
        base_url: str = "",
        api_version: str = "",
        region: str = "",
        data_zone: str = "",
        is_external: bool = False,
        is_local: bool = False,
        health_check_url: str = "",
        model_parameters: dict[str, object] | None = None,
        enabled: bool = True,
        provider_id: str | None = None,
    ) -> AIModelProvider:
        now = _now_iso()
        normalized_code = provider_code.strip().lower()
        normalized_provider_type = provider_type.strip().lower()
        resolved_id = provider_id or normalized_code
        with self._connect() as conn:
            existing_parameters = self._fetchone(
                conn,
                "SELECT model_parameters_json FROM ai_model_providers WHERE provider_code = ?",
                (normalized_code,),
            )
            parameters_json = (
                str(existing_parameters[0])
                if model_parameters is None and existing_parameters is not None
                else serialize_model_parameters(
                    model_parameters,
                    provider_type=normalized_provider_type,
                )
            )
            self._execute(
                conn,
                """
                INSERT INTO ai_model_providers(
                    provider_id, provider_code, provider_type, display_name, base_url,
                    api_version, region, data_zone, is_external, is_local, health_check_url,
                    enabled, created_at, updated_at, model_parameters_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_code) DO UPDATE SET
                    provider_type = excluded.provider_type,
                    display_name = excluded.display_name,
                    base_url = excluded.base_url,
                    api_version = excluded.api_version,
                    region = excluded.region,
                    data_zone = excluded.data_zone,
                    is_external = excluded.is_external,
                    is_local = excluded.is_local,
                    health_check_url = excluded.health_check_url,
                    model_parameters_json = excluded.model_parameters_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    resolved_id,
                    normalized_code,
                    normalized_provider_type,
                    display_name.strip(),
                    base_url.strip(),
                    api_version.strip(),
                    region.strip(),
                    data_zone.strip(),
                    _bool_int(is_external),
                    _bool_int(is_local),
                    health_check_url.strip(),
                    _bool_int(enabled),
                    now,
                    now,
                    parameters_json,
                ),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT provider_id, provider_code, provider_type, display_name, base_url,
                       api_version, region, data_zone, is_external, is_local, health_check_url,
                       enabled, created_at, updated_at, deleted_at, deleted_by_admin_user_id,
                       deleted_reason, model_parameters_json
                FROM ai_model_providers
                WHERE provider_code = ?
                """,
                (normalized_code,),
            )
        if row is None:
            raise RuntimeError(f"AI model provider was not saved: {normalized_code}")
        return _row_to_ai_model_provider(row)

    def list_ai_model_providers(self, *, include_deleted: bool = False) -> list[AIModelProvider]:
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT provider_id, provider_code, provider_type, display_name, base_url,
                       api_version, region, data_zone, is_external, is_local, health_check_url,
                       enabled, created_at, updated_at, deleted_at, deleted_by_admin_user_id,
                       deleted_reason, model_parameters_json
                FROM ai_model_providers
                {where}
                ORDER BY deleted_at IS NOT NULL, is_local DESC, display_name, provider_code
                """,
            ).fetchall()
        return [_row_to_ai_model_provider(row) for row in rows]

    def soft_delete_ai_model_provider(
        self,
        *,
        provider_id: str,
        admin_user_id: str,
        reason: str,
    ) -> AIModelProvider:
        normalized_provider_id = provider_id.strip()
        normalized_admin_user_id = admin_user_id.strip()
        normalized_reason = reason.strip()
        if not normalized_provider_id:
            raise ValueError("provider_id is required")
        if not normalized_reason:
            raise ValueError("reason is required")
        now = _now_iso()
        with self._connect() as conn:
            existing = self._fetchone(
                conn,
                """
                SELECT provider_id
                FROM ai_model_providers
                WHERE provider_id = ?
                """,
                (normalized_provider_id,),
            )
            if existing is None:
                raise KeyError(f"AI model provider {normalized_provider_id} not found")
            self._execute(
                conn,
                """
                UPDATE ai_model_providers
                SET enabled = 0,
                    deleted_at = ?,
                    deleted_by_admin_user_id = ?,
                    deleted_reason = ?,
                    updated_at = ?
                WHERE provider_id = ?
                """,
                (
                    now,
                    normalized_admin_user_id,
                    normalized_reason,
                    now,
                    normalized_provider_id,
                ),
            )
            self._execute(
                conn,
                """
                UPDATE ai_model_profiles
                SET enabled = 0,
                    updated_at = ?
                WHERE provider_id = ?
                """,
                (now, normalized_provider_id),
            )
            self._execute(
                conn,
                """
                UPDATE ai_model_credentials
                SET enabled = 0,
                    updated_at = ?
                WHERE provider_id = ?
                """,
                (now, normalized_provider_id),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT provider_id, provider_code, provider_type, display_name, base_url,
                       api_version, region, data_zone, is_external, is_local, health_check_url,
                       enabled, created_at, updated_at, deleted_at, deleted_by_admin_user_id,
                       deleted_reason, model_parameters_json
                FROM ai_model_providers
                WHERE provider_id = ?
                """,
                (normalized_provider_id,),
            )
        if row is None:
            raise RuntimeError(f"AI model provider was not soft-deleted: {normalized_provider_id}")
        return _row_to_ai_model_provider(row)

    def upsert_ai_model_profile(
        self,
        *,
        provider_id: str,
        model_code: str,
        deployment_name: str = "",
        model_parameters: dict[str, object] | None = None,
        context_window_tokens: int = 0,
        input_price_per_1m: float = 0.0,
        cached_input_price_per_1m: float = 0.0,
        output_price_per_1m: float = 0.0,
        billing_currency: str = "USD",
        effective_from: str | None = None,
        effective_to: str | None = None,
        eu_data_zone_capable: bool = False,
        is_default_for_free: bool = False,
        enabled: bool = True,
        model_profile_id: str | None = None,
    ) -> AIModelProfile:
        now = _now_iso()
        normalized_model = model_code.strip()
        resolved_id = model_profile_id or f"{provider_id}:{normalized_model}"
        with self._connect() as conn:
            provider_row = self._fetchone(
                conn,
                "SELECT provider_type FROM ai_model_providers WHERE provider_id = ? AND deleted_at IS NULL",
                (provider_id,),
            )
            if provider_row is None:
                raise ValueError("Provider does not exist")
            existing_parameters = self._fetchone(
                conn,
                "SELECT model_parameters_json FROM ai_model_profiles WHERE model_profile_id = ?",
                (resolved_id,),
            )
            parameters_json = (
                str(existing_parameters[0])
                if model_parameters is None and existing_parameters is not None
                else serialize_model_parameters(
                    model_parameters,
                    provider_type=str(provider_row[0]),
                )
            )
            self._execute(
                conn,
                """
                INSERT INTO ai_model_profiles(
                    model_profile_id, provider_id, model_code, deployment_name,
                    context_window_tokens, input_price_per_1m, cached_input_price_per_1m,
                    output_price_per_1m, billing_currency, effective_from, effective_to,
                    eu_data_zone_capable, is_default_for_free, enabled, created_at, updated_at,
                    model_parameters_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_profile_id) DO UPDATE SET
                    provider_id = excluded.provider_id,
                    model_code = excluded.model_code,
                    deployment_name = excluded.deployment_name,
                    model_parameters_json = excluded.model_parameters_json,
                    context_window_tokens = excluded.context_window_tokens,
                    input_price_per_1m = excluded.input_price_per_1m,
                    cached_input_price_per_1m = excluded.cached_input_price_per_1m,
                    output_price_per_1m = excluded.output_price_per_1m,
                    billing_currency = excluded.billing_currency,
                    effective_from = excluded.effective_from,
                    effective_to = excluded.effective_to,
                    eu_data_zone_capable = excluded.eu_data_zone_capable,
                    is_default_for_free = excluded.is_default_for_free,
                    enabled = excluded.enabled,
                    deleted_at = NULL,
                    deleted_by_admin_user_id = '',
                    deleted_reason = '',
                    updated_at = excluded.updated_at
                """,
                (
                    resolved_id,
                    provider_id,
                    normalized_model,
                    deployment_name.strip(),
                    max(context_window_tokens, 0),
                    max(input_price_per_1m, 0.0),
                    max(cached_input_price_per_1m, 0.0),
                    max(output_price_per_1m, 0.0),
                    billing_currency.strip().upper() or "USD",
                    effective_from,
                    effective_to,
                    _bool_int(eu_data_zone_capable),
                    _bool_int(is_default_for_free),
                    _bool_int(enabled),
                    now,
                    now,
                    parameters_json,
                ),
            )
            if is_default_for_free:
                self._execute(
                    conn,
                    """
                    UPDATE ai_model_profiles
                    SET is_default_for_free = 0, updated_at = ?
                    WHERE provider_id = ?
                      AND model_profile_id <> ?
                    """,
                    (now, provider_id, resolved_id),
                )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT model_profile_id, provider_id, model_code, deployment_name,
                       context_window_tokens, input_price_per_1m, cached_input_price_per_1m,
                       output_price_per_1m, billing_currency, effective_from, effective_to,
                       eu_data_zone_capable, is_default_for_free, enabled, created_at, updated_at,
                        deleted_at, deleted_by_admin_user_id, deleted_reason, model_parameters_json
                FROM ai_model_profiles
                WHERE model_profile_id = ?
                """,
                (resolved_id,),
            )
        if row is None:
            raise RuntimeError(f"AI model profile was not saved: {resolved_id}")
        return _row_to_ai_model_profile(row)

    def soft_delete_ai_model_profile(
        self,
        *,
        model_profile_id: str,
        admin_user_id: str,
        reason: str,
    ) -> AIModelProfile:
        normalized_id = model_profile_id.strip()
        if not normalized_id:
            raise ValueError("model_profile_id is required")
        now = _now_iso()
        with self._connect() as conn:
            existing = self._fetchone(
                conn,
                """
                SELECT model_profile_id, provider_id, model_code, deployment_name,
                       context_window_tokens, input_price_per_1m, cached_input_price_per_1m,
                       output_price_per_1m, billing_currency, effective_from, effective_to,
                       eu_data_zone_capable, is_default_for_free, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason, model_parameters_json
                FROM ai_model_profiles
                WHERE model_profile_id = ?
                """,
                (normalized_id,),
            )
            if existing is None:
                raise KeyError(f"AI model profile {normalized_id} not found")
            profile = _row_to_ai_model_profile(existing)
            if profile.deleted_at:
                return profile
            if profile.is_default_for_free:
                raise ValueError("Cannot delete the default free model profile")
            active_policy_row = self._fetchone(
                conn,
                """
                SELECT policy_id
                FROM ai_task_route_policies
                WHERE enabled = 1
                  AND deleted_at IS NULL
                  AND (
                    preferred_external_model_profile_id = ?
                    OR preferred_local_model_profile_id = ?
                  )
                LIMIT 1
                """,
                (normalized_id, normalized_id),
            )
            if active_policy_row is not None:
                raise ValueError("Cannot delete a model profile used by an enabled routing policy")
            self._execute(
                conn,
                """
                UPDATE ai_model_profiles
                SET enabled = 0,
                    is_default_for_free = 0,
                    deleted_at = ?,
                    deleted_by_admin_user_id = ?,
                    deleted_reason = ?,
                    updated_at = ?
                WHERE model_profile_id = ?
                """,
                (now, admin_user_id.strip(), reason.strip(), now, normalized_id),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT model_profile_id, provider_id, model_code, deployment_name,
                       context_window_tokens, input_price_per_1m, cached_input_price_per_1m,
                       output_price_per_1m, billing_currency, effective_from, effective_to,
                       eu_data_zone_capable, is_default_for_free, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason, model_parameters_json
                FROM ai_model_profiles
                WHERE model_profile_id = ?
                """,
                (normalized_id,),
            )
        if row is None:
            raise RuntimeError(f"AI model profile was not soft-deleted: {normalized_id}")
        return _row_to_ai_model_profile(row)

    def list_ai_model_profiles(
        self, *, provider_id: str | None = None, include_deleted: bool = False
    ) -> list[AIModelProfile]:
        filters: list[str] = []
        params: list[Any] = []
        if provider_id is not None:
            filters.append("provider_id = ?")
            params.append(provider_id.strip())
        if not include_deleted:
            filters.append("deleted_at IS NULL")
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT model_profile_id, provider_id, model_code, deployment_name,
                       context_window_tokens, input_price_per_1m, cached_input_price_per_1m,
                       output_price_per_1m, billing_currency, effective_from, effective_to,
                       eu_data_zone_capable, is_default_for_free, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason, model_parameters_json
                FROM ai_model_profiles
                {where}
                ORDER BY deleted_at IS NOT NULL, enabled DESC, provider_id, is_default_for_free DESC, model_code
                """,
                tuple(params),
            ).fetchall()
        return [_row_to_ai_model_profile(row) for row in rows]

    def upsert_ai_task_route_policy(
        self,
        *,
        task_type: str,
        plan_code: str = "",
        model_group_id: str | None = None,
        preferred_external_model_profile_id: str | None = None,
        preferred_local_model_profile_id: str | None = None,
        allow_external: bool = False,
        require_external_ack: bool = True,
        require_eu_data_zone: bool = True,
        fallback_local_on_error: bool = True,
        fallback_local_on_budget: bool = True,
        max_cost_eur: float = 0.0,
        priority: int = 0,
        enabled: bool = True,
        policy_id: str | None = None,
    ) -> AITaskRoutePolicy:
        now = _now_iso()
        normalized_task = _normalize_route_key(task_type, default="default")
        normalized_plan = _normalize_route_key(plan_code, default="")
        resolved_id = (
            policy_id or f"{normalized_task}:{normalized_plan}:{model_group_id or 'default'}"
        )
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO ai_task_route_policies(
                    policy_id, task_type, plan_code, model_group_id,
                    preferred_external_model_profile_id, preferred_local_model_profile_id,
                    allow_external, require_external_ack, require_eu_data_zone,
                    fallback_local_on_error, fallback_local_on_budget, max_cost_eur,
                    priority, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    task_type = excluded.task_type,
                    plan_code = excluded.plan_code,
                    model_group_id = excluded.model_group_id,
                    preferred_external_model_profile_id = excluded.preferred_external_model_profile_id,
                    preferred_local_model_profile_id = excluded.preferred_local_model_profile_id,
                    allow_external = excluded.allow_external,
                    require_external_ack = excluded.require_external_ack,
                    require_eu_data_zone = excluded.require_eu_data_zone,
                    fallback_local_on_error = excluded.fallback_local_on_error,
                    fallback_local_on_budget = excluded.fallback_local_on_budget,
                    max_cost_eur = excluded.max_cost_eur,
                    priority = excluded.priority,
                    enabled = excluded.enabled,
                    deleted_at = NULL,
                    deleted_by_admin_user_id = '',
                    deleted_reason = '',
                    updated_at = excluded.updated_at
                """,
                (
                    resolved_id,
                    normalized_task,
                    normalized_plan,
                    model_group_id,
                    preferred_external_model_profile_id,
                    preferred_local_model_profile_id,
                    _bool_int(allow_external),
                    _bool_int(require_external_ack),
                    _bool_int(require_eu_data_zone),
                    _bool_int(fallback_local_on_error),
                    _bool_int(fallback_local_on_budget),
                    max(max_cost_eur, 0.0),
                    priority,
                    _bool_int(enabled),
                    now,
                    now,
                ),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT policy_id, task_type, plan_code, model_group_id,
                       preferred_external_model_profile_id, preferred_local_model_profile_id,
                       allow_external, require_external_ack, require_eu_data_zone,
                       fallback_local_on_error, fallback_local_on_budget, max_cost_eur,
                       priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_task_route_policies
                WHERE policy_id = ?
                """,
                (resolved_id,),
            )
        if row is None:
            raise RuntimeError(f"AI task route policy was not saved: {resolved_id}")
        return _row_to_ai_task_route_policy(row)

    def soft_delete_ai_task_route_policy(
        self,
        *,
        policy_id: str,
        admin_user_id: str,
        reason: str,
    ) -> AITaskRoutePolicy:
        normalized_id = policy_id.strip()
        if not normalized_id:
            raise ValueError("policy_id is required")
        now = _now_iso()
        with self._connect() as conn:
            existing = self._fetchone(
                conn,
                """
                SELECT policy_id, task_type, plan_code, model_group_id,
                       preferred_external_model_profile_id, preferred_local_model_profile_id,
                       allow_external, require_external_ack, require_eu_data_zone,
                       fallback_local_on_error, fallback_local_on_budget, max_cost_eur,
                       priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_task_route_policies
                WHERE policy_id = ?
                """,
                (normalized_id,),
            )
            if existing is None:
                raise KeyError(f"AI task route policy {normalized_id} not found")
            policy = _row_to_ai_task_route_policy(existing)
            if policy.deleted_at:
                return policy
            self._execute(
                conn,
                """
                UPDATE ai_task_route_policies
                SET enabled = 0,
                    deleted_at = ?,
                    deleted_by_admin_user_id = ?,
                    deleted_reason = ?,
                    updated_at = ?
                WHERE policy_id = ?
                """,
                (now, admin_user_id.strip(), reason.strip(), now, normalized_id),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT policy_id, task_type, plan_code, model_group_id,
                       preferred_external_model_profile_id, preferred_local_model_profile_id,
                       allow_external, require_external_ack, require_eu_data_zone,
                       fallback_local_on_error, fallback_local_on_budget, max_cost_eur,
                       priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_task_route_policies
                WHERE policy_id = ?
                """,
                (normalized_id,),
            )
        if row is None:
            raise RuntimeError(f"AI task route policy was not soft-deleted: {normalized_id}")
        return _row_to_ai_task_route_policy(row)

    def list_ai_task_route_policies(
        self, *, include_deleted: bool = False
    ) -> list[AITaskRoutePolicy]:
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT policy_id, task_type, plan_code, model_group_id,
                       preferred_external_model_profile_id, preferred_local_model_profile_id,
                       allow_external, require_external_ack, require_eu_data_zone,
                       fallback_local_on_error, fallback_local_on_budget, max_cost_eur,
                       priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_task_route_policies
                {where}
                ORDER BY deleted_at IS NOT NULL, enabled DESC, priority DESC, task_type, plan_code, model_group_id
                """,
            ).fetchall()
        return [_row_to_ai_task_route_policy(row) for row in rows]

    def upsert_ai_model_credential(
        self,
        *,
        provider_id: str,
        secret_value: str,
        credential_name: str = "default",
        secret_type: str = "api_key",
        enabled: bool = True,
        credential_id: str | None = None,
    ) -> AIModelCredential:
        normalized_provider = provider_id.strip()
        normalized_name = _normalize_route_key(credential_name, default="default")
        normalized_type = _normalize_route_key(secret_type, default="api_key")
        if not normalized_provider:
            raise ValueError("provider_id is required")
        if not secret_value.strip():
            raise ValueError("secret_value is required")
        resolved_id = credential_id or f"{normalized_provider}:{normalized_type}:{normalized_name}"
        now = _now_iso()
        protected_secret = _protect_model_secret(secret_value.strip())
        secret_preview = _secret_preview(secret_value)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO ai_model_credentials(
                    credential_id, provider_id, credential_name, secret_type,
                    protected_secret, secret_preview, enabled, created_at, updated_at,
                    last_revealed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(credential_id) DO UPDATE SET
                    provider_id = excluded.provider_id,
                    credential_name = excluded.credential_name,
                    secret_type = excluded.secret_type,
                    protected_secret = excluded.protected_secret,
                    secret_preview = excluded.secret_preview,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    resolved_id,
                    normalized_provider,
                    normalized_name,
                    normalized_type,
                    protected_secret,
                    secret_preview,
                    _bool_int(enabled),
                    now,
                    now,
                ),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT credential_id, provider_id, credential_name, secret_type,
                       protected_secret, secret_preview, enabled, created_at,
                       updated_at, last_revealed_at
                FROM ai_model_credentials
                WHERE credential_id = ?
                """,
                (resolved_id,),
            )
        if row is None:
            raise RuntimeError(f"AI model credential was not saved: {resolved_id}")
        return _row_to_ai_model_credential(row, reveal_secret=False)

    def list_ai_model_credentials(
        self,
        *,
        provider_id: str | None = None,
        reveal: bool = False,
    ) -> list[AIModelCredential]:
        params: tuple[Any, ...] = ()
        where = ""
        if provider_id is not None:
            where = "WHERE provider_id = ?"
            params = (provider_id.strip(),)
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT credential_id, provider_id, credential_name, secret_type,
                       protected_secret, secret_preview, enabled, created_at,
                       updated_at, last_revealed_at
                FROM ai_model_credentials
                {where}
                ORDER BY provider_id, credential_name, secret_type
                """,
                params,
            ).fetchall()
            if reveal and rows:
                now = _now_iso()
                for credential_id in [str(row[0]) for row in rows]:
                    self._execute(
                        conn,
                        """
                        UPDATE ai_model_credentials
                        SET last_revealed_at = ?
                        WHERE credential_id = ?
                        """,
                        (now, credential_id),
                    )
                conn.commit()
                rows = self._execute(
                    conn,
                    f"""
                    SELECT credential_id, provider_id, credential_name, secret_type,
                           protected_secret, secret_preview, enabled, created_at,
                           updated_at, last_revealed_at
                    FROM ai_model_credentials
                    {where}
                    ORDER BY provider_id, credential_name, secret_type
                    """,
                    params,
                ).fetchall()
        return [_row_to_ai_model_credential(row, reveal_secret=reveal) for row in rows]

    def set_ai_model_credential_enabled(
        self,
        *,
        credential_id: str,
        enabled: bool,
    ) -> AIModelCredential:
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE ai_model_credentials
                SET enabled = ?, updated_at = ?
                WHERE credential_id = ?
                """,
                (_bool_int(enabled), now, credential_id.strip()),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT credential_id, provider_id, credential_name, secret_type,
                       protected_secret, secret_preview, enabled, created_at,
                       updated_at, last_revealed_at
                FROM ai_model_credentials
                WHERE credential_id = ?
                """,
                (credential_id.strip(),),
            )
        if row is None:
            raise KeyError(f"AI model credential {credential_id} not found")
        return _row_to_ai_model_credential(row, reveal_secret=False)

    def get_ai_model_provider_secret(
        self,
        *,
        provider_id: str,
        secret_type: str = "api_key",
    ) -> str | None:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT credential_id, provider_id, credential_name, secret_type,
                       protected_secret, secret_preview, enabled, created_at,
                       updated_at, last_revealed_at
                FROM ai_model_credentials
                WHERE provider_id = ?
                  AND secret_type = ?
                  AND enabled = 1
                ORDER BY credential_name = 'default' DESC, updated_at DESC
                LIMIT 1
                """,
                (provider_id.strip(), _normalize_route_key(secret_type, default="api_key")),
            )
        if row is None:
            return None
        return _row_to_ai_model_credential(row, reveal_secret=True).secret_value

    def upsert_ai_model_group(
        self,
        *,
        group_code: str,
        display_name: str,
        priority: int = 0,
        enabled: bool = True,
        model_group_id: str | None = None,
    ) -> AIModelGroup:
        now = _now_iso()
        normalized_code = _normalize_route_key(group_code, default="")
        if not normalized_code:
            raise ValueError("group_code is required")
        resolved_id = model_group_id or normalized_code
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO ai_model_groups(
                    model_group_id, group_code, display_name, priority,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_code) DO UPDATE SET
                    display_name = excluded.display_name,
                    priority = excluded.priority,
                    enabled = excluded.enabled,
                    deleted_at = NULL,
                    deleted_by_admin_user_id = '',
                    deleted_reason = '',
                    updated_at = excluded.updated_at
                """,
                (
                    resolved_id,
                    normalized_code,
                    display_name.strip(),
                    priority,
                    _bool_int(enabled),
                    now,
                    now,
                ),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT model_group_id, group_code, display_name, priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_model_groups
                WHERE group_code = ?
                """,
                (normalized_code,),
            )
        if row is None:
            raise RuntimeError(f"AI model group was not saved: {normalized_code}")
        return _row_to_ai_model_group(row)

    def soft_delete_ai_model_group(
        self,
        *,
        model_group_id: str,
        admin_user_id: str,
        reason: str,
    ) -> AIModelGroup:
        normalized_id = model_group_id.strip()
        if not normalized_id:
            raise ValueError("model_group_id is required")
        now = _now_iso()
        with self._connect() as conn:
            existing = self._fetchone(
                conn,
                """
                SELECT model_group_id, group_code, display_name, priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_model_groups
                WHERE model_group_id = ?
                """,
                (normalized_id,),
            )
            if existing is None:
                raise KeyError(f"AI model group {normalized_id} not found")
            group = _row_to_ai_model_group(existing)
            if group.deleted_at:
                return group
            self._execute(
                conn,
                """
                UPDATE ai_model_groups
                SET enabled = 0,
                    deleted_at = ?,
                    deleted_by_admin_user_id = ?,
                    deleted_reason = ?,
                    updated_at = ?
                WHERE model_group_id = ?
                """,
                (now, admin_user_id.strip(), reason.strip(), now, normalized_id),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT model_group_id, group_code, display_name, priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_model_groups
                WHERE model_group_id = ?
                """,
                (normalized_id,),
            )
        if row is None:
            raise RuntimeError(f"AI model group was not soft-deleted: {normalized_id}")
        return _row_to_ai_model_group(row)

    def delete_ai_model_group(self, *, model_group_id: str) -> None:
        with self._connect() as conn:
            self._execute(
                conn, "DELETE FROM ai_model_groups WHERE model_group_id = ?", (model_group_id,)
            )
            conn.commit()

    def list_ai_model_groups(self, *, include_deleted: bool = False) -> list[AIModelGroup]:
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT model_group_id, group_code, display_name, priority, enabled, created_at, updated_at,
                       deleted_at, deleted_by_admin_user_id, deleted_reason
                FROM ai_model_groups
                {where}
                ORDER BY deleted_at IS NOT NULL, enabled DESC, priority DESC, display_name
                """,
            ).fetchall()
        return [_row_to_ai_model_group(row) for row in rows]

    def add_ai_model_group_user(
        self, *, model_group_id: str, user_id: str
    ) -> AIModelGroupMembership:
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO ai_model_group_users(model_group_id, user_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(model_group_id, user_id) DO UPDATE SET
                    created_at = excluded.created_at
                """,
                (model_group_id, user_id, now),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT gu.model_group_id, gu.user_id, u.email, u.full_name, gu.created_at
                FROM ai_model_group_users gu
                JOIN users u ON u.user_id = gu.user_id
                WHERE gu.model_group_id = ? AND gu.user_id = ?
                """,
                (model_group_id, user_id),
            )
        if row is None:
            raise RuntimeError(f"AI model group user was not saved: {model_group_id}:{user_id}")
        return _row_to_ai_model_group_membership(row)

    def remove_ai_model_group_user(self, *, model_group_id: str, user_id: str) -> None:
        with self._connect() as conn:
            self._execute(
                conn,
                "DELETE FROM ai_model_group_users WHERE model_group_id = ? AND user_id = ?",
                (model_group_id, user_id),
            )
            conn.commit()

    def list_ai_model_group_users(
        self, *, model_group_id: str | None = None
    ) -> list[AIModelGroupMembership]:
        params: tuple[Any, ...] = ()
        filter_clause = ""
        if model_group_id:
            filter_clause = "WHERE gu.model_group_id = ?"
            params = (model_group_id,)
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT gu.model_group_id, gu.user_id, u.email, u.full_name, gu.created_at
                FROM ai_model_group_users gu
                JOIN users u ON u.user_id = gu.user_id
                {filter_clause}
                ORDER BY gu.model_group_id, u.email
                """,
                params,
            ).fetchall()
        return [_row_to_ai_model_group_membership(row) for row in rows]

    def get_ai_model_user_override(self, *, user_id: str) -> AIModelUserOverride | None:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT override_id, user_id, model_profile_id, enabled,
                       created_by_admin_user_id, updated_by_admin_user_id,
                       disabled_by_admin_user_id, created_reason, updated_reason,
                       disabled_reason, created_at, updated_at, disabled_at
                FROM ai_model_user_overrides
                WHERE user_id = ?
                """,
                (user_id.strip(),),
            )
        return _row_to_ai_model_user_override(row) if row is not None else None

    def upsert_ai_model_user_override(
        self,
        *,
        user_id: str,
        model_profile_id: str,
        admin_user_id: str,
        reason: str,
    ) -> AIModelUserOverride:
        normalized_user_id = user_id.strip()
        normalized_model_profile_id = model_profile_id.strip()
        normalized_admin_user_id = admin_user_id.strip()
        normalized_reason = reason.strip()
        if not normalized_user_id:
            raise ValueError("user_id is required")
        if not normalized_model_profile_id:
            raise ValueError("model_profile_id is required")
        if not normalized_reason:
            raise ValueError("reason is required")
        now = _now_iso()
        with self._connect() as conn:
            target = self._get_ai_model_route_target(conn, normalized_model_profile_id)
            if target is None:
                raise ValueError("model_profile_id must reference an enabled model profile")
            existing = self._fetchone(
                conn,
                "SELECT override_id FROM ai_model_user_overrides WHERE user_id = ?",
                (normalized_user_id,),
            )
            if existing is None:
                override_id = str(uuid.uuid4())
                self._execute(
                    conn,
                    """
                    INSERT INTO ai_model_user_overrides(
                        override_id, user_id, model_profile_id, enabled,
                        created_by_admin_user_id, updated_by_admin_user_id,
                        created_reason, updated_reason, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        override_id,
                        normalized_user_id,
                        normalized_model_profile_id,
                        normalized_admin_user_id,
                        normalized_admin_user_id,
                        normalized_reason,
                        normalized_reason,
                        now,
                        now,
                    ),
                )
            else:
                override_id = str(existing[0])
                self._execute(
                    conn,
                    """
                    UPDATE ai_model_user_overrides
                    SET model_profile_id = ?,
                        enabled = 1,
                        updated_by_admin_user_id = ?,
                        disabled_by_admin_user_id = '',
                        updated_reason = ?,
                        disabled_reason = '',
                        updated_at = ?,
                        disabled_at = NULL
                    WHERE override_id = ?
                    """,
                    (
                        normalized_model_profile_id,
                        normalized_admin_user_id,
                        normalized_reason,
                        now,
                        override_id,
                    ),
                )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT override_id, user_id, model_profile_id, enabled,
                       created_by_admin_user_id, updated_by_admin_user_id,
                       disabled_by_admin_user_id, created_reason, updated_reason,
                       disabled_reason, created_at, updated_at, disabled_at
                FROM ai_model_user_overrides
                WHERE override_id = ?
                """,
                (override_id,),
            )
        if row is None:
            raise RuntimeError(f"AI model user override was not saved: {normalized_user_id}")
        return _row_to_ai_model_user_override(row)

    def disable_ai_model_user_override(
        self,
        *,
        user_id: str,
        admin_user_id: str,
        reason: str,
    ) -> AIModelUserOverride:
        normalized_user_id = user_id.strip()
        normalized_admin_user_id = admin_user_id.strip()
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("reason is required")
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE ai_model_user_overrides
                SET enabled = 0,
                    updated_by_admin_user_id = ?,
                    disabled_by_admin_user_id = ?,
                    updated_reason = ?,
                    disabled_reason = ?,
                    updated_at = ?,
                    disabled_at = ?
                WHERE user_id = ?
                """,
                (
                    normalized_admin_user_id,
                    normalized_admin_user_id,
                    normalized_reason,
                    normalized_reason,
                    now,
                    now,
                    normalized_user_id,
                ),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT override_id, user_id, model_profile_id, enabled,
                       created_by_admin_user_id, updated_by_admin_user_id,
                       disabled_by_admin_user_id, created_reason, updated_reason,
                       disabled_reason, created_at, updated_at, disabled_at
                FROM ai_model_user_overrides
                WHERE user_id = ?
                """,
                (normalized_user_id,),
            )
        if row is None:
            raise KeyError(f"AI model user override for user {normalized_user_id} not found")
        return _row_to_ai_model_user_override(row)

    def list_users_for_admin(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        query: str = "",
    ) -> list[AdminUser]:
        bounded_limit = min(max(limit, 1), 500)
        bounded_offset = max(offset, 0)
        normalized_query = query.strip().lower()
        params: tuple[Any, ...]
        filter_clause = ""
        if normalized_query:
            filter_clause = "WHERE lower(email) LIKE ? OR lower(full_name) LIKE ?"
            like_query = f"%{normalized_query}%"
            params = (like_query, like_query, bounded_limit, bounded_offset)
        else:
            params = (bounded_limit, bounded_offset)
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT user_id, phone_number, email, full_name, role, is_enabled, created_at
                FROM users
                {filter_clause}
                ORDER BY created_at DESC, email
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [_row_to_admin_user(row) for row in rows]

    def count_users_for_admin(self, *, query: str = "") -> int:
        normalized_query = query.strip().lower()
        params: tuple[Any, ...] = ()
        filter_clause = ""
        if normalized_query:
            filter_clause = "WHERE lower(email) LIKE ? OR lower(full_name) LIKE ?"
            like_query = f"%{normalized_query}%"
            params = (like_query, like_query)
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                f"SELECT COUNT(*) FROM users {filter_clause}",
                params,
            )
        return int(row[0]) if row is not None else 0

    def search_case_users_for_admin(self, *, email: str, limit: int = 25) -> list[AdminCaseUser]:
        bounded_limit = min(max(limit, 1), 100)
        normalized_email = email.strip().lower()
        if not normalized_email:
            return []
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT user_id, email, full_name, role, is_enabled, created_at
                FROM users
                WHERE lower(email) LIKE ?
                ORDER BY
                    CASE WHEN lower(email) = ? THEN 0 ELSE 1 END,
                    email
                LIMIT ?
                """,
                (f"%{normalized_email}%", normalized_email, bounded_limit),
            ).fetchall()
        return [_row_to_admin_case_user(row) for row in rows]

    def update_admin_user(
        self,
        *,
        user_id: str,
        role: str,
        is_enabled: bool,
    ) -> AdminUser:
        normalized_role = _normalize_user_role(role)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE users
                SET role = ?, is_enabled = ?
                WHERE user_id = ?
                """,
                (normalized_role, _bool_int(is_enabled), user_id),
            )
            row = self._fetchone(
                conn,
                """
                SELECT user_id, phone_number, email, full_name, role, is_enabled, created_at
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            )
        if row is None:
            raise KeyError(f"User {user_id} not found")
        return _row_to_admin_user(row)

    def record_ai_model_admin_audit_event(
        self,
        *,
        admin_user_id: str,
        admin_email: str,
        action: str,
        entity_type: str,
        entity_id: str,
        old_value_summary: dict[str, Any] | None = None,
        new_value_summary: dict[str, Any] | None = None,
        reason: str = "",
        correlation_id: str = "",
        audit_event_id: str | None = None,
    ) -> AIModelAdminAuditEvent:
        now = _now_iso()
        resolved_id = audit_event_id or str(uuid.uuid4())
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO ai_model_admin_audit_events(
                    audit_event_id, admin_user_id, admin_email, action, entity_type,
                    entity_id, old_value_summary_json, new_value_summary_json,
                    reason, correlation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_id,
                    admin_user_id.strip(),
                    admin_email.strip().lower(),
                    action.strip().lower(),
                    entity_type.strip().lower(),
                    entity_id.strip(),
                    _to_json(old_value_summary or {}),
                    _to_json(new_value_summary or {}),
                    reason.strip(),
                    correlation_id.strip(),
                    now,
                ),
            )
            conn.commit()
            row = self._fetchone(
                conn,
                """
                SELECT audit_event_id, admin_user_id, admin_email, action, entity_type,
                       entity_id, old_value_summary_json, new_value_summary_json,
                       reason, correlation_id, created_at
                FROM ai_model_admin_audit_events
                WHERE audit_event_id = ?
                """,
                (resolved_id,),
            )
        if row is None:
            raise RuntimeError(f"AI model admin audit event was not saved: {resolved_id}")
        return _row_to_ai_model_admin_audit_event(row)

    def list_ai_model_admin_audit_events(self, *, limit: int = 100) -> list[AIModelAdminAuditEvent]:
        bounded_limit = min(max(limit, 1), 500)
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT audit_event_id, admin_user_id, admin_email, action, entity_type,
                       entity_id, old_value_summary_json, new_value_summary_json,
                       reason, correlation_id, created_at
                FROM ai_model_admin_audit_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [_row_to_ai_model_admin_audit_event(row) for row in rows]

    def resolve_ai_model_route(
        self,
        *,
        user_id: str,
        plan_code: str,
        task_type: str,
        prefer_local: bool = False,
        external_acknowledged: bool = False,
    ) -> AIModelRouteSelection:
        normalized_task = _normalize_route_key(task_type, default="default")
        normalized_plan = _normalize_route_key(plan_code, default="free")
        with self._connect() as conn:
            user_override = self._get_enabled_ai_model_user_override_target(
                conn,
                user_id=user_id,
            )
            if user_override is not None:
                override, target = user_override
                provider, profile = target
                route_type = (
                    "user_override_external" if provider.is_external else "user_override_local"
                )
                return AIModelRouteSelection(
                    policy=None,
                    provider=provider,
                    model_profile=profile,
                    route_type=route_type,
                    task_type=normalized_task,
                    plan_code=normalized_plan,
                    requires_external_ack=False,
                    reason=f"Admin per-user model override {override.override_id} selected this model.",
                )
            policy = self._select_ai_task_route_policy(
                conn,
                user_id=user_id,
                plan_code=normalized_plan,
                task_type=normalized_task,
            )
            if policy is None:
                return AIModelRouteSelection(
                    policy=None,
                    provider=None,
                    model_profile=None,
                    route_type="unconfigured",
                    task_type=normalized_task,
                    plan_code=normalized_plan,
                    requires_external_ack=False,
                    reason="No enabled route policy matched this task and plan.",
                )

            local = (
                self._get_ai_model_route_target(conn, policy.preferred_local_model_profile_id)
                if policy.preferred_local_model_profile_id
                else None
            )
            external = (
                self._get_ai_model_route_target(conn, policy.preferred_external_model_profile_id)
                if policy.preferred_external_model_profile_id
                else None
            )

        if prefer_local and local is not None:
            return _route_selection(
                policy=policy,
                target=local,
                route_type="paid_local_override" if normalized_plan != "free" else "free_local",
                task_type=normalized_task,
                plan_code=normalized_plan,
                reason="Local model was requested for this task.",
            )
        if normalized_plan == "free" or not policy.allow_external:
            if local is None:
                return _route_selection_without_target(
                    policy=policy,
                    route_type="local_unavailable",
                    task_type=normalized_task,
                    plan_code=normalized_plan,
                    reason="Route policy requires local model routing but no enabled local model is configured.",
                )
            return _route_selection(
                policy=policy,
                target=local,
                route_type="free_local" if normalized_plan == "free" else "local",
                task_type=normalized_task,
                plan_code=normalized_plan,
                reason="Route policy selected local model routing.",
            )
        if external is None:
            if local is not None and policy.fallback_local_on_error:
                return _route_selection(
                    policy=policy,
                    target=local,
                    route_type="local_fallback",
                    task_type=normalized_task,
                    plan_code=normalized_plan,
                    reason="External routing is allowed but no enabled external model is configured.",
                )
            return _route_selection_without_target(
                policy=policy,
                route_type="external_unavailable",
                task_type=normalized_task,
                plan_code=normalized_plan,
                reason="External routing is allowed but no enabled external model is configured.",
            )

        external_provider, external_profile = external
        if policy.require_external_ack and not external_acknowledged:
            return AIModelRouteSelection(
                policy=policy,
                provider=None,
                model_profile=None,
                route_type="external_ack_required",
                task_type=normalized_task,
                plan_code=normalized_plan,
                requires_external_ack=True,
                reason="External paid model routing requires user acknowledgement before use.",
            )
        if policy.require_eu_data_zone and not external_profile.eu_data_zone_capable:
            if local is not None and policy.fallback_local_on_error:
                return _route_selection(
                    policy=policy,
                    target=local,
                    route_type="local_fallback",
                    task_type=normalized_task,
                    plan_code=normalized_plan,
                    reason="External model is not marked EU data zone capable.",
                )
            return AIModelRouteSelection(
                policy=policy,
                provider=external_provider,
                model_profile=external_profile,
                route_type="blocked_non_eu_external",
                task_type=normalized_task,
                plan_code=normalized_plan,
                requires_external_ack=False,
                reason="External model is not marked EU data zone capable.",
            )
        if (
            policy.max_cost_eur > 0
            and self._ai_model_usage_cost_eur(
                user_id=user_id,
                plan_code=normalized_plan,
                task_type=normalized_task,
            )
            >= policy.max_cost_eur
        ):
            reason = (
                "External model budget cap reached for this route policy; "
                "using configured local fallback."
            )
            if local is not None and policy.fallback_local_on_budget:
                return _route_selection(
                    policy=policy,
                    target=local,
                    route_type="local_budget_fallback",
                    task_type=normalized_task,
                    plan_code=normalized_plan,
                    reason=reason,
                )
            return _route_selection_without_target(
                policy=policy,
                route_type="budget_exhausted",
                task_type=normalized_task,
                plan_code=normalized_plan,
                reason=(
                    "External model budget cap reached for this route policy "
                    "and local budget fallback is disabled or unavailable."
                ),
            )
        return _route_selection(
            policy=policy,
            target=external,
            route_type="external",
            task_type=normalized_task,
            plan_code=normalized_plan,
            reason="Route policy selected external model routing.",
        )

    def _ai_model_usage_cost_eur(
        self,
        *,
        user_id: str,
        plan_code: str,
        task_type: str,
    ) -> float:
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            return 0.0
        with self._connect() as conn:
            row = self._execute(
                conn,
                """
                SELECT COALESCE(SUM(estimated_cost_eur), 0)
                FROM ai_model_usage_ledger
                WHERE user_id = ? AND plan_code = ? AND task_type = ?
                """,
                (
                    normalized_user_id,
                    _normalize_route_key(plan_code, default="free"),
                    _normalize_route_key(task_type, default="default"),
                ),
            ).fetchone()
        return float(row[0] if row is not None and row[0] is not None else 0.0)

    def record_ai_model_usage(
        self,
        *,
        provider: str,
        model: str,
        route_type: str,
        input_tokens: int,
        output_tokens: int,
        case_id: str = "",
        user_id: str = "",
        subscription_id: str = "",
        plan_code: str = "",
        task_type: str = "default",
        model_group_id: str = "",
        cached_input_tokens: int = 0,
        estimated_cost_provider_currency: float = 0.0,
        estimated_cost_eur: float = 0.0,
        provider_currency: str = "USD",
        exchange_rate_used: float = 1.0,
        request_started_at: str | None = None,
        request_completed_at: str | None = None,
        latency_ms: int = 0,
        status: str = "ok",
        fallback_reason: str = "",
        confidentiality_warning_ack_id: str = "",
        session_id: str = "",
        question_id: str = "",
        question_text: str = "",
        question_preview: str = "",
        question_sha256: str = "",
        answer_id: str = "",
        audit_metadata: dict[str, Any] | None = None,
        usage_id: str | None = None,
    ) -> str:
        now = _now_iso()
        resolved_usage_id = usage_id or str(uuid.uuid4())
        total_tokens = max(input_tokens, 0) + max(output_tokens, 0)
        resolved_question_preview = _ai_audit_question_preview(
            question_preview=question_preview,
            question_text=question_text,
        )
        resolved_question_sha256 = question_sha256.strip().lower()
        if not resolved_question_sha256 and question_text.strip():
            resolved_question_sha256 = hashlib.sha256(
                question_text.strip().encode("utf-8")
            ).hexdigest()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO ai_model_usage_ledger(
                    usage_id, user_id, subscription_id, plan_code, case_id, task_type,
                    model_group_id, provider, model, route_type, input_tokens,
                    cached_input_tokens, output_tokens, total_tokens,
                    estimated_cost_provider_currency, estimated_cost_eur, provider_currency,
                    exchange_rate_used, request_started_at, request_completed_at,
                    latency_ms, status, fallback_reason, confidentiality_warning_ack_id,
                    session_id, question_id, question_preview, question_sha256, answer_id,
                    audit_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_usage_id,
                    user_id,
                    subscription_id,
                    _normalize_route_key(plan_code, default=""),
                    case_id,
                    _normalize_route_key(task_type, default="default"),
                    model_group_id,
                    provider.strip().lower(),
                    model.strip(),
                    route_type.strip().lower(),
                    max(input_tokens, 0),
                    max(cached_input_tokens, 0),
                    max(output_tokens, 0),
                    total_tokens,
                    max(estimated_cost_provider_currency, 0.0),
                    max(estimated_cost_eur, 0.0),
                    provider_currency.strip().upper() or "USD",
                    max(exchange_rate_used, 0.0),
                    request_started_at or now,
                    request_completed_at or now,
                    max(latency_ms, 0),
                    status.strip().lower() or "ok",
                    fallback_reason.strip(),
                    confidentiality_warning_ack_id.strip(),
                    session_id.strip(),
                    question_id.strip(),
                    resolved_question_preview,
                    resolved_question_sha256,
                    answer_id.strip(),
                    _to_json(audit_metadata or {}),
                    now,
                ),
            )
            conn.commit()
        return resolved_usage_id

    def summarize_ai_model_usage(
        self,
        *,
        minutes: int = 60,
        case_id: str | None = None,
    ) -> list[AIModelUsageSummary]:
        cutoff = (
            (datetime.now(timezone.utc) - timedelta(minutes=max(minutes, 1)))
            .isoformat()
            .replace("+00:00", "Z")
        )
        params: list[Any] = [cutoff]
        case_filter = ""
        if case_id is not None:
            case_filter = " AND case_id = ?"
            params.append(case_id)
        with self._connect() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT '' AS case_id, '' AS user_id, '' AS subscription_id,
                       plan_code, task_type, provider,
                       model, route_type, status, fallback_reason,
                       SUM(input_tokens), SUM(cached_input_tokens), SUM(output_tokens),
                       SUM(total_tokens), SUM(estimated_cost_eur), COUNT(*)
                FROM ai_model_usage_ledger
                WHERE request_completed_at >= ?{case_filter}
                GROUP BY plan_code, task_type, provider, model, route_type, status,
                         fallback_reason
                ORDER BY SUM(estimated_cost_eur) DESC, SUM(total_tokens) DESC
                """,
                tuple(params),
            ).fetchall()
        return [_row_to_ai_model_usage_summary(row) for row in rows]

    def summarize_top_ai_model_cases(
        self,
        *,
        minutes: int = 60,
        limit: int = 10,
    ) -> list[AIModelTopCaseUsage]:
        cutoff = (
            (datetime.now(timezone.utc) - timedelta(minutes=max(minutes, 1)))
            .isoformat()
            .replace("+00:00", "Z")
        )
        bounded_limit = min(max(limit, 1), 50)
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT case_id, plan_code, 'all' AS provider, 'all' AS model,
                       CASE
                           WHEN route_type IN ('local', 'local_only') OR provider LIKE '%%ollama%%'
                           THEN 'local'
                           WHEN route_type IN ('external', 'external_ack_required')
                           THEN 'paid'
                           ELSE COALESCE(NULLIF(route_type, ''), 'unknown')
                       END AS route_type,
                       SUM(input_tokens), SUM(cached_input_tokens), SUM(output_tokens),
                       SUM(total_tokens), SUM(estimated_cost_eur), COUNT(*)
                FROM ai_model_usage_ledger
                WHERE request_completed_at >= ? AND case_id <> ''
                GROUP BY case_id, plan_code,
                         CASE
                             WHEN route_type IN ('local', 'local_only') OR provider LIKE '%%ollama%%'
                             THEN 'local'
                             WHEN route_type IN ('external', 'external_ack_required')
                             THEN 'paid'
                             ELSE COALESCE(NULLIF(route_type, ''), 'unknown')
                         END
                ORDER BY SUM(total_tokens) DESC, SUM(estimated_cost_eur) DESC
                LIMIT ?
                """,
                (cutoff, bounded_limit),
            ).fetchall()
        return [_row_to_ai_model_top_case_usage(row) for row in rows]

    def list_ai_model_usage_audit(
        self,
        *,
        case_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AIModelUsageAuditEntry]:
        bounded_limit = min(max(limit, 1), 500)
        bounded_offset = max(offset, 0)
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT usage_id, case_id, user_id, subscription_id, plan_code, task_type,
                       model_group_id, provider, model, route_type, input_tokens,
                       cached_input_tokens, output_tokens, total_tokens,
                       estimated_cost_provider_currency, estimated_cost_eur,
                       provider_currency, exchange_rate_used, request_started_at,
                       request_completed_at, latency_ms, status, fallback_reason,
                       confidentiality_warning_ack_id, session_id, question_id,
                       question_preview, question_sha256, answer_id,
                       audit_metadata_json, created_at
                FROM ai_model_usage_ledger
                WHERE case_id = ?
                ORDER BY request_completed_at DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                (case_id, bounded_limit, bounded_offset),
            ).fetchall()
        return [_row_to_ai_model_usage_audit_entry(row) for row in rows]

    def create_user(
        self,
        *,
        email: str,
        password: str,
        phone_number: str | None = None,
        full_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        address: str | None = None,
        city: str | None = None,
        country: str | None = None,
        zip_code: str | None = None,
        tax_number: str | None = None,
        identity_card_number: str | None = None,
        date_of_birth: str | None = None,
        social_security_number: str | None = None,
        data_processing_consent_at: str | None = None,
        data_processing_consent_version: str | None = None,
    ) -> User:
        user_id = str(uuid.uuid4())
        now = _now_iso()
        password_hash = _hash_password(password)
        normalized_email = email.strip().lower()
        normalized_phone = _normalize_phone(phone_number)
        normalized_first = _normalize_optional_text(first_name)
        normalized_last = _normalize_optional_text(last_name)
        normalized_address = _normalize_optional_text(address)
        normalized_city = _normalize_optional_text(city)
        normalized_country = _normalize_optional_text(country)
        normalized_zip_code = _normalize_optional_text(zip_code)
        normalized_tax_number = _normalize_optional_text(tax_number)
        normalized_identity_card_number = _normalize_optional_text(identity_card_number)
        normalized_date_of_birth = _normalize_optional_text(date_of_birth)
        normalized_social_security_number = _normalize_optional_text(social_security_number)
        role = _default_role_for_email(normalized_email)
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
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, password_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    normalized_phone,
                    normalized_email,
                    normalized_first,
                    normalized_last,
                    resolved_full_name,
                    normalized_address,
                    normalized_city,
                    normalized_country,
                    normalized_zip_code,
                    normalized_tax_number,
                    normalized_identity_card_number,
                    normalized_date_of_birth,
                    normalized_social_security_number,
                    data_processing_consent_at,
                    data_processing_consent_version,
                    None,
                    None,
                    role,
                    1,
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
            address=normalized_address,
            city=normalized_city,
            country=normalized_country,
            zip_code=normalized_zip_code,
            tax_number=normalized_tax_number,
            identity_card_number=normalized_identity_card_number,
            date_of_birth=normalized_date_of_birth,
            social_security_number=normalized_social_security_number,
            data_processing_consent_at=data_processing_consent_at,
            data_processing_consent_version=data_processing_consent_version,
            mcp_api_key_hash=None,
            mcp_api_key_expires_at=None,
            created_at=now,
            role=role,
            is_enabled=True,
        )

    def save_registration_code(
        self,
        *,
        email: str,
        code: str,
        expires_in_minutes: int = 30,
    ) -> None:
        normalized_email = email.strip().lower()
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO registration_codes(email, code_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    code_hash = excluded.code_hash,
                    expires_at = excluded.expires_at,
                    created_at = excluded.created_at
                """,
                (
                    normalized_email,
                    _hash_one_time_code(code),
                    (now + timedelta(minutes=max(expires_in_minutes, 1))).isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

    def verify_registration_code(self, *, email: str, code: str) -> bool:
        normalized_email = email.strip().lower()
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT code_hash, expires_at
                FROM registration_codes
                WHERE email = ?
                """,
                (normalized_email,),
            )
            if row is None:
                return False
            stored_hash = str(row[0])
            expires_at = str(row[1])
            if not _is_future_iso_datetime(expires_at):
                self._execute(
                    conn, "DELETE FROM registration_codes WHERE email = ?", (normalized_email,)
                )
                conn.commit()
                return False
            provided_hash = _hash_one_time_code(code)
            if not hmac.compare_digest(stored_hash, provided_hash):
                return False
            self._execute(
                conn, "DELETE FROM registration_codes WHERE email = ?", (normalized_email,)
            )
            conn.commit()
            return True

    def save_mcp_pending_signup(
        self,
        *,
        pending_id: str,
        email: str,
        payload_json: str,
        expires_in_minutes: int = 30,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO mcp_pending_signups(pending_id, email, payload_json, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(pending_id) DO UPDATE SET
                    email = excluded.email,
                    payload_json = excluded.payload_json,
                    expires_at = excluded.expires_at,
                    created_at = excluded.created_at
                """,
                (
                    pending_id,
                    email.strip().lower(),
                    payload_json,
                    (now + timedelta(minutes=max(expires_in_minutes, 1))).isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

    def consume_mcp_pending_signup(self, *, pending_id: str) -> str | None:
        normalized_id = pending_id.strip()
        if not normalized_id:
            return None
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT payload_json, expires_at
                FROM mcp_pending_signups
                WHERE pending_id = ?
                """,
                (normalized_id,),
            )
            if row is None:
                return None
            payload_json = str(row[0])
            expires_at = str(row[1])
            if not _is_future_iso_datetime(expires_at):
                self._execute(
                    conn, "DELETE FROM mcp_pending_signups WHERE pending_id = ?", (normalized_id,)
                )
                conn.commit()
                return None
            self._execute(
                conn, "DELETE FROM mcp_pending_signups WHERE pending_id = ?", (normalized_id,)
            )
            conn.commit()
            return payload_json

    def save_mcp_oauth_authorization_code(
        self,
        *,
        code: str,
        user_id: str,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        resource: str,
        scope: str = "mcp:laws",
        expires_in_minutes: int = 10,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO mcp_oauth_authorization_codes(
                    code, user_id, client_id, redirect_uri, code_challenge, resource, scope, expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code.strip(),
                    user_id,
                    client_id.strip(),
                    redirect_uri.strip(),
                    code_challenge.strip(),
                    resource.strip(),
                    scope.strip() or "mcp:laws",
                    (now + timedelta(minutes=max(expires_in_minutes, 1))).isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

    def consume_mcp_oauth_authorization_code(self, *, code: str) -> dict[str, str] | None:
        normalized_code = code.strip()
        if not normalized_code:
            return None
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT user_id, client_id, redirect_uri, code_challenge, resource, scope, expires_at
                FROM mcp_oauth_authorization_codes
                WHERE code = ?
                """,
                (normalized_code,),
            )
            if row is None:
                return None
            self._execute(
                conn, "DELETE FROM mcp_oauth_authorization_codes WHERE code = ?", (normalized_code,)
            )
            conn.commit()
        if not _is_future_iso_datetime(str(row[6])):
            return None
        return {
            "user_id": str(row[0]),
            "client_id": str(row[1]),
            "redirect_uri": str(row[2]),
            "code_challenge": str(row[3]),
            "resource": str(row[4]),
            "scope": str(row[5]),
        }

    def save_mcp_otp_verification(
        self,
        *,
        user_id: str,
        purpose: str,
        expires_in_hours: int,
    ) -> None:
        normalized_user_id = user_id.strip()
        normalized_purpose = purpose.strip().lower()
        if not normalized_user_id or not normalized_purpose:
            return
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=max(expires_in_hours, 1))
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO mcp_otp_verifications(user_id, purpose, expires_at, verified_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, purpose) DO UPDATE SET
                    expires_at = excluded.expires_at,
                    verified_at = excluded.verified_at
                """,
                (
                    normalized_user_id,
                    normalized_purpose,
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

    def has_valid_mcp_otp_verification(self, *, user_id: str, purpose: str) -> bool:
        normalized_user_id = user_id.strip()
        normalized_purpose = purpose.strip().lower()
        if not normalized_user_id or not normalized_purpose:
            return False
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT expires_at
                FROM mcp_otp_verifications
                WHERE user_id = ? AND purpose = ?
                """,
                (normalized_user_id, normalized_purpose),
            )
            if row is None:
                return False
            expires_at = str(row[0])
            if _is_future_iso_datetime(expires_at):
                return True
            self._execute(
                conn,
                "DELETE FROM mcp_otp_verifications WHERE user_id = ? AND purpose = ?",
                (normalized_user_id, normalized_purpose),
            )
            conn.commit()
            return False

    def save_mfa_verification(self, *, user_id: str, purpose: str, expires_in_hours: int) -> None:
        self.save_mcp_otp_verification(
            user_id=user_id,
            purpose=purpose,
            expires_in_hours=expires_in_hours,
        )

    def has_valid_mfa_verification(self, *, user_id: str, purpose: str) -> bool:
        return self.has_valid_mcp_otp_verification(user_id=user_id, purpose=purpose)

    def get_user_mfa_settings(self, *, user_id: str) -> UserMfaSettings:
        normalized_user_id = user_id.strip()
        now = _now_iso()
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT
                    user_id, totp_secret_protected, pending_totp_secret_protected,
                    totp_enabled_at, created_at, updated_at
                FROM user_mfa_settings
                WHERE user_id = ?
                """,
                (normalized_user_id,),
            )
        if row is None:
            return UserMfaSettings(
                user_id=normalized_user_id,
                totp_enabled=False,
                totp_pending=False,
                totp_secret_protected=None,
                pending_totp_secret_protected=None,
                totp_enabled_at=None,
                updated_at=now,
            )
        return _row_to_user_mfa_settings(row)

    def start_user_totp_enrollment(self, *, user_id: str, protected_secret: str) -> UserMfaSettings:
        normalized_user_id = user_id.strip()
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO user_mfa_settings(
                    user_id, totp_secret_protected, pending_totp_secret_protected,
                    totp_enabled_at, created_at, updated_at
                )
                VALUES (?, NULL, ?, NULL, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    pending_totp_secret_protected = excluded.pending_totp_secret_protected,
                    updated_at = excluded.updated_at
                """,
                (normalized_user_id, protected_secret, now, now),
            )
            conn.commit()
        return self.get_user_mfa_settings(user_id=normalized_user_id)

    def enable_user_totp(self, *, user_id: str) -> UserMfaSettings:
        normalized_user_id = user_id.strip()
        now = _now_iso()
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                "SELECT pending_totp_secret_protected FROM user_mfa_settings WHERE user_id = ?",
                (normalized_user_id,),
            )
            if row is None or row[0] is None:
                raise KeyError(f"Pending TOTP enrollment for user {normalized_user_id} not found")
            self._execute(
                conn,
                """
                UPDATE user_mfa_settings
                SET
                    totp_secret_protected = pending_totp_secret_protected,
                    pending_totp_secret_protected = NULL,
                    totp_enabled_at = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (now, now, normalized_user_id),
            )
            conn.commit()
        return self.get_user_mfa_settings(user_id=normalized_user_id)

    def disable_user_totp(self, *, user_id: str) -> UserMfaSettings:
        normalized_user_id = user_id.strip()
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO user_mfa_settings(
                    user_id, totp_secret_protected, pending_totp_secret_protected,
                    totp_enabled_at, created_at, updated_at
                )
                VALUES (?, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    totp_secret_protected = NULL,
                    pending_totp_secret_protected = NULL,
                    totp_enabled_at = NULL,
                    updated_at = excluded.updated_at
                """,
                (normalized_user_id, now, now),
            )
            conn.commit()
        return self.get_user_mfa_settings(user_id=normalized_user_id)

    def create_mfa_login_challenge(
        self,
        *,
        user_id: str,
        token: str,
        expires_in_minutes: int = 10,
    ) -> None:
        normalized_user_id = user_id.strip()
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO mfa_login_challenges(challenge_token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    _hash_mfa_challenge_token(token),
                    normalized_user_id,
                    (now + timedelta(minutes=max(expires_in_minutes, 1))).isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()

    def consume_mfa_login_challenge(self, *, token: str) -> str | None:
        token_hash = _hash_mfa_challenge_token(token)
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT user_id, expires_at
                FROM mfa_login_challenges
                WHERE challenge_token_hash = ?
                """,
                (token_hash,),
            )
            if row is None:
                return None
            self._execute(
                conn,
                "DELETE FROM mfa_login_challenges WHERE challenge_token_hash = ?",
                (token_hash,),
            )
            conn.commit()
        if not _is_future_iso_datetime(str(row[1])):
            return None
        return str(row[0])

    def issue_device_auth_token(
        self,
        *,
        user_id: str,
        device_id: str,
        expires_in_days: int = 30,
    ) -> str:
        normalized_device = device_id.strip()
        if not normalized_device:
            raise ValueError("device_id is required")
        now = datetime.now(timezone.utc)
        raw_token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO device_auth_tokens(user_id, device_id, token_hash, expires_at, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, device_id) DO UPDATE SET
                    token_hash = excluded.token_hash,
                    expires_at = excluded.expires_at,
                    last_used_at = excluded.last_used_at
                """,
                (
                    user_id,
                    normalized_device,
                    _hash_one_time_code(raw_token),
                    (now + timedelta(days=max(expires_in_days, 1))).isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()
        return raw_token

    def authenticate_device_auth_token(
        self,
        *,
        phone_number: str,
        device_id: str,
        token: str,
    ) -> User | None:
        user = self.find_user_by_phone(phone_number=phone_number)
        if user is None:
            return None
        normalized_device = device_id.strip()
        normalized_token = token.strip()
        if not normalized_device or not normalized_token:
            return None
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT token_hash, expires_at
                FROM device_auth_tokens
                WHERE user_id = ? AND device_id = ?
                """,
                (user.user_id, normalized_device),
            )
            if row is None:
                return None
            token_hash = str(row[0])
            expires_at = str(row[1])
            if not _is_future_iso_datetime(expires_at):
                self._execute(
                    conn,
                    "DELETE FROM device_auth_tokens WHERE user_id = ? AND device_id = ?",
                    (user.user_id, normalized_device),
                )
                conn.commit()
                return None
            if not hmac.compare_digest(token_hash, _hash_one_time_code(normalized_token)):
                return None
            self._execute(
                conn,
                """
                UPDATE device_auth_tokens
                SET last_used_at = ?
                WHERE user_id = ? AND device_id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), user.user_id, normalized_device),
            )
            conn.commit()
        return user

    def authenticate_user_device_auth_token(
        self,
        *,
        user_id: str,
        device_id: str,
        token: str,
    ) -> User | None:
        normalized_user_id = user_id.strip()
        normalized_device = device_id.strip()
        normalized_token = token.strip()
        if not normalized_user_id or not normalized_device or not normalized_token:
            return None
        user = self.find_user_by_id(user_id=normalized_user_id)
        if user is None:
            return None
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT token_hash, expires_at
                FROM device_auth_tokens
                WHERE user_id = ? AND device_id = ?
                """,
                (normalized_user_id, normalized_device),
            )
            if row is None:
                return None
            token_hash = str(row[0])
            expires_at = str(row[1])
            if not _is_future_iso_datetime(expires_at):
                self._execute(
                    conn,
                    "DELETE FROM device_auth_tokens WHERE user_id = ? AND device_id = ?",
                    (normalized_user_id, normalized_device),
                )
                conn.commit()
                return None
            if not hmac.compare_digest(token_hash, _hash_one_time_code(normalized_token)):
                return None
            self._execute(
                conn,
                """
                UPDATE device_auth_tokens
                SET last_used_at = ?
                WHERE user_id = ? AND device_id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), normalized_user_id, normalized_device),
            )
            conn.commit()
        return user

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

    def get_subscription_plan(self, *, plan_code: str) -> SubscriptionPlan:
        normalized_plan = plan_code.strip().lower()
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT plan_code, display_name, subscription_type, price_eur, max_cases, max_documents_per_case, case_ttl_days
                FROM subscription_plans
                WHERE plan_code = ?
                """,
                (normalized_plan,),
            )
        if row is None:
            raise KeyError(f"Subscription plan {normalized_plan or plan_code} not found")
        return _row_to_subscription_plan(row)

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
                SELECT
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at, password_hash
                FROM users
                WHERE email = ?
                """,
                (email.strip().lower(),),
            )
        if row is None:
            return None
        if not _verify_password(password, row[21]):
            return None
        user = _row_to_user(row)
        if not user.is_enabled:
            return None
        return user

    def find_user_by_phone(self, *, phone_number: str) -> User | None:
        normalized_phone = _normalize_phone(phone_number)
        if normalized_phone is None:
            return None
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at
                FROM users
                WHERE phone_number = ?
                """,
                (normalized_phone,),
            )
        if row is None:
            return None
        return _row_to_user(row)

    def find_user_by_email(self, *, email: str) -> User | None:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at
                FROM users
                WHERE email = ?
                """,
                (email.strip().lower(),),
            )
        if row is None:
            return None
        return _row_to_user(row)

    def find_user_by_id(self, *, user_id: str) -> User | None:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at
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
                SELECT
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at
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
        address: str | None = None,
        city: str | None = None,
        country: str | None = None,
        zip_code: str | None = None,
        tax_number: str | None = None,
        identity_card_number: str | None = None,
        date_of_birth: str | None = None,
        social_security_number: str | None = None,
        password: str | None = None,
    ) -> User:
        normalized_phone = _normalize_phone(phone_number)
        normalized_first = _normalize_optional_text(first_name)
        normalized_last = _normalize_optional_text(last_name)
        normalized_address = _normalize_optional_text(address)
        normalized_city = _normalize_optional_text(city)
        normalized_country = _normalize_optional_text(country)
        normalized_zip_code = _normalize_optional_text(zip_code)
        normalized_tax_number = _normalize_optional_text(tax_number)
        normalized_identity_card_number = _normalize_optional_text(identity_card_number)
        normalized_date_of_birth = _normalize_optional_text(date_of_birth)
        normalized_social_security_number = _normalize_optional_text(social_security_number)
        normalized_password = _normalize_optional_text(password)
        with self._connect() as conn:
            current = self._fetchone(
                conn,
                """
                SELECT
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at
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
                    SET
                        phone_number = ?, first_name = ?, last_name = ?, full_name = ?,
                        address = ?, city = ?, country = ?, zip_code = ?, tax_number = ?,
                        identity_card_number = ?, date_of_birth = ?, social_security_number = ?,
                        password_hash = ?
                    WHERE user_id = ?
                    """,
                    (
                        normalized_phone,
                        normalized_first,
                        normalized_last,
                        resolved_full_name,
                        normalized_address,
                        normalized_city,
                        normalized_country,
                        normalized_zip_code,
                        normalized_tax_number,
                        normalized_identity_card_number,
                        normalized_date_of_birth,
                        normalized_social_security_number,
                        _hash_password(normalized_password),
                        user_id,
                    ),
                )
            else:
                self._execute(
                    conn,
                    """
                    UPDATE users
                    SET
                        phone_number = ?, first_name = ?, last_name = ?, full_name = ?,
                        address = ?, city = ?, country = ?, zip_code = ?, tax_number = ?,
                        identity_card_number = ?, date_of_birth = ?, social_security_number = ?
                    WHERE user_id = ?
                    """,
                    (
                        normalized_phone,
                        normalized_first,
                        normalized_last,
                        resolved_full_name,
                        normalized_address,
                        normalized_city,
                        normalized_country,
                        normalized_zip_code,
                        normalized_tax_number,
                        normalized_identity_card_number,
                        normalized_date_of_birth,
                        normalized_social_security_number,
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
            address=normalized_address,
            city=normalized_city,
            country=normalized_country,
            zip_code=normalized_zip_code,
            tax_number=normalized_tax_number,
            identity_card_number=normalized_identity_card_number,
            date_of_birth=normalized_date_of_birth,
            social_security_number=normalized_social_security_number,
            data_processing_consent_at=current_user.data_processing_consent_at,
            data_processing_consent_version=current_user.data_processing_consent_version,
            mcp_api_key_hash=current_user.mcp_api_key_hash,
            mcp_api_key_expires_at=current_user.mcp_api_key_expires_at,
            created_at=current_user.created_at,
            role=current_user.role,
            is_enabled=current_user.is_enabled,
        )

    def update_user_email(self, *, user_id: str, email: str) -> User:
        normalized_email = email.strip().lower()
        with self._connect() as conn:
            current = self._fetchone(
                conn,
                """
                SELECT
                    user_id, phone_number, email, first_name, last_name, full_name,
                    address, city, country, zip_code, tax_number, identity_card_number,
                    date_of_birth, social_security_number,
                    data_processing_consent_at, data_processing_consent_version,
                    mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at
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
                first_name=current_user.first_name,
                last_name=current_user.last_name,
                phone_number=current_user.phone_number,
                email=normalized_email,
            )
            self._execute(
                conn,
                """
                UPDATE users
                SET email = ?, full_name = ?
                WHERE user_id = ?
                """,
                (normalized_email, resolved_full_name, user_id),
            )
        return User(
            user_id=user_id,
            phone_number=current_user.phone_number,
            email=normalized_email,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            full_name=resolved_full_name,
            address=current_user.address,
            city=current_user.city,
            country=current_user.country,
            zip_code=current_user.zip_code,
            tax_number=current_user.tax_number,
            identity_card_number=current_user.identity_card_number,
            date_of_birth=current_user.date_of_birth,
            social_security_number=current_user.social_security_number,
            data_processing_consent_at=current_user.data_processing_consent_at,
            data_processing_consent_version=current_user.data_processing_consent_version,
            mcp_api_key_hash=current_user.mcp_api_key_hash,
            mcp_api_key_expires_at=current_user.mcp_api_key_expires_at,
            created_at=current_user.created_at,
        )

    def set_user_mcp_api_key(self, *, user_id: str, api_key: str, expires_at: str) -> User:
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE users
                SET mcp_api_key_hash = ?, mcp_api_key_expires_at = ?
                WHERE user_id = ?
                """,
                (_hash_password(api_key), expires_at, user_id),
            )
        return self.get_user(user_id=user_id)

    def clear_user_mcp_api_key(self, *, user_id: str) -> User:
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE users
                SET mcp_api_key_hash = NULL, mcp_api_key_expires_at = NULL
                WHERE user_id = ?
                """,
                (user_id,),
            )
        return self.get_user(user_id=user_id)

    def find_user_by_mcp_api_key(self, *, api_key: str) -> User | None:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT user_id, phone_number, email, first_name, last_name, full_name,
                       address, city, country, zip_code, tax_number, identity_card_number,
                       date_of_birth, social_security_number,
                       data_processing_consent_at, data_processing_consent_version,
                       mcp_api_key_hash, mcp_api_key_expires_at, role, is_enabled, created_at
                FROM users
                WHERE mcp_api_key_hash IS NOT NULL
                """,
            ).fetchall()
        for row in rows:
            if row[16] and _verify_password(api_key, str(row[16])):
                expires_at = str(row[17]) if row[17] is not None else None
                if expires_at and expires_at > _now_iso():
                    user = _row_to_user(row)
                    if user.is_enabled:
                        return user
        return None

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

    def upsert_case_catalog_selection(
        self,
        *,
        selection_scope: str,
        entity_id: str,
        case_id: str = "",
        session_id: str = "",
        case_type_id: str = "",
        case_type_key: str = "",
        case_type_name: str = "",
        prompt_ids: list[str] | tuple[str, ...] = (),
        template_ids: list[str] | tuple[str, ...] = (),
        template_keys: list[str] | tuple[str, ...] = (),
        status: str,
        confidence_score: float = 0.0,
        confidence_gap: float = 0.0,
        source: str = "",
        first_message_preview: str = "",
        first_message_sha256: str = "",
        clarification_question: str = "",
    ) -> CaseCatalogSelection:
        normalized_scope = selection_scope.strip().lower()
        normalized_entity_id = entity_id.strip()
        normalized_case_id = case_id.strip()
        if normalized_scope not in {"case", "session"}:
            raise ValueError("selection_scope must be 'case' or 'session'")
        if not normalized_entity_id:
            raise ValueError("entity_id is required")
        now = _now_iso()
        selection_id = str(uuid.uuid4())
        with self._connect() as conn:
            existing = self._fetchone(
                conn,
                """
                SELECT selection_id, created_at
                FROM case_catalog_selections
                WHERE selection_scope = ? AND entity_id = ?
                """,
                (normalized_scope, normalized_entity_id),
            )
            if existing is not None:
                selection_id = str(existing[0])
                created_at = str(existing[1])
            else:
                created_at = now
            self._execute(
                conn,
                """
                INSERT INTO case_catalog_selections(
                    selection_id, selection_scope, entity_id, case_id, session_id,
                    case_type_id, case_type_key, case_type_name, prompt_ids_json, template_ids_json,
                    template_keys_json, status, confidence_score, confidence_gap, source,
                    first_message_preview, first_message_sha256, clarification_question, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(selection_scope, entity_id) DO UPDATE SET
                    case_id = excluded.case_id,
                    session_id = excluded.session_id,
                    case_type_id = excluded.case_type_id,
                    case_type_key = excluded.case_type_key,
                    case_type_name = excluded.case_type_name,
                    prompt_ids_json = excluded.prompt_ids_json,
                    template_ids_json = excluded.template_ids_json,
                    template_keys_json = excluded.template_keys_json,
                    status = excluded.status,
                    confidence_score = excluded.confidence_score,
                    confidence_gap = excluded.confidence_gap,
                    source = excluded.source,
                    first_message_preview = excluded.first_message_preview,
                    first_message_sha256 = excluded.first_message_sha256,
                    clarification_question = excluded.clarification_question,
                    updated_at = excluded.updated_at
                """,
                (
                    selection_id,
                    normalized_scope,
                    normalized_entity_id,
                    normalized_case_id or None,
                    session_id.strip(),
                    case_type_id.strip(),
                    case_type_key.strip(),
                    case_type_name.strip(),
                    json.dumps(list(prompt_ids), ensure_ascii=True),
                    json.dumps(list(template_ids), ensure_ascii=True),
                    json.dumps(list(template_keys), ensure_ascii=True),
                    status.strip(),
                    float(confidence_score),
                    float(confidence_gap),
                    source.strip(),
                    _ai_audit_question_preview(
                        question_preview=first_message_preview,
                        question_text=first_message_preview,
                        max_chars=500,
                    ),
                    first_message_sha256.strip(),
                    clarification_question.strip(),
                    created_at,
                    now,
                ),
            )
        return self.get_case_catalog_selection(
            selection_scope=normalized_scope,
            entity_id=normalized_entity_id,
        )

    def get_case_catalog_selection(
        self,
        *,
        selection_scope: str,
        entity_id: str,
    ) -> CaseCatalogSelection | None:
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT selection_id, selection_scope, entity_id, case_id, session_id,
                       case_type_id, case_type_key, case_type_name, prompt_ids_json, template_ids_json,
                       template_keys_json, status, confidence_score, confidence_gap, source,
                       first_message_preview, first_message_sha256, clarification_question, created_at, updated_at
                FROM case_catalog_selections
                WHERE selection_scope = ? AND entity_id = ?
                """,
                (selection_scope.strip().lower(), entity_id.strip()),
            )
        return _row_to_case_catalog_selection(row) if row is not None else None

    def list_case_catalog_selections(
        self,
        *,
        case_id: str = "",
        session_id: str = "",
    ) -> list[CaseCatalogSelection]:
        clauses: list[str] = []
        params: list[object] = []
        if case_id.strip():
            clauses.append("case_id = ?")
            params.append(case_id.strip())
        if session_id.strip():
            clauses.append("session_id = ?")
            params.append(session_id.strip())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT selection_id, selection_scope, entity_id, case_id, session_id,
                   case_type_id, case_type_key, case_type_name, prompt_ids_json, template_ids_json,
                   template_keys_json, status, confidence_score, confidence_gap, source,
                   first_message_preview, first_message_sha256, clarification_question, created_at, updated_at
            FROM case_catalog_selections
            {where_sql}
            ORDER BY updated_at DESC
        """
        with self._connect() as conn:
            rows = self._execute(conn, query, tuple(params)).fetchall()
        return [_row_to_case_catalog_selection(row) for row in rows]

    def record_case_catalog_event(
        self,
        *,
        case_id: str = "",
        session_id: str = "",
        event_type: str,
        status: str,
        severity: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> CaseCatalogEvent:
        now = _now_iso()
        event_id = str(uuid.uuid4())
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO case_catalog_events(
                    event_id, case_id, session_id, event_type, status, severity, summary, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    case_id.strip() or None,
                    session_id.strip(),
                    event_type.strip(),
                    status.strip(),
                    severity.strip(),
                    summary.strip(),
                    _to_json(details or {}),
                    now,
                ),
            )
        return self.list_case_catalog_events(
            case_id=case_id,
            session_id=session_id,
            limit=1,
            offset=0,
        )[0]

    def list_case_catalog_events(
        self,
        *,
        case_id: str = "",
        session_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[CaseCatalogEvent]:
        clauses: list[str] = []
        params: list[object] = []
        if case_id.strip():
            clauses.append("case_id = ?")
            params.append(case_id.strip())
        if session_id.strip():
            clauses.append("session_id = ?")
            params.append(session_id.strip())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT event_id, case_id, session_id, event_type, status, severity, summary, details_json, created_at
            FROM case_catalog_events
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend((max(limit, 0), max(offset, 0)))
        with self._connect() as conn:
            rows = self._execute(conn, query, tuple(params)).fetchall()
        return [_row_to_case_catalog_event(row) for row in rows]

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

    @staticmethod
    def unlimited_access_email_allowlist() -> set[str]:
        raw_value = os.getenv("JURISDIGTA_UNLIMITED_ACCESS_EMAILS")
        if raw_value is None:
            return set(DEFAULT_UNLIMITED_ACCESS_EMAILS)
        normalized = raw_value.strip()
        if normalized.lower() == "unknown-variable":
            return set(DEFAULT_UNLIMITED_ACCESS_EMAILS)
        if not normalized:
            return set()
        return {
            chunk.strip().lower()
            for chunk in normalized.replace(";", ",").split(",")
            if chunk.strip()
        }

    def has_unlimited_access(self, *, user_id: str) -> bool:
        user = self.find_user_by_id(user_id=user_id)
        if user is None:
            return False
        if user.role == USER_ROLE_ADMIN and user.is_enabled:
            return True
        return user.email.strip().lower() in self.unlimited_access_email_allowlist()

    def can_select_assistant_model(self, *, user_id: str) -> bool:
        return self.has_unlimited_access(user_id=user_id)

    def can_select_assistant_model_by_email(self, *, email: str) -> bool:
        user = self.find_user_by_email(email=email)
        if user is None:
            return False
        return self.can_select_assistant_model(user_id=user.user_id)

    def resolve_selected_ai_model_route(
        self,
        *,
        user_id: str,
        user_email: str = "",
        plan_code: str,
        task_type: str,
        model_profile_id: str,
    ) -> AIModelRouteSelection:
        normalized_user_id = user_id.strip()
        normalized_user_email = user_email.strip().lower()
        normalized_profile_id = model_profile_id.strip()
        normalized_task = _normalize_route_key(task_type, default="default")
        normalized_plan = _normalize_route_key(plan_code, default="free")
        if not normalized_profile_id:
            return AIModelRouteSelection(
                policy=None,
                provider=None,
                model_profile=None,
                route_type="selected_profile_missing",
                task_type=normalized_task,
                plan_code=normalized_plan,
                requires_external_ack=False,
                reason="Selected model profile id is required.",
            )
        can_select = False
        if normalized_user_id:
            can_select = self.can_select_assistant_model(user_id=normalized_user_id)
        if not can_select and normalized_user_email:
            can_select = self.can_select_assistant_model_by_email(email=normalized_user_email)
        if not can_select:
            return AIModelRouteSelection(
                policy=None,
                provider=None,
                model_profile=None,
                route_type="selected_profile_forbidden",
                task_type=normalized_task,
                plan_code=normalized_plan,
                requires_external_ack=False,
                reason="User is not allowed to select assistant model profiles.",
            )
        with self._connect() as conn:
            target = self._get_ai_model_route_target(conn, normalized_profile_id)
        if target is None:
            return AIModelRouteSelection(
                policy=None,
                provider=None,
                model_profile=None,
                route_type="selected_profile_unavailable",
                task_type=normalized_task,
                plan_code=normalized_plan,
                requires_external_ack=False,
                reason="Selected model profile is not enabled or does not exist.",
            )
        provider, _profile = target
        return _route_selection(
            policy=None,
            target=target,
            route_type="user_selected_external" if provider.is_external else "user_selected_local",
            task_type=normalized_task,
            plan_code=normalized_plan,
            reason="User selected this assistant model profile for the current workflow.",
        )

    def get_case_limit(self, *, user_id: str) -> int:
        return self.get_effective_subscription_plan(user_id=user_id).max_cases

    def get_case_write_block_detail(
        self, *, case_id: str, user_id: str
    ) -> CaseWriteBlockReason | None:
        case = self.get_case(case_id=case_id)
        if case.user_id != user_id or case.status == "deleted":
            raise KeyError(f"Case {case_id} not found")
        plan = self.get_effective_subscription_plan(user_id=user_id)
        if plan.case_ttl_days is None:
            return None
        created_at = datetime.fromisoformat(case.created_at.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        expires_at = created_at + timedelta(days=plan.case_ttl_days)
        if datetime.now(timezone.utc) >= expires_at:
            message = (
                f"Case is read-only because the {plan.display_name} plan allows edits "
                f"for {plan.case_ttl_days} day(s) after creation."
            )
            return CaseWriteBlockReason(
                code=CASE_WRITE_WINDOW_EXPIRED_CODE,
                message=message,
                plan_display_name=plan.display_name,
                ttl_days=plan.case_ttl_days,
            )
        return None

    def get_case_write_block_reason(self, *, case_id: str, user_id: str) -> str | None:
        block = self.get_case_write_block_detail(case_id=case_id, user_id=user_id)
        return block.message if block is not None else None

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

    def soft_delete_case_for_admin(self, *, case_id: str, user_id: str) -> Case:
        before = self.get_case(case_id=case_id)
        if before.user_id != user_id:
            raise KeyError(f"Case {case_id} not found for user {user_id}")
        if before.status == "deleted":
            return before
        self.soft_delete_case(case_id=case_id, user_id=user_id)
        return self.get_case(case_id=case_id)

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

    def delete_case_document(
        self,
        *,
        case_id: str,
        doc_id: str,
        actor_user_id: str,
        correlation_id: str,
    ) -> CaseDocumentDeletionEvent:
        """Permanently erase one case document while retaining a minimal audit tombstone."""

        case = self.get_case(case_id=case_id)
        if case.user_id != actor_user_id or case.status == "deleted":
            raise KeyError(f"Document {doc_id} not found for case {case_id}")
        document = self.get_case_document(case_id=case_id, doc_id=doc_id)
        event_id = str(uuid.uuid4())
        communication_id = str(uuid.uuid4())
        deleted_at = _now_iso()
        storage_path = self._resolve_storage_path(document.storage_uri)
        staged_path = storage_path.with_name(f"{storage_path.name}.deleting-{event_id}")
        payload_staged = False

        if storage_path.exists():
            storage_path.replace(staged_path)
            payload_staged = True

        try:
            with self._connect() as conn:
                owned = self._fetchone(
                    conn,
                    """
                    SELECT d.doc_id
                    FROM case_documents d
                    JOIN cases c ON c.case_id = d.case_id
                    WHERE d.case_id = ? AND d.doc_id = ?
                      AND c.user_id = ? AND c.status <> 'deleted'
                    """,
                    (case_id, doc_id, actor_user_id),
                )
                if owned is None:
                    raise KeyError(f"Document {doc_id} not found for case {case_id}")

                share_rows = self._execute(
                    conn,
                    "SELECT share_id FROM document_shares WHERE case_id = ? AND doc_id = ?",
                    (case_id, doc_id),
                ).fetchall()
                share_ids = [str(row[0]) for row in share_rows]
                if share_ids:
                    placeholders = ", ".join("?" for _ in share_ids)
                    self._execute(
                        conn,
                        f"DELETE FROM document_share_audit_events WHERE share_id IN ({placeholders})",
                        tuple(share_ids),
                    )
                self._execute(
                    conn,
                    "DELETE FROM document_shares WHERE case_id = ? AND doc_id = ?",
                    (case_id, doc_id),
                )
                self._execute(
                    conn,
                    "DELETE FROM case_document_chunks WHERE case_id = ? AND doc_id = ?",
                    (case_id, doc_id),
                )
                self._execute(
                    conn,
                    "DELETE FROM case_document_contents WHERE case_id = ? AND doc_id = ?",
                    (case_id, doc_id),
                )
                result = self._execute(
                    conn,
                    "DELETE FROM case_documents WHERE case_id = ? AND doc_id = ?",
                    (case_id, doc_id),
                )
                if result.rowcount == 0:
                    raise KeyError(f"Document {doc_id} not found for case {case_id}")

                self._execute(
                    conn,
                    """
                    INSERT INTO case_communications(
                        communication_id, case_id, channel, transcript_uri, summary, created_at
                    ) VALUES (?, ?, 'system', NULL, ?, ?)
                    """,
                    (
                        communication_id,
                        case_id,
                        f"SYSTEM: Document deleted at {deleted_at}.",
                        deleted_at,
                    ),
                )
                self._execute(
                    conn,
                    """
                    INSERT INTO case_document_deletion_events(
                        event_id, case_id, doc_id, document_kind, actor_user_id,
                        correlation_id, outcome, deleted_at, communication_id
                    ) VALUES (?, ?, ?, ?, ?, ?, 'deleted', ?, ?)
                    """,
                    (
                        event_id,
                        case_id,
                        doc_id,
                        document.kind,
                        actor_user_id,
                        correlation_id,
                        deleted_at,
                        communication_id,
                    ),
                )
                self._execute(
                    conn,
                    "UPDATE cases SET updated_at = ? WHERE case_id = ?",
                    (deleted_at, case_id),
                )
                if payload_staged:
                    staged_path.unlink()
        except Exception:
            if payload_staged and staged_path.exists() and not storage_path.exists():
                staged_path.replace(storage_path)
            raise

        return CaseDocumentDeletionEvent(
            event_id=event_id,
            case_id=case_id,
            doc_id=doc_id,
            document_kind=document.kind,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            outcome="deleted",
            deleted_at=deleted_at,
            communication_id=communication_id,
        )

    def list_case_document_deletion_events(
        self, *, case_id: str
    ) -> list[CaseDocumentDeletionEvent]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT event_id, case_id, doc_id, document_kind, actor_user_id,
                       correlation_id, outcome, deleted_at, communication_id
                FROM case_document_deletion_events
                WHERE case_id = ?
                ORDER BY deleted_at DESC
                """,
                (case_id,),
            ).fetchall()
        return [
            CaseDocumentDeletionEvent(
                event_id=str(row[0]),
                case_id=str(row[1]),
                doc_id=str(row[2]),
                document_kind=str(row[3]),
                actor_user_id=str(row[4]),
                correlation_id=str(row[5]),
                outcome=str(row[6]),
                deleted_at=str(row[7]),
                communication_id=str(row[8]),
            )
            for row in rows
        ]

    def create_document_share(
        self,
        *,
        share_id: str,
        token_hash: str,
        case_id: str,
        doc_id: str,
        sender_user_id: str,
        recipient_email: str,
        locale: str,
        expires_at: str,
    ) -> DocumentShare:
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO document_shares(
                    share_id, token_hash, case_id, doc_id, sender_user_id,
                    recipient_email_protected, locale, status, expires_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    share_id,
                    token_hash,
                    case_id,
                    doc_id,
                    sender_user_id,
                    _protect_document_share_email(recipient_email.strip().lower()),
                    locale,
                    expires_at,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get_document_share_by_id(share_id=share_id)

    def get_document_share_by_id(self, *, share_id: str) -> DocumentShare:
        return self._get_document_share("share_id", share_id)

    def get_document_share_by_token_hash(self, *, token_hash: str) -> DocumentShare:
        return self._get_document_share("token_hash", token_hash)

    def get_document_share_by_session_hash(self, *, session_token_hash: str) -> DocumentShare:
        return self._get_document_share("session_token_hash", session_token_hash)

    def _get_document_share(self, column: str, value: str) -> DocumentShare:
        if column not in {"share_id", "token_hash", "session_token_hash"}:
            raise ValueError("Unsupported document share lookup")
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                f"""
                SELECT share_id, token_hash, case_id, doc_id, sender_user_id,
                       recipient_email_protected, locale, status, expires_at,
                       code_hash, code_expires_at, code_attempts, last_code_sent_at,
                       session_token_hash, session_expires_at, last_accessed_at,
                       created_at, updated_at
                FROM document_shares
                WHERE {column} = ?
                """,
                (value,),
            )
        if row is None:
            raise KeyError("Document share not found")
        recipient = _reveal_document_share_email(str(row[5]))
        if recipient is None:
            raise ValueError("Document share recipient cannot be revealed")
        return DocumentShare(
            share_id=str(row[0]),
            token_hash=str(row[1]),
            case_id=str(row[2]),
            doc_id=str(row[3]),
            sender_user_id=str(row[4]),
            recipient_email=recipient,
            locale=str(row[6]),
            status=str(row[7]),
            expires_at=str(row[8]),
            code_hash=str(row[9]),
            code_expires_at=str(row[10]) if row[10] else None,
            code_attempts=int(row[11]),
            last_code_sent_at=str(row[12]) if row[12] else None,
            session_token_hash=str(row[13]),
            session_expires_at=str(row[14]) if row[14] else None,
            last_accessed_at=str(row[15]) if row[15] else None,
            created_at=str(row[16]),
            updated_at=str(row[17]),
        )

    def set_document_share_code(
        self, *, share_id: str, code_hash: str, code_expires_at: str, sent_at: str
    ) -> None:
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE document_shares
                SET code_hash = ?, code_expires_at = ?, code_attempts = 0,
                    last_code_sent_at = ?, updated_at = ?
                WHERE share_id = ? AND status = 'active'
                """,
                (code_hash, code_expires_at, sent_at, sent_at, share_id),
            )
            conn.commit()

    def increment_document_share_code_attempts(self, *, share_id: str) -> int:
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                "UPDATE document_shares SET code_attempts = code_attempts + 1, updated_at = ? WHERE share_id = ?",
                (now, share_id),
            )
            row = self._fetchone(
                conn, "SELECT code_attempts FROM document_shares WHERE share_id = ?", (share_id,)
            )
            conn.commit()
        return int(row[0]) if row else 0

    def activate_document_share_session(
        self, *, share_id: str, session_token_hash: str, session_expires_at: str
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE document_shares
                SET code_hash = '', code_expires_at = NULL, code_attempts = 0,
                    session_token_hash = ?, session_expires_at = ?, last_accessed_at = ?, updated_at = ?
                WHERE share_id = ? AND status = 'active'
                """,
                (session_token_hash, session_expires_at, now, now, share_id),
            )
            conn.commit()

    def touch_document_share_session(self, *, share_id: str, session_expires_at: str) -> None:
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE document_shares
                SET last_accessed_at = ?, session_expires_at = ?, updated_at = ?
                WHERE share_id = ? AND status = 'active'
                """,
                (now, session_expires_at, now, share_id),
            )
            conn.commit()

    def revoke_document_share(self, *, share_id: str, sender_user_id: str) -> bool:
        now = _now_iso()
        with self._connect() as conn:
            result = self._execute(
                conn,
                """
                UPDATE document_shares
                SET status = 'revoked', code_hash = '', code_expires_at = NULL,
                    session_token_hash = '', session_expires_at = NULL, updated_at = ?
                WHERE share_id = ? AND sender_user_id = ? AND status = 'active'
                """,
                (now, share_id, sender_user_id),
            )
            conn.commit()
        return result.rowcount > 0

    def expire_document_share(self, *, share_id: str) -> None:
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                UPDATE document_shares
                SET status = 'expired', token_hash = share_id,
                    recipient_email_protected = '', code_hash = '', code_expires_at = NULL,
                    session_token_hash = '', session_expires_at = NULL, updated_at = ?
                WHERE share_id = ? AND status = 'active'
                """,
                (now, share_id),
            )
            conn.commit()

    def record_document_share_audit(self, *, share_id: str, action: str, outcome: str = "") -> None:
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO document_share_audit_events(audit_event_id, share_id, action, outcome, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), share_id, action, outcome, _now_iso()),
            )
            conn.commit()

    def list_case_communications(
        self, *, case_id: str, limit: int | None = None, offset: int = 0
    ) -> list[CaseCommunication]:
        query = """
            SELECT communication_id, case_id, channel, transcript_uri, summary, created_at,
                   presentation_json
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
                SELECT communication_id, case_id, channel, transcript_uri, summary, created_at,
                       presentation_json
                FROM case_communications
                WHERE case_id = ? AND communication_id = ?
                """,
                (case_id, communication_id),
            )
        if row is None:
            raise KeyError(f"Communication {communication_id} not found for case {case_id}")
        return _row_to_case_communication(row)

    def add_case_citation(
        self,
        *,
        case_id: str,
        question_message_id: str | None,
        answer_message_id: str | None,
        source_type: str,
        title: str,
        source_id: str | None = None,
        source_url: str | None = None,
        citation_label: str | None = None,
        law_number: str | None = None,
        section: str | None = None,
        effective_from: str | None = None,
        court: str | None = None,
        ecli: str | None = None,
        file_number: str | None = None,
        decision_date: str | None = None,
        snippet: str | None = None,
        retrieval_tool: str | None = None,
        relevance_score: float | None = None,
    ) -> str:
        citation_id = str(uuid.uuid4())
        now = _now_iso()
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO case_citations(
                    citation_id, case_id, question_message_id, answer_message_id,
                    source_type, source_id, source_url, title, citation_label,
                    law_number, section, effective_from, court, ecli, file_number,
                    decision_date, snippet, retrieval_tool, relevance_score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    citation_id,
                    case_id,
                    question_message_id,
                    answer_message_id,
                    source_type,
                    source_id,
                    source_url,
                    title,
                    citation_label,
                    law_number,
                    section,
                    effective_from,
                    court,
                    ecli,
                    file_number,
                    decision_date,
                    snippet,
                    retrieval_tool,
                    relevance_score,
                    now,
                ),
            )
            self._execute(
                conn,
                "UPDATE cases SET updated_at = ? WHERE case_id = ?",
                (now, case_id),
            )
        return citation_id

    def list_case_citations(
        self,
        *,
        case_id: str,
        answer_message_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CaseCitation]:
        query = """
            SELECT citation_id, case_id, question_message_id, answer_message_id,
                   source_type, source_id, source_url, title, citation_label,
                   law_number, section, effective_from, court, ecli, file_number,
                   decision_date, snippet, retrieval_tool, relevance_score, created_at
            FROM case_citations
            WHERE case_id = ?
        """
        params: tuple[Any, ...]
        if answer_message_id is None:
            params = (case_id,)
        else:
            query += " AND answer_message_id = ?"
            params = (case_id, answer_message_id)
        query += " ORDER BY created_at ASC, citation_id ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params = (*params, limit, max(offset, 0))
        with self._connect() as conn:
            rows = self._execute(conn, query, params).fetchall()
        return [_row_to_case_citation(row) for row in rows]

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
        presentation: dict[str, Any] | None = None,
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
            presentation=presentation,
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

    def add_case_session_history_document(
        self,
        *,
        case_id: str,
        session_id: str,
        content: str,
        uploaded_by_user_id: str | None = None,
    ) -> str:
        filename = f"session-{session_id}.txt"
        payload = content.encode("utf-8")
        with self._connect() as conn:
            existing = self._fetchone(
                conn,
                """
                SELECT doc_id, storage_uri FROM case_documents
                WHERE case_id = ? AND kind = 'session_history' AND original_filename = ?
                LIMIT 1
                """,
                (case_id, filename),
            )
            if existing is not None:
                doc_id = str(existing[0])
                storage_uri = str(existing[1])
                self._replace_stored_payload(storage_uri=storage_uri, payload=payload)
                self._execute(
                    conn,
                    """
                    UPDATE case_documents
                    SET uploaded_by_user_id = ?, processing_status = 'uploaded',
                        processing_error = NULL, processed_at = NULL
                    WHERE doc_id = ?
                    """,
                    (uploaded_by_user_id, doc_id),
                )
                self._execute(
                    conn,
                    "UPDATE cases SET updated_at = ? WHERE case_id = ?",
                    (_now_iso(), case_id),
                )
                conn.commit()
                return doc_id
            row = self._fetchone(
                conn,
                """
                SELECT COALESCE(MAX(version), 0)
                FROM case_documents
                WHERE case_id = ? AND kind = 'session_history'
                """,
                (case_id,),
            )
        next_version = int(row[0]) + 1 if row else 1
        return self.add_case_document(
            case_id=case_id,
            kind="session_history",
            version=next_version,
            original_filename=filename,
            payload=payload,
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
        presentation: dict[str, Any] | None = None,
    ) -> str:
        communication_id = str(uuid.uuid4())
        transcript_uri: str | None = None
        if transcript_payload is not None:
            relative_uri = Path(case_id) / "communications" / f"{communication_id}.{extension}"
            transcript_uri = self._store_payload(
                relative_uri=relative_uri, payload=transcript_payload
            )
        with self._connect() as conn:
            self._execute(
                conn,
                """
                INSERT INTO case_communications(
                    communication_id, case_id, channel, transcript_uri, summary, created_at,
                    presentation_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    communication_id,
                    case_id,
                    channel,
                    transcript_uri,
                    summary,
                    _now_iso(),
                    json.dumps(presentation or {}, ensure_ascii=False, sort_keys=True),
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

    def get_effective_user_subscription(self, *, user_id: str) -> UserSubscription | None:
        now = _now_iso()
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT subscription_id, user_id, plan_code, status, starts_at, ends_at,
                       case_ids_json, created_at, updated_at
                FROM user_subscriptions
                WHERE user_id = ?
                  AND status = 'paid'
                  AND (starts_at IS NULL OR starts_at = '' OR starts_at <= ?)
                  AND (ends_at IS NULL OR ends_at = '' OR ends_at > ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, now, now),
            )
        return _row_to_user_subscription(row) if row is not None else None

    def get_effective_subscription_plan(self, *, user_id: str) -> SubscriptionPlan:
        if self.has_unlimited_access(user_id=user_id):
            return SubscriptionPlan(
                "unlimited",
                "Unlimited Access",
                "internal",
                0,
                UNLIMITED_ACCESS_LIMIT,
                UNLIMITED_ACCESS_LIMIT,
                None,
            )
        now = _now_iso()
        with self._connect() as conn:
            row = self._fetchone(
                conn,
                """
                SELECT sp.plan_code, sp.display_name, sp.subscription_type, sp.price_eur,
                       sp.max_cases, sp.max_documents_per_case, sp.case_ttl_days
                FROM user_subscriptions us
                JOIN subscription_plans sp ON sp.plan_code = us.plan_code
                WHERE us.user_id = ?
                  AND us.status = 'paid'
                  AND (us.starts_at IS NULL OR us.starts_at = '' OR us.starts_at <= ?)
                  AND (us.ends_at IS NULL OR us.ends_at = '' OR us.ends_at > ?)
                ORDER BY us.created_at DESC
                LIMIT 1
                """,
                (user_id, now, now),
            )
        if row is None:
            return SubscriptionPlan("free", "Free", "none", 0, 1, 2, 1)
        return _row_to_subscription_plan(row)

    def get_document_upload_limit(self, *, user_id: str) -> int:
        return self.get_effective_subscription_plan(user_id=user_id).max_documents_per_case

    def list_unprocessed_case_documents(self, *, limit: int = 20) -> list[CaseDocument]:
        with self._connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT doc_id, case_id, kind, version, storage_uri, original_filename, uploaded_by_user_id,
                       processing_status, processing_error, processed_at, created_at
                FROM case_documents
                WHERE kind IN ('uploaded', 'chat_attachment', 'session_history')
                  AND processing_status IN ('uploaded', 'failed')
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_case_document(row) for row in rows]

    def mark_document_processing(
        self, *, doc_id: str, status: str, error: str | None = None
    ) -> None:
        processed_at = _now_iso() if status == "processed" else None
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
            existing = self._fetchone(
                conn, "SELECT content_id FROM case_document_contents WHERE doc_id = ?", (doc_id,)
            )
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

    def _replace_stored_payload(self, *, storage_uri: str, payload: bytes) -> None:
        destination = self._resolve_storage_path(storage_uri)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

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

    def _select_ai_task_route_policy(
        self,
        conn: sqlite3.Connection | PostgresConnection[Any],
        *,
        user_id: str,
        plan_code: str,
        task_type: str,
    ) -> AITaskRoutePolicy | None:
        group_rows = self._execute(
            conn,
            """
            SELECT gu.model_group_id
            FROM ai_model_group_users gu
            JOIN ai_model_groups g ON g.model_group_id = gu.model_group_id
            WHERE gu.user_id = ?
              AND g.enabled = 1
              AND g.deleted_at IS NULL
            """,
            (user_id,),
        ).fetchall()
        group_ids = [str(row[0]) for row in group_rows]
        group_clause = "model_group_id IS NULL OR model_group_id = ''"
        params: list[Any] = [task_type, "default", plan_code, "", "*"]
        if group_ids:
            placeholders = ", ".join("?" for _ in group_ids)
            group_clause = f"{group_clause} OR model_group_id IN ({placeholders})"
            params.extend(group_ids)
        params.extend([task_type, plan_code])
        if group_ids:
            params.extend(group_ids)
        query = f"""
            SELECT policy_id, task_type, plan_code, model_group_id,
                   preferred_external_model_profile_id, preferred_local_model_profile_id,
                   allow_external, require_external_ack, require_eu_data_zone,
                   fallback_local_on_error, fallback_local_on_budget, max_cost_eur,
                   priority, enabled, created_at, updated_at,
                   deleted_at, deleted_by_admin_user_id, deleted_reason
            FROM ai_task_route_policies
            WHERE enabled = 1
              AND deleted_at IS NULL
              AND task_type IN (?, ?)
              AND plan_code IN (?, ?, ?)
              AND ({group_clause})
            ORDER BY
              CASE WHEN task_type = ? THEN 0 ELSE 1 END,
              CASE WHEN plan_code = ? THEN 0 WHEN plan_code = '' THEN 1 ELSE 2 END,
              CASE
                WHEN model_group_id IS NULL OR model_group_id = '' THEN 1
                {"WHEN model_group_id IN (" + ", ".join("?" for _ in group_ids) + ") THEN 0" if group_ids else ""}
                ELSE 2
              END,
              priority DESC,
              created_at DESC
            LIMIT 1
        """
        row = self._fetchone(conn, query, tuple(params))
        return _row_to_ai_task_route_policy(row) if row is not None else None

    def _get_ai_model_route_target(
        self,
        conn: sqlite3.Connection | PostgresConnection[Any],
        model_profile_id: str | None,
    ) -> tuple[AIModelProvider, AIModelProfile] | None:
        if not model_profile_id:
            return None
        row = self._fetchone(
            conn,
            """
            SELECT p.provider_id, p.provider_code, p.provider_type, p.display_name, p.base_url,
                   p.api_version, p.region, p.data_zone, p.is_external, p.is_local,
                   p.health_check_url, p.enabled, p.created_at, p.updated_at,
                   p.deleted_at, p.deleted_by_admin_user_id, p.deleted_reason, p.model_parameters_json,
                   m.model_profile_id, m.provider_id, m.model_code, m.deployment_name,
                   m.context_window_tokens, m.input_price_per_1m, m.cached_input_price_per_1m,
                   m.output_price_per_1m, m.billing_currency, m.effective_from, m.effective_to,
                   m.eu_data_zone_capable, m.is_default_for_free, m.enabled, m.created_at, m.updated_at,
                   m.deleted_at, m.deleted_by_admin_user_id, m.deleted_reason, m.model_parameters_json
            FROM ai_model_profiles m
            JOIN ai_model_providers p ON p.provider_id = m.provider_id
            WHERE m.model_profile_id = ?
              AND m.enabled = 1
              AND m.deleted_at IS NULL
              AND p.enabled = 1
              AND p.deleted_at IS NULL
            """,
            (model_profile_id,),
        )
        if row is None:
            return None
        return _row_to_ai_model_provider(row[:18]), _row_to_ai_model_profile(row[18:])

    def _get_enabled_ai_model_user_override_target(
        self,
        conn: sqlite3.Connection | PostgresConnection[Any],
        *,
        user_id: str,
    ) -> tuple[AIModelUserOverride, tuple[AIModelProvider, AIModelProfile]] | None:
        if not user_id.strip():
            return None
        row = self._fetchone(
            conn,
            """
            SELECT override_id, user_id, model_profile_id, enabled,
                   created_by_admin_user_id, updated_by_admin_user_id,
                   disabled_by_admin_user_id, created_reason, updated_reason,
                   disabled_reason, created_at, updated_at, disabled_at
            FROM ai_model_user_overrides
            WHERE user_id = ?
              AND enabled = 1
            """,
            (user_id.strip(),),
        )
        if row is None:
            return None
        override = _row_to_ai_model_user_override(row)
        target = self._get_ai_model_route_target(conn, override.model_profile_id)
        if target is None:
            return None
        return override, target

    def _ensure_ai_model_routing_schema(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        self._execute_script(
            conn,
            """
            CREATE TABLE IF NOT EXISTS ai_model_providers (
                provider_id TEXT PRIMARY KEY,
                provider_code TEXT UNIQUE NOT NULL,
                provider_type TEXT NOT NULL,
                display_name TEXT NOT NULL,
                base_url TEXT NOT NULL DEFAULT '',
                api_version TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT '',
                data_zone TEXT NOT NULL DEFAULT '',
                is_external INTEGER NOT NULL DEFAULT 0,
                is_local INTEGER NOT NULL DEFAULT 0,
                health_check_url TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by_admin_user_id TEXT NOT NULL DEFAULT '',
                deleted_reason TEXT NOT NULL DEFAULT '',
                model_parameters_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS ai_model_profiles (
                model_profile_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_code TEXT NOT NULL,
                deployment_name TEXT NOT NULL DEFAULT '',
                context_window_tokens INTEGER NOT NULL DEFAULT 0,
                input_price_per_1m REAL NOT NULL DEFAULT 0,
                cached_input_price_per_1m REAL NOT NULL DEFAULT 0,
                output_price_per_1m REAL NOT NULL DEFAULT 0,
                billing_currency TEXT NOT NULL DEFAULT 'USD',
                effective_from TEXT,
                effective_to TEXT,
                eu_data_zone_capable INTEGER NOT NULL DEFAULT 0,
                is_default_for_free INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by_admin_user_id TEXT NOT NULL DEFAULT '',
                deleted_reason TEXT NOT NULL DEFAULT '',
                model_parameters_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(provider_id, model_code),
                FOREIGN KEY(provider_id) REFERENCES ai_model_providers(provider_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_model_credentials (
                credential_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                credential_name TEXT NOT NULL DEFAULT 'default',
                secret_type TEXT NOT NULL DEFAULT 'api_key',
                protected_secret TEXT NOT NULL,
                secret_preview TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_revealed_at TEXT,
                UNIQUE(provider_id, credential_name, secret_type),
                FOREIGN KEY(provider_id) REFERENCES ai_model_providers(provider_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_model_groups (
                model_group_id TEXT PRIMARY KEY,
                group_code TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by_admin_user_id TEXT NOT NULL DEFAULT '',
                deleted_reason TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS ai_model_group_users (
                model_group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(model_group_id, user_id),
                FOREIGN KEY(model_group_id) REFERENCES ai_model_groups(model_group_id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_task_route_policies (
                policy_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                plan_code TEXT NOT NULL DEFAULT '',
                model_group_id TEXT,
                preferred_external_model_profile_id TEXT,
                preferred_local_model_profile_id TEXT,
                allow_external INTEGER NOT NULL DEFAULT 0,
                require_external_ack INTEGER NOT NULL DEFAULT 1,
                require_eu_data_zone INTEGER NOT NULL DEFAULT 1,
                fallback_local_on_error INTEGER NOT NULL DEFAULT 1,
                fallback_local_on_budget INTEGER NOT NULL DEFAULT 1,
                max_cost_eur REAL NOT NULL DEFAULT 0,
                priority INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by_admin_user_id TEXT NOT NULL DEFAULT '',
                deleted_reason TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(model_group_id) REFERENCES ai_model_groups(model_group_id) ON DELETE SET NULL,
                FOREIGN KEY(preferred_external_model_profile_id) REFERENCES ai_model_profiles(model_profile_id) ON DELETE SET NULL,
                FOREIGN KEY(preferred_local_model_profile_id) REFERENCES ai_model_profiles(model_profile_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS ai_model_usage_ledger (
                usage_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT '',
                subscription_id TEXT NOT NULL DEFAULT '',
                plan_code TEXT NOT NULL DEFAULT '',
                case_id TEXT NOT NULL DEFAULT '',
                task_type TEXT NOT NULL DEFAULT '',
                model_group_id TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                route_type TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                cached_input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_provider_currency REAL NOT NULL DEFAULT 0,
                estimated_cost_eur REAL NOT NULL DEFAULT 0,
                provider_currency TEXT NOT NULL DEFAULT 'USD',
                exchange_rate_used REAL NOT NULL DEFAULT 1,
                request_started_at TEXT NOT NULL,
                request_completed_at TEXT NOT NULL,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ok',
                fallback_reason TEXT NOT NULL DEFAULT '',
                confidentiality_warning_ack_id TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL DEFAULT '',
                question_id TEXT NOT NULL DEFAULT '',
                question_preview TEXT NOT NULL DEFAULT '',
                question_sha256 TEXT NOT NULL DEFAULT '',
                answer_id TEXT NOT NULL DEFAULT '',
                audit_metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_model_admin_audit_events (
                audit_event_id TEXT PRIMARY KEY,
                admin_user_id TEXT NOT NULL DEFAULT '',
                admin_email TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                old_value_summary_json TEXT NOT NULL DEFAULT '{}',
                new_value_summary_json TEXT NOT NULL DEFAULT '{}',
                reason TEXT NOT NULL DEFAULT '',
                correlation_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_model_user_overrides (
                override_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL UNIQUE,
                model_profile_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_by_admin_user_id TEXT NOT NULL DEFAULT '',
                updated_by_admin_user_id TEXT NOT NULL DEFAULT '',
                disabled_by_admin_user_id TEXT NOT NULL DEFAULT '',
                created_reason TEXT NOT NULL DEFAULT '',
                updated_reason TEXT NOT NULL DEFAULT '',
                disabled_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                disabled_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(model_profile_id) REFERENCES ai_model_profiles(model_profile_id) ON DELETE RESTRICT
            );

            CREATE INDEX IF NOT EXISTS idx_ai_task_route_policies_lookup
            ON ai_task_route_policies(task_type, plan_code, enabled, priority);

            CREATE INDEX IF NOT EXISTS idx_ai_model_usage_case_model_time
            ON ai_model_usage_ledger(case_id, provider, model, request_completed_at);

            CREATE INDEX IF NOT EXISTS idx_ai_model_usage_task_model_time
            ON ai_model_usage_ledger(task_type, provider, model, request_completed_at);

            CREATE INDEX IF NOT EXISTS idx_ai_model_admin_audit_entity_time
            ON ai_model_admin_audit_events(entity_type, entity_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_ai_model_user_overrides_enabled_user
            ON ai_model_user_overrides(user_id, enabled);

            CREATE INDEX IF NOT EXISTS idx_ai_model_user_overrides_profile
            ON ai_model_user_overrides(model_profile_id);

            """,
        )
        self._ensure_ai_model_profile_columns(conn)
        self._ensure_ai_model_parameter_columns(conn)
        self._ensure_ai_model_soft_delete_columns(conn)
        self._ensure_ai_model_usage_audit_columns(conn)
        self._ensure_case_catalog_selection_columns(conn)
        self._ensure_case_catalog_reference_columns(conn)
        self._ensure_case_communication_presentation_column(conn)

    def _ensure_case_communication_presentation_column(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            existing_columns = {
                row[0]
                for row in self._execute(
                    conn,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = ?
                    """,
                    ("case_communications",),
                ).fetchall()
            }
        else:
            existing_columns = {
                row[1]
                for row in self._execute(conn, "PRAGMA table_info(case_communications)").fetchall()
            }
        if "presentation_json" not in existing_columns:
            self._execute(
                conn,
                "ALTER TABLE case_communications "
                "ADD COLUMN presentation_json TEXT NOT NULL DEFAULT '{}'",
            )

    def _ensure_case_catalog_selection_columns(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            existing_columns = {
                row[0]
                for row in self._execute(
                    conn,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = ?
                    """,
                    ("case_catalog_selections",),
                ).fetchall()
            }
        else:
            existing_columns = {
                row[1]
                for row in self._execute(conn, "PRAGMA table_info(case_catalog_selections)").fetchall()
            }
        if "clarification_question" not in existing_columns:
            self._execute(
                conn,
                "ALTER TABLE case_catalog_selections ADD COLUMN clarification_question TEXT NOT NULL DEFAULT ''",
            )

    def _ensure_case_catalog_reference_columns(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            self._execute(conn, "UPDATE case_catalog_selections SET case_id = NULL WHERE case_id = ''")
            self._execute(conn, "UPDATE case_catalog_events SET case_id = NULL WHERE case_id = ''")
            self._execute(conn, "ALTER TABLE case_catalog_selections ALTER COLUMN case_id DROP NOT NULL")
            self._execute(conn, "ALTER TABLE case_catalog_selections ALTER COLUMN case_id DROP DEFAULT")
            self._execute(conn, "ALTER TABLE case_catalog_events ALTER COLUMN case_id DROP NOT NULL")
            self._execute(conn, "ALTER TABLE case_catalog_events ALTER COLUMN case_id DROP DEFAULT")
            return

        selection_columns = {
            str(row[1]): {"notnull": int(row[3]), "default": row[4]}
            for row in self._execute(conn, "PRAGMA table_info(case_catalog_selections)").fetchall()
        }
        event_columns = {
            str(row[1]): {"notnull": int(row[3]), "default": row[4]}
            for row in self._execute(conn, "PRAGMA table_info(case_catalog_events)").fetchall()
        }
        selection_case_id = selection_columns.get("case_id")
        event_case_id = event_columns.get("case_id")
        if not selection_case_id or not event_case_id:
            return
        needs_selection_migration = selection_case_id["notnull"] == 1
        needs_event_migration = event_case_id["notnull"] == 1
        if not needs_selection_migration and not needs_event_migration:
            return

        self._execute(conn, "PRAGMA foreign_keys = OFF")
        self._execute(conn, "ALTER TABLE case_catalog_selections RENAME TO case_catalog_selections_legacy")
        self._execute(conn, "ALTER TABLE case_catalog_events RENAME TO case_catalog_events_legacy")
        self._execute_script(
            conn,
            """
            CREATE TABLE case_catalog_selections (
                selection_id TEXT PRIMARY KEY,
                selection_scope TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                case_id TEXT DEFAULT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                case_type_id TEXT NOT NULL DEFAULT '',
                case_type_key TEXT NOT NULL DEFAULT '',
                case_type_name TEXT NOT NULL DEFAULT '',
                prompt_ids_json TEXT NOT NULL DEFAULT '[]',
                template_ids_json TEXT NOT NULL DEFAULT '[]',
                template_keys_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'unclassified',
                confidence_score REAL NOT NULL DEFAULT 0,
                confidence_gap REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT '',
                first_message_preview TEXT NOT NULL DEFAULT '',
                first_message_sha256 TEXT NOT NULL DEFAULT '',
                clarification_question TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(selection_scope, entity_id),
                FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            );

            CREATE TABLE case_catalog_events (
                event_id TEXT PRIMARY KEY,
                case_id TEXT DEFAULT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'info',
                summary TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            );
            """,
        )
        self._execute(
            conn,
            """
            INSERT INTO case_catalog_selections(
                selection_id, selection_scope, entity_id, case_id, session_id,
                case_type_id, case_type_key, case_type_name, prompt_ids_json, template_ids_json,
                template_keys_json, status, confidence_score, confidence_gap, source,
                first_message_preview, first_message_sha256, clarification_question, created_at, updated_at
            )
            SELECT
                selection_id, selection_scope, entity_id, NULLIF(case_id, ''), session_id,
                case_type_id, case_type_key, case_type_name, prompt_ids_json, template_ids_json,
                template_keys_json, status, confidence_score, confidence_gap, source,
                first_message_preview, first_message_sha256, clarification_question, created_at, updated_at
            FROM case_catalog_selections_legacy
            """,
        )
        self._execute(
            conn,
            """
            INSERT INTO case_catalog_events(
                event_id, case_id, session_id, event_type, status, severity, summary, details_json, created_at
            )
            SELECT
                event_id, NULLIF(case_id, ''), session_id, event_type, status, severity, summary, details_json, created_at
            FROM case_catalog_events_legacy
            """,
        )
        self._execute(conn, "DROP TABLE case_catalog_selections_legacy")
        self._execute(conn, "DROP TABLE case_catalog_events_legacy")
        self._execute(conn, "PRAGMA foreign_keys = ON")

    def _ensure_ai_model_soft_delete_columns(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        for table_name in (
            "ai_model_providers",
            "ai_model_profiles",
            "ai_model_groups",
            "ai_task_route_policies",
        ):
            self._ensure_soft_delete_columns(conn, table_name=table_name)

    def _ensure_soft_delete_columns(
        self, conn: sqlite3.Connection | PostgresConnection[Any], *, table_name: str
    ) -> None:
        if self.uses_postgres:
            existing_columns = {
                row[0]
                for row in self._execute(
                    conn,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = ?
                    """,
                    (table_name,),
                ).fetchall()
            }
        else:
            existing_columns = {
                row[1] for row in self._execute(conn, f"PRAGMA table_info({table_name})").fetchall()
            }
        missing_columns = {
            "deleted_at": "TEXT",
            "deleted_by_admin_user_id": "TEXT NOT NULL DEFAULT ''",
            "deleted_reason": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, column_definition in missing_columns.items():
            if column_name not in existing_columns:
                self._execute(
                    conn,
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}",
                )

    def _ensure_ai_model_profile_columns(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        if self.uses_postgres:
            profile_columns = {
                row[0]
                for row in self._execute(
                    conn,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'ai_model_profiles'
                    """,
                ).fetchall()
            }
        else:
            profile_columns = {
                row[1]
                for row in self._execute(conn, "PRAGMA table_info(ai_model_profiles)").fetchall()
            }
        if "is_default_for_free" not in profile_columns:
            self._execute(
                conn,
                "ALTER TABLE ai_model_profiles ADD COLUMN is_default_for_free INTEGER NOT NULL DEFAULT 0",
            )

    def _ensure_ai_model_parameter_columns(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        for table_name in ("ai_model_providers", "ai_model_profiles"):
            if self.uses_postgres:
                columns = {
                    row[0]
                    for row in self._execute(
                        conn,
                        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                        (table_name,),
                    ).fetchall()
                }
            else:
                columns = {
                    row[1]
                    for row in self._execute(conn, f"PRAGMA table_info({table_name})").fetchall()
                }
            if "model_parameters_json" not in columns:
                self._execute(
                    conn,
                    f"ALTER TABLE {table_name} ADD COLUMN model_parameters_json TEXT NOT NULL DEFAULT '{{}}'",
                )

    def _ensure_ai_model_usage_audit_columns(
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
                    WHERE table_name = 'ai_model_usage_ledger'
                    """,
                ).fetchall()
            }
        else:
            columns = {
                row[1]
                for row in self._execute(
                    conn, "PRAGMA table_info(ai_model_usage_ledger)"
                ).fetchall()
            }
        missing_columns = {
            "session_id": "TEXT NOT NULL DEFAULT ''",
            "question_id": "TEXT NOT NULL DEFAULT ''",
            "question_preview": "TEXT NOT NULL DEFAULT ''",
            "question_sha256": "TEXT NOT NULL DEFAULT ''",
            "answer_id": "TEXT NOT NULL DEFAULT ''",
            "audit_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column_name, column_definition in missing_columns.items():
            if column_name not in columns:
                self._execute(
                    conn,
                    f"ALTER TABLE ai_model_usage_ledger ADD COLUMN {column_name} {column_definition}",
                )
        self._execute(
            conn,
            """
            CREATE INDEX IF NOT EXISTS idx_ai_model_usage_case_question_time
            ON ai_model_usage_ledger(case_id, question_id, request_completed_at)
            """,
        )

    def _ensure_user_schema(self, conn: sqlite3.Connection | PostgresConnection[Any]) -> None:
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
            columns = {row[1] for row in self._execute(conn, "PRAGMA table_info(users)").fetchall()}

        if "phone_number" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN phone_number TEXT")
        if "first_name" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN first_name TEXT")
        if "last_name" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN last_name TEXT")
        if "address" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN address TEXT")
        if "city" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN city TEXT")
        if "country" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN country TEXT")
        if "zip_code" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN zip_code TEXT")
        if "tax_number" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN tax_number TEXT")
        if "identity_card_number" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN identity_card_number TEXT")
        if "date_of_birth" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN date_of_birth TEXT")
        if "social_security_number" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN social_security_number TEXT")
        if "data_processing_consent_at" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN data_processing_consent_at TEXT")
        if "data_processing_consent_version" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN data_processing_consent_version TEXT")
        if "mcp_api_key_hash" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN mcp_api_key_hash TEXT")
        if "mcp_api_key_expires_at" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN mcp_api_key_expires_at TEXT")
        if "role" not in columns:
            self._execute(conn, "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if "is_enabled" not in columns:
            self._execute(
                conn, "ALTER TABLE users ADD COLUMN is_enabled INTEGER NOT NULL DEFAULT 1"
            )
        self._execute(conn, "UPDATE users SET role = 'user' WHERE role IS NULL OR TRIM(role) = ''")
        self._execute(conn, "UPDATE users SET is_enabled = 1 WHERE is_enabled IS NULL")
        for admin_email in _configured_admin_emails():
            self._execute(
                conn,
                "UPDATE users SET role = 'admin', is_enabled = 1 WHERE lower(email) = ?",
                (admin_email,),
            )
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

    def _ensure_mcp_oauth_schema(self, conn: sqlite3.Connection | PostgresConnection[Any]) -> None:
        if self.uses_postgres:
            columns = {
                row[0]
                for row in self._execute(
                    conn,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'mcp_oauth_authorization_codes'
                    """,
                ).fetchall()
            }
        else:
            columns = {
                row[1]
                for row in self._execute(
                    conn,
                    "PRAGMA table_info(mcp_oauth_authorization_codes)",
                ).fetchall()
            }
        if "resource" not in columns:
            self._execute(
                conn,
                "ALTER TABLE mcp_oauth_authorization_codes ADD COLUMN resource TEXT NOT NULL DEFAULT ''",
            )
        if "scope" not in columns:
            self._execute(
                conn,
                "ALTER TABLE mcp_oauth_authorization_codes ADD COLUMN scope TEXT NOT NULL DEFAULT 'mcp:laws'",
            )
        self._execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mcp_otp_verifications (
                user_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                PRIMARY KEY(user_id, purpose),
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """,
        )
        self._execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS user_mfa_settings (
                user_id TEXT PRIMARY KEY,
                totp_secret_protected TEXT,
                pending_totp_secret_protected TEXT,
                totp_enabled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """,
        )
        self._execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mfa_login_challenges (
                challenge_token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
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
            columns = {
                row[1]
                for row in self._execute(conn, "PRAGMA table_info(case_documents)").fetchall()
            }
        if "processing_status" not in columns:
            self._execute(
                conn,
                "ALTER TABLE case_documents ADD COLUMN processing_status TEXT NOT NULL DEFAULT 'uploaded'",
            )
        if "processing_error" not in columns:
            self._execute(conn, "ALTER TABLE case_documents ADD COLUMN processing_error TEXT")
        if "processed_at" not in columns:
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
                for row in self._execute(
                    conn, "PRAGMA table_info(case_document_contents)"
                ).fetchall()
            }
        if "embedding_model" not in content_columns:
            self._execute(
                conn,
                "ALTER TABLE case_document_contents ADD COLUMN embedding_model TEXT NOT NULL DEFAULT ''",
            )
        if "embedding_dimensions" not in content_columns:
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

    def _ensure_case_citation_schema(
        self, conn: sqlite3.Connection | PostgresConnection[Any]
    ) -> None:
        self._execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS case_citations (
                citation_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                question_message_id TEXT,
                answer_message_id TEXT,
                source_type TEXT NOT NULL,
                source_id TEXT,
                source_url TEXT,
                title TEXT NOT NULL,
                citation_label TEXT,
                law_number TEXT,
                section TEXT,
                effective_from TEXT,
                court TEXT,
                ecli TEXT,
                file_number TEXT,
                decision_date TEXT,
                snippet TEXT,
                retrieval_tool TEXT,
                relevance_score REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
            )
            """,
        )
        self._execute(
            conn,
            """
            CREATE INDEX IF NOT EXISTS idx_case_citations_case_answer
            ON case_citations(case_id, answer_message_id, created_at)
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
            columns = {
                row[1]
                for row in self._execute(conn, "PRAGMA table_info(subscription_plans)").fetchall()
            }
        if "max_documents_per_case" not in columns:
            self._execute(
                conn,
                "ALTER TABLE subscription_plans ADD COLUMN max_documents_per_case INTEGER NOT NULL DEFAULT 2",
            )

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
            ("free", "Free", "none", 0, 1, 2, 1),
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

    def _seed_ai_model_routing(self, conn: sqlite3.Connection | PostgresConnection[Any]) -> None:
        now = _now_iso()
        local_base_url = (
            os.getenv("LOCAL_LLM_OPENAI_BASE_URL", "").strip() or "http://127.0.0.1:11434/v1"
        )
        local_health_url = (
            os.getenv("LOCAL_LLM_HEALTH_URL", "").strip() or "http://127.0.0.1:11434/api/tags"
        )
        local_model = "qwen3:1.7b"
        local_profile_id = "local_ollama_default"
        azure_profile_id = "azure_foundry_gpt_4o_mini"
        self._execute(
            conn,
            """
            INSERT INTO ai_model_providers(
                provider_id, provider_code, provider_type, display_name, base_url,
                api_version, region, data_zone, is_external, is_local, health_check_url,
                enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_code) DO UPDATE SET
                provider_type = excluded.provider_type,
                display_name = excluded.display_name,
                base_url = excluded.base_url,
                health_check_url = excluded.health_check_url,
                is_external = excluded.is_external,
                is_local = excluded.is_local,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                "local_ollama",
                "local_ollama",
                "ollama",
                "Local Ollama",
                local_base_url.rstrip("/"),
                "",
                "",
                "local",
                0,
                1,
                local_health_url,
                1,
                now,
                now,
            ),
        )
        self._execute(
            conn,
            """
            INSERT INTO ai_model_providers(
                provider_id, provider_code, provider_type, display_name, base_url,
                api_version, region, data_zone, is_external, is_local, health_check_url,
                enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_code) DO UPDATE SET
                provider_type = excluded.provider_type,
                display_name = excluded.display_name,
                is_external = excluded.is_external,
                is_local = excluded.is_local,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                "azure_foundry",
                "azure_foundry",
                "azurefoundry",
                "Azure AI Foundry",
                "",
                "2024-12-01-preview",
                "",
                "eu",
                1,
                0,
                "",
                1,
                now,
                now,
            ),
        )
        self._execute(
            conn,
            """
            INSERT INTO ai_model_profiles(
                model_profile_id, provider_id, model_code, deployment_name,
                context_window_tokens, input_price_per_1m, cached_input_price_per_1m,
                output_price_per_1m, billing_currency, effective_from, effective_to,
                eu_data_zone_capable, is_default_for_free, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_profile_id) DO NOTHING
            """,
            (
                local_profile_id,
                "local_ollama",
                local_model,
                local_model,
                0,
                0.0,
                0.0,
                0.0,
                "EUR",
                None,
                None,
                1,
                1,
                1,
                now,
                now,
            ),
        )
        self._execute(
            conn,
            """
            INSERT INTO ai_model_profiles(
                model_profile_id, provider_id, model_code, deployment_name,
                context_window_tokens, input_price_per_1m, cached_input_price_per_1m,
                output_price_per_1m, billing_currency, effective_from, effective_to,
                eu_data_zone_capable, is_default_for_free, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_profile_id) DO UPDATE SET
                model_code = excluded.model_code,
                deployment_name = excluded.deployment_name,
                eu_data_zone_capable = excluded.eu_data_zone_capable,
                updated_at = excluded.updated_at
            """,
            (
                azure_profile_id,
                "azure_foundry",
                "gpt-4o-mini",
                "gpt-4o-mini",
                128000,
                0.15,
                0.075,
                0.60,
                "USD",
                None,
                None,
                1,
                0,
                1,
                now,
                now,
            ),
        )
        for plan_code in ("", "free", "case", "basic", "premium", "unlimited"):
            allow_external = 0 if plan_code in ("", "free") else 1
            external_profile_id = (
                azure_profile_id if plan_code in ("case", "basic", "premium", "unlimited") else None
            )
            self._execute(
                conn,
                """
                INSERT INTO ai_task_route_policies(
                    policy_id, task_type, plan_code, model_group_id,
                    preferred_external_model_profile_id, preferred_local_model_profile_id,
                    allow_external, require_external_ack, require_eu_data_zone,
                    fallback_local_on_error, fallback_local_on_budget, max_cost_eur,
                    priority, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO NOTHING
                """,
                (
                    f"default:{plan_code}:default",
                    "default",
                    plan_code,
                    None,
                    external_profile_id,
                    local_profile_id,
                    allow_external,
                    0 if external_profile_id else 1,
                    1,
                    1,
                    1,
                    0.0,
                    0,
                    1,
                    now,
                    now,
                ),
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


def _row_to_ai_model_provider(row: tuple[object, ...]) -> AIModelProvider:
    return AIModelProvider(
        provider_id=str(row[0]),
        provider_code=str(row[1]),
        provider_type=str(row[2]),
        display_name=str(row[3]),
        base_url=str(row[4]),
        api_version=str(row[5]),
        region=str(row[6]),
        data_zone=str(row[7]),
        is_external=_row_bool(row[8]),
        is_local=_row_bool(row[9]),
        health_check_url=str(row[10]),
        model_parameters=deserialize_model_parameters(row[17] if len(row) > 17 else "{}"),
        enabled=_row_bool(row[11]),
        created_at=str(row[12]),
        updated_at=str(row[13]),
        deleted_at=str(row[14]) if len(row) > 14 and row[14] is not None else None,
        deleted_by_admin_user_id=str(row[15]) if len(row) > 15 else "",
        deleted_reason=str(row[16]) if len(row) > 16 else "",
    )


def _row_to_ai_model_profile(row: tuple[object, ...]) -> AIModelProfile:
    return AIModelProfile(
        model_profile_id=str(row[0]),
        provider_id=str(row[1]),
        model_code=str(row[2]),
        deployment_name=str(row[3]),
        model_parameters=deserialize_model_parameters(row[19] if len(row) > 19 else "{}"),
        context_window_tokens=int(row[4]),
        input_price_per_1m=float(row[5]),
        cached_input_price_per_1m=float(row[6]),
        output_price_per_1m=float(row[7]),
        billing_currency=str(row[8]),
        effective_from=str(row[9]) if row[9] is not None else None,
        effective_to=str(row[10]) if row[10] is not None else None,
        eu_data_zone_capable=_row_bool(row[11]),
        is_default_for_free=_row_bool(row[12]),
        enabled=_row_bool(row[13]),
        created_at=str(row[14]),
        updated_at=str(row[15]),
        deleted_at=str(row[16]) if len(row) > 16 and row[16] is not None else None,
        deleted_by_admin_user_id=str(row[17]) if len(row) > 17 else "",
        deleted_reason=str(row[18]) if len(row) > 18 else "",
    )


def _row_to_ai_model_credential(
    row: tuple[object, ...], *, reveal_secret: bool
) -> AIModelCredential:
    protected_secret = str(row[4])
    return AIModelCredential(
        credential_id=str(row[0]),
        provider_id=str(row[1]),
        credential_name=str(row[2]),
        secret_type=str(row[3]),
        protected_secret=protected_secret,
        secret_preview=str(row[5]),
        secret_value=_reveal_model_secret(protected_secret) if reveal_secret else None,
        enabled=_row_bool(row[6]),
        created_at=str(row[7]),
        updated_at=str(row[8]),
        last_revealed_at=str(row[9]) if row[9] is not None else None,
    )


def _row_to_ai_task_route_policy(row: tuple[object, ...]) -> AITaskRoutePolicy:
    return AITaskRoutePolicy(
        policy_id=str(row[0]),
        task_type=str(row[1]),
        plan_code=str(row[2]),
        model_group_id=str(row[3]) if row[3] is not None else None,
        preferred_external_model_profile_id=str(row[4]) if row[4] is not None else None,
        preferred_local_model_profile_id=str(row[5]) if row[5] is not None else None,
        allow_external=_row_bool(row[6]),
        require_external_ack=_row_bool(row[7]),
        require_eu_data_zone=_row_bool(row[8]),
        fallback_local_on_error=_row_bool(row[9]),
        fallback_local_on_budget=_row_bool(row[10]),
        max_cost_eur=float(row[11]),
        priority=int(row[12]),
        enabled=_row_bool(row[13]),
        created_at=str(row[14]),
        updated_at=str(row[15]),
        deleted_at=str(row[16]) if len(row) > 16 and row[16] is not None else None,
        deleted_by_admin_user_id=str(row[17]) if len(row) > 17 else "",
        deleted_reason=str(row[18]) if len(row) > 18 else "",
    )


def _row_to_ai_model_group(row: tuple[object, ...]) -> AIModelGroup:
    return AIModelGroup(
        model_group_id=str(row[0]),
        group_code=str(row[1]),
        display_name=str(row[2]),
        priority=int(row[3] or 0),
        enabled=_row_bool(row[4]),
        created_at=str(row[5]),
        updated_at=str(row[6]),
        deleted_at=str(row[7]) if len(row) > 7 and row[7] is not None else None,
        deleted_by_admin_user_id=str(row[8]) if len(row) > 8 else "",
        deleted_reason=str(row[9]) if len(row) > 9 else "",
    )


def _row_to_ai_model_group_membership(row: tuple[object, ...]) -> AIModelGroupMembership:
    return AIModelGroupMembership(
        model_group_id=str(row[0]),
        user_id=str(row[1]),
        email=str(row[2]),
        full_name=str(row[3]),
        created_at=str(row[4]),
    )


def _row_to_ai_model_user_override(row: tuple[object, ...]) -> AIModelUserOverride:
    return AIModelUserOverride(
        override_id=str(row[0]),
        user_id=str(row[1]),
        model_profile_id=str(row[2]),
        enabled=_row_bool(row[3]),
        created_by_admin_user_id=str(row[4]),
        updated_by_admin_user_id=str(row[5]),
        disabled_by_admin_user_id=str(row[6]),
        created_reason=str(row[7]),
        updated_reason=str(row[8]),
        disabled_reason=str(row[9]),
        created_at=str(row[10]),
        updated_at=str(row[11]),
        disabled_at=str(row[12]) if row[12] is not None else None,
    )


def _row_to_ai_model_admin_audit_event(row: tuple[object, ...]) -> AIModelAdminAuditEvent:
    return AIModelAdminAuditEvent(
        audit_event_id=str(row[0]),
        admin_user_id=str(row[1]),
        admin_email=str(row[2]),
        action=str(row[3]),
        entity_type=str(row[4]),
        entity_id=str(row[5]),
        old_value_summary=str(row[6]),
        new_value_summary=str(row[7]),
        reason=str(row[8]),
        correlation_id=str(row[9]),
        created_at=str(row[10]),
    )


def _row_to_case_citation(row: tuple[object, ...]) -> CaseCitation:
    relevance_score = row[18]
    return CaseCitation(
        citation_id=str(row[0]),
        case_id=str(row[1]),
        question_message_id=str(row[2]) if row[2] is not None else None,
        answer_message_id=str(row[3]) if row[3] is not None else None,
        source_type=str(row[4]),
        source_id=str(row[5]) if row[5] is not None else None,
        source_url=str(row[6]) if row[6] is not None else None,
        title=str(row[7]),
        citation_label=str(row[8]) if row[8] is not None else None,
        law_number=str(row[9]) if row[9] is not None else None,
        section=str(row[10]) if row[10] is not None else None,
        effective_from=str(row[11]) if row[11] is not None else None,
        court=str(row[12]) if row[12] is not None else None,
        ecli=str(row[13]) if row[13] is not None else None,
        file_number=str(row[14]) if row[14] is not None else None,
        decision_date=str(row[15]) if row[15] is not None else None,
        snippet=str(row[16]) if row[16] is not None else None,
        retrieval_tool=str(row[17]) if row[17] is not None else None,
        relevance_score=float(relevance_score) if relevance_score is not None else None,
        created_at=str(row[19]),
    )


def _row_to_ai_model_usage_summary(row: tuple[object, ...]) -> AIModelUsageSummary:
    return AIModelUsageSummary(
        case_id=str(row[0]),
        user_id=str(row[1]),
        subscription_id=str(row[2]),
        plan_code=str(row[3]),
        task_type=str(row[4]),
        provider=str(row[5]),
        model=str(row[6]),
        route_type=str(row[7]),
        status=str(row[8]),
        fallback_reason=str(row[9]),
        input_tokens=int(row[10] or 0),
        cached_input_tokens=int(row[11] or 0),
        output_tokens=int(row[12] or 0),
        total_tokens=int(row[13] or 0),
        estimated_cost_eur=float(row[14] or 0),
        request_count=int(row[15] or 0),
    )


def _row_to_ai_model_top_case_usage(row: tuple[object, ...]) -> AIModelTopCaseUsage:
    return AIModelTopCaseUsage(
        case_id=str(row[0]),
        plan_code=str(row[1]),
        provider=str(row[2]),
        model=str(row[3]),
        route_type=str(row[4]),
        input_tokens=int(row[5] or 0),
        cached_input_tokens=int(row[6] or 0),
        output_tokens=int(row[7] or 0),
        total_tokens=int(row[8] or 0),
        estimated_cost_eur=float(row[9] or 0),
        request_count=int(row[10] or 0),
    )


def _row_to_ai_model_usage_audit_entry(row: tuple[object, ...]) -> AIModelUsageAuditEntry:
    return AIModelUsageAuditEntry(
        usage_id=str(row[0]),
        case_id=str(row[1]),
        user_id=str(row[2]),
        subscription_id=str(row[3]),
        plan_code=str(row[4]),
        task_type=str(row[5]),
        model_group_id=str(row[6]),
        provider=str(row[7]),
        model=str(row[8]),
        route_type=str(row[9]),
        input_tokens=int(row[10] or 0),
        cached_input_tokens=int(row[11] or 0),
        output_tokens=int(row[12] or 0),
        total_tokens=int(row[13] or 0),
        estimated_cost_provider_currency=float(row[14] or 0),
        estimated_cost_eur=float(row[15] or 0),
        provider_currency=str(row[16]),
        exchange_rate_used=float(row[17] or 0),
        request_started_at=str(row[18]),
        request_completed_at=str(row[19]),
        latency_ms=int(row[20] or 0),
        status=str(row[21]),
        fallback_reason=str(row[22]),
        confidentiality_warning_ack_id=str(row[23]),
        session_id=str(row[24]),
        question_id=str(row[25]),
        question_preview=str(row[26]),
        question_sha256=str(row[27]),
        answer_id=str(row[28]),
        audit_metadata=_json_loads_dict(str(row[29] or "{}")),
        created_at=str(row[30]),
    )


def _ai_audit_question_preview(
    *,
    question_preview: str,
    question_text: str,
    max_chars: int = 1000,
) -> str:
    source = question_preview if question_preview.strip() else question_text
    normalized = " ".join(source.split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _json_loads_dict(value: str) -> dict[str, Any]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _json_loads_list_strings(value: str) -> list[str]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item).strip() for item in loaded if str(item).strip()]


def _route_selection(
    *,
    policy: AITaskRoutePolicy,
    target: tuple[AIModelProvider, AIModelProfile],
    route_type: str,
    task_type: str,
    plan_code: str,
    reason: str,
) -> AIModelRouteSelection:
    provider, profile = target
    return AIModelRouteSelection(
        policy=policy,
        provider=provider,
        model_profile=profile,
        route_type=route_type,
        task_type=task_type,
        plan_code=plan_code,
        requires_external_ack=False,
        reason=reason,
    )


def _route_selection_without_target(
    *,
    policy: AITaskRoutePolicy,
    route_type: str,
    task_type: str,
    plan_code: str,
    reason: str,
) -> AIModelRouteSelection:
    return AIModelRouteSelection(
        policy=policy,
        provider=None,
        model_profile=None,
        route_type=route_type,
        task_type=task_type,
        plan_code=plan_code,
        requires_external_ack=False,
        reason=reason,
    )


def _bool_int(value: bool) -> int:
    return 1 if value else 0


def _row_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_route_key(value: str, *, default: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    return normalized or default


def _normalize_user_role(value: str) -> str:
    normalized = value.strip().lower()
    return USER_ROLE_ADMIN if normalized == USER_ROLE_ADMIN else USER_ROLE_USER


def _configured_admin_emails() -> set[str]:
    raw = os.getenv("JURISDIGTA_ADMIN_EMAILS", "").strip()
    if not raw or raw.lower() == "unknown-variable":
        raw = os.getenv("JURISDIGTA_UNLIMITED_ACCESS_EMAILS", "").strip()
    values = {item.strip().lower() for item in raw.replace(";", ",").split(",") if item.strip()}
    values.update(DEFAULT_ADMIN_EMAILS)
    return values


def _default_role_for_email(email: str) -> str:
    return (
        USER_ROLE_ADMIN if email.strip().lower() in _configured_admin_emails() else USER_ROLE_USER
    )


def _protect_model_secret(secret: str) -> str:
    key = _model_credential_encryption_key()
    nonce = secrets.token_bytes(16)
    plaintext = secret.encode("utf-8")
    ciphertext = _xor_bytes(
        plaintext, _model_keystream(key=key, nonce=nonce, length=len(plaintext))
    )
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return "v1:" + base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")


def _protect_document_share_email(email: str) -> str:
    return _protect_model_secret(email)


def _reveal_document_share_email(protected_email: str) -> str | None:
    return _reveal_model_secret(protected_email)


def _reveal_model_secret(protected_secret: str) -> str | None:
    if not protected_secret.startswith("v1:"):
        return None
    try:
        payload = base64.urlsafe_b64decode(protected_secret[3:].encode("ascii"))
    except Exception:
        return None
    if len(payload) < 49:
        return None
    nonce = payload[:16]
    tag = payload[16:48]
    ciphertext = payload[48:]
    key = _model_credential_encryption_key()
    expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        return None
    plaintext = _xor_bytes(
        ciphertext, _model_keystream(key=key, nonce=nonce, length=len(ciphertext))
    )
    return plaintext.decode("utf-8")


def _model_credential_encryption_key() -> bytes:
    raw = (
        os.getenv("AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "").strip()
        or os.getenv("TOTP_SECRET_ENCRYPTION_KEY", "").strip()
        or os.getenv("MCP_API_JWT_SECRET", "").strip()
        or os.getenv("JWT_SECRET", "").strip()
        or "local-jurisdigta-model-credential-development-key"
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _model_keystream(*, key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    block = 0
    while len(output) < length:
        output.extend(hmac.new(key, nonce + block.to_bytes(4, "big"), hashlib.sha256).digest())
        block += 1
    return bytes(output[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _secret_preview(secret: str) -> str:
    normalized = secret.strip()
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:3]}...{normalized[-4:]}"


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


def generate_one_time_code(length: int = 6) -> str:
    digit_count = max(length, 4)
    return "".join(str(random.randint(0, 9)) for _ in range(digit_count))[:length]


def _hash_one_time_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _is_future_iso_datetime(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > datetime.now(timezone.utc)


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
        presentation=_json_loads_dict(str(row[6])) if len(row) > 6 and row[6] else {},
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
    if len(values) <= 8:
        values = [*values[:6], None, None, None, None, None, None, None, None, *values[6:]]
    role = (
        _normalize_user_role(str(values[18]))
        if len(values) > 20 and values[18] is not None
        else USER_ROLE_USER
    )
    is_enabled = _row_bool(values[19]) if len(values) > 20 and values[19] is not None else True
    created_at_index = 20 if len(values) > 20 else 18
    return User(
        user_id=str(values[0]),
        phone_number=str(values[1]) if values[1] is not None else None,
        email=str(values[2]),
        first_name=str(values[3]) if values[3] is not None else None,
        last_name=str(values[4]) if values[4] is not None else None,
        full_name=str(values[5]),
        address=str(values[6]) if values[6] is not None else None,
        city=str(values[7]) if values[7] is not None else None,
        country=str(values[8]) if values[8] is not None else None,
        zip_code=str(values[9]) if values[9] is not None else None,
        tax_number=str(values[10]) if values[10] is not None else None,
        identity_card_number=str(values[11]) if values[11] is not None else None,
        date_of_birth=str(values[12]) if values[12] is not None else None,
        social_security_number=str(values[13]) if values[13] is not None else None,
        data_processing_consent_at=str(values[14])
        if len(values) > 14 and values[14] is not None
        else None,
        data_processing_consent_version=str(values[15])
        if len(values) > 15 and values[15] is not None
        else None,
        mcp_api_key_hash=str(values[16]) if len(values) > 16 and values[16] is not None else None,
        mcp_api_key_expires_at=str(values[17])
        if len(values) > 17 and values[17] is not None
        else None,
        created_at=str(values[created_at_index])
        if len(values) > created_at_index and values[created_at_index] is not None
        else None,
        role=role,
        is_enabled=is_enabled,
    )


def _row_to_admin_user(row: tuple[object, ...]) -> AdminUser:
    return AdminUser(
        user_id=str(row[0]),
        phone_number=str(row[1]) if row[1] is not None else None,
        email=str(row[2]),
        full_name=str(row[3]),
        role=_normalize_user_role(str(row[4])),
        is_enabled=_row_bool(row[5]),
        created_at=str(row[6]) if row[6] is not None else None,
    )


def _row_to_admin_case_user(row: tuple[object, ...]) -> AdminCaseUser:
    return AdminCaseUser(
        user_id=str(row[0]),
        email=str(row[1]),
        full_name=str(row[2]),
        role=_normalize_user_role(str(row[3])),
        is_enabled=_row_bool(row[4]),
        created_at=str(row[5]) if row[5] is not None else None,
    )


def _row_to_user_mfa_settings(row: tuple[object, ...]) -> UserMfaSettings:
    totp_secret = str(row[1]) if row[1] is not None else None
    pending_secret = str(row[2]) if row[2] is not None else None
    totp_enabled_at = str(row[3]) if row[3] is not None else None
    return UserMfaSettings(
        user_id=str(row[0]),
        totp_enabled=bool(totp_secret and totp_enabled_at),
        totp_pending=bool(pending_secret),
        totp_secret_protected=totp_secret,
        pending_totp_secret_protected=pending_secret,
        totp_enabled_at=totp_enabled_at,
        updated_at=str(row[5]),
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


def _row_to_case_catalog_selection(row: tuple[object, ...]) -> CaseCatalogSelection:
    return CaseCatalogSelection(
        selection_id=str(row[0]),
        selection_scope=str(row[1]),
        entity_id=str(row[2]),
        case_id=str(row[3] or ""),
        session_id=str(row[4]),
        case_type_id=str(row[5]),
        case_type_key=str(row[6]),
        case_type_name=str(row[7]),
        prompt_ids=tuple(_json_loads_list_strings(str(row[8] or "[]"))),
        template_ids=tuple(_json_loads_list_strings(str(row[9] or "[]"))),
        template_keys=tuple(_json_loads_list_strings(str(row[10] or "[]"))),
        status=str(row[11]),
        confidence_score=float(row[12] or 0),
        confidence_gap=float(row[13] or 0),
        source=str(row[14]),
        first_message_preview=str(row[15]),
        first_message_sha256=str(row[16]),
        clarification_question=str(row[17]),
        created_at=str(row[18]),
        updated_at=str(row[19]),
    )


def _row_to_case_catalog_event(row: tuple[object, ...]) -> CaseCatalogEvent:
    return CaseCatalogEvent(
        event_id=str(row[0]),
        case_id=str(row[1] or ""),
        session_id=str(row[2]),
        event_type=str(row[3]),
        status=str(row[4]),
        severity=str(row[5]),
        summary=str(row[6]),
        details=_json_loads_dict(str(row[7] or "{}")),
        created_at=str(row[8]),
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


def _hash_mfa_challenge_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


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
