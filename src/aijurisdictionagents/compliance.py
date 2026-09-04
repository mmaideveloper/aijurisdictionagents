from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from collections.abc import Mapping, Sequence
import uuid

from .api_db.store import ApiDatabaseStore


CONSENT_SCOPE_DATA_PROCESSING = "data_processing"
CONSENT_SCOPE_EXTERNAL_MODEL = "external_model"
CONSENT_SCOPE_EXTERNAL_CHECK = "external_check"
CONSENT_SCOPE_MARKETING = "marketing"
CONSENT_SCOPE_SENSITIVE_PROCESSING = "sensitive_processing"
CONSENT_SCOPES = frozenset(
    {
        CONSENT_SCOPE_DATA_PROCESSING,
        CONSENT_SCOPE_EXTERNAL_MODEL,
        CONSENT_SCOPE_EXTERNAL_CHECK,
        CONSENT_SCOPE_MARKETING,
        CONSENT_SCOPE_SENSITIVE_PROCESSING,
    }
)

_PROHIBITED_AUDIT_KEY_PARTS = (
    "address",
    "content",
    "document",
    "email",
    "name",
    "password",
    "phone",
    "prompt",
    "secret",
    "text",
    "token",
)


@dataclass(frozen=True)
class ConsentEvent:
    event_id: str
    user_id: str
    session_id: str
    scope: str
    notice_version: str
    granted: bool
    source: str
    country: str
    purpose: str
    captured_at: str
    expires_at: str | None
    previous_event_id: str | None


@dataclass(frozen=True)
class RetentionRunResult:
    run_id: str
    started_at: str
    completed_at: str
    deleted_rows: dict[str, int]
    deleted_files: int


class ComplianceService:
    """GDPR/AI Act controls backed by the API database.

    Compliance-event subjects are one-way hashes. Event metadata is allowlisted by
    exclusion and size-bounded so prompts, legal text, secrets, and direct identifiers
    cannot be written through this service.
    """

    def __init__(self, store: ApiDatabaseStore) -> None:
        self.store = store

    def initialize(self) -> None:
        with self.store._connect() as conn:
            self.store._execute_script(
                conn,
                """
                CREATE TABLE IF NOT EXISTS consent_events (
                    event_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    consent_scope TEXT NOT NULL,
                    consent_text_version TEXT NOT NULL,
                    granted INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    country TEXT NOT NULL DEFAULT '',
                    purpose TEXT NOT NULL DEFAULT '',
                    captured_at TEXT NOT NULL,
                    expires_at TEXT,
                    previous_event_id TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_consent_events_user_scope_time
                ON consent_events(user_id, consent_scope, captured_at DESC);

                CREATE TABLE IF NOT EXISTS processing_restrictions (
                    user_id TEXT PRIMARY KEY,
                    restricted INTEGER NOT NULL DEFAULT 1,
                    reason_code TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    lifted_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS data_subject_requests (
                    request_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    completed_at TEXT,
                    result_manifest_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_dsar_user_requested
                ON data_subject_requests(user_id, requested_at DESC);

                CREATE TABLE IF NOT EXISTS compliance_events (
                    event_id TEXT PRIMARY KEY,
                    subject_ref TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    correlation_id TEXT NOT NULL DEFAULT '',
                    occurred_at TEXT NOT NULL,
                    previous_event_hash TEXT NOT NULL DEFAULT '',
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_compliance_subject_time
                ON compliance_events(subject_ref, occurred_at DESC);

                CREATE TABLE IF NOT EXISTS retention_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}'
                );
                """,
            )
            if not self.store.uses_postgres:
                self.store._execute(
                    conn,
                    """
                    CREATE TRIGGER IF NOT EXISTS compliance_events_no_update
                    BEFORE UPDATE ON compliance_events
                    BEGIN SELECT RAISE(ABORT, 'compliance_events is append-only'); END
                    """,
                )
                self.store._execute(
                    conn,
                    """
                    CREATE TRIGGER IF NOT EXISTS compliance_events_no_delete
                    BEFORE DELETE ON compliance_events
                    BEGIN SELECT RAISE(ABORT, 'compliance_events is append-only'); END
                    """,
                )
            conn.commit()

    def record_consent(
        self,
        *,
        user_id: str,
        scope: str,
        notice_version: str,
        granted: bool,
        source: str,
        country: str = "",
        purpose: str = "",
        session_id: str = "",
        captured_at: str | None = None,
        expires_at: str | None = None,
        correlation_id: str = "",
    ) -> ConsentEvent:
        normalized_scope = scope.strip().lower()
        if normalized_scope not in CONSENT_SCOPES:
            raise ValueError(f"Unsupported consent scope: {scope}")
        if not notice_version.strip():
            raise ValueError("Consent notice version is required")
        now = captured_at or _now_iso()
        event_id = str(uuid.uuid4())
        with self.store._connect() as conn:
            if self.store._fetchone(
                conn, "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ) is None:
                raise KeyError(f"User {user_id} not found")
            previous = self.store._fetchone(
                conn,
                """
                SELECT event_id FROM consent_events
                WHERE user_id = ? AND consent_scope = ?
                ORDER BY captured_at DESC, event_id DESC LIMIT 1
                """,
                (user_id, normalized_scope),
            )
            previous_event_id = str(previous[0]) if previous else None
            self.store._execute(
                conn,
                """
                INSERT INTO consent_events(
                    event_id, user_id, session_id, consent_scope, consent_text_version,
                    granted, source, country, purpose, captured_at, expires_at, previous_event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    user_id,
                    session_id.strip(),
                    normalized_scope,
                    notice_version.strip(),
                    1 if granted else 0,
                    source.strip().lower() or "api",
                    country.strip().upper(),
                    purpose.strip()[:250],
                    now,
                    expires_at,
                    previous_event_id,
                ),
            )
            conn.commit()
        self.record_event(
            user_id=user_id,
            event_type="consent",
            action="grant" if granted else "revoke",
            outcome="recorded",
            metadata={"scope": normalized_scope, "notice_version": notice_version.strip()},
            correlation_id=correlation_id,
        )
        return ConsentEvent(
            event_id=event_id,
            user_id=user_id,
            session_id=session_id.strip(),
            scope=normalized_scope,
            notice_version=notice_version.strip(),
            granted=granted,
            source=source.strip().lower() or "api",
            country=country.strip().upper(),
            purpose=purpose.strip()[:250],
            captured_at=now,
            expires_at=expires_at,
            previous_event_id=previous_event_id,
        )

    def list_consents(self, *, user_id: str) -> list[ConsentEvent]:
        with self.store._connect() as conn:
            rows = self.store._execute(
                conn,
                """
                SELECT event_id, user_id, session_id, consent_scope, consent_text_version,
                       granted, source, country, purpose, captured_at, expires_at, previous_event_id
                FROM consent_events WHERE user_id = ?
                ORDER BY captured_at DESC, event_id DESC
                """,
                (user_id,),
            ).fetchall()
        return [_row_to_consent_event(row) for row in rows]

    def has_active_consent(
        self, *, user_id: str, scope: str, notice_version: str | None = None
    ) -> bool:
        normalized_scope = scope.strip().lower()
        with self.store._connect() as conn:
            row = self.store._fetchone(
                conn,
                """
                SELECT granted, consent_text_version, expires_at
                FROM consent_events
                WHERE user_id = ? AND consent_scope = ?
                ORDER BY captured_at DESC, event_id DESC LIMIT 1
                """,
                (user_id, normalized_scope),
            )
        if row is None or not bool(row[0]):
            return False
        if notice_version is not None and str(row[1]) != notice_version:
            return False
        return row[2] is None or str(row[2]) > _now_iso()

    def set_processing_restriction(
        self,
        *,
        user_id: str,
        restricted: bool,
        reason_code: str,
        correlation_id: str = "",
    ) -> None:
        now = _now_iso()
        with self.store._connect() as conn:
            if self.store._fetchone(
                conn, "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ) is None:
                raise KeyError(f"User {user_id} not found")
            self.store._execute(
                conn,
                """
                INSERT INTO processing_restrictions(
                    user_id, restricted, reason_code, requested_at, lifted_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    restricted = excluded.restricted,
                    reason_code = excluded.reason_code,
                    requested_at = excluded.requested_at,
                    lifted_at = excluded.lifted_at
                """,
                (user_id, 1 if restricted else 0, reason_code.strip()[:80], now, None if restricted else now),
            )
            conn.commit()
        self.record_event(
            user_id=user_id,
            event_type="data_subject_right",
            action="restrict" if restricted else "lift_restriction",
            outcome="completed",
            metadata={"reason_code": reason_code.strip()[:80]},
            correlation_id=correlation_id,
        )

    def is_processing_restricted(self, *, user_id: str) -> bool:
        if not user_id.strip():
            return False
        with self.store._connect() as conn:
            row = self.store._fetchone(
                conn,
                "SELECT restricted FROM processing_restrictions WHERE user_id = ?",
                (user_id,),
            )
        return row is not None and bool(row[0])

    def record_event(
        self,
        *,
        user_id: str,
        event_type: str,
        action: str,
        outcome: str,
        metadata: Mapping[str, object] | None = None,
        correlation_id: str = "",
    ) -> str:
        event_id = str(uuid.uuid4())
        occurred_at = _now_iso()
        subject_ref = _subject_ref(user_id)
        sanitized = _sanitize_audit_metadata(metadata or {})
        metadata_json = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
        with self.store._connect() as conn:
            previous = self.store._fetchone(
                conn,
                "SELECT event_hash FROM compliance_events ORDER BY occurred_at DESC, event_id DESC LIMIT 1",
                (),
            )
            previous_hash = str(previous[0]) if previous else ""
            canonical = "|".join(
                (previous_hash, event_id, subject_ref, event_type, action, outcome, metadata_json, occurred_at)
            )
            event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            self.store._execute(
                conn,
                """
                INSERT INTO compliance_events(
                    event_id, subject_ref, event_type, action, outcome, metadata_json,
                    correlation_id, occurred_at, previous_event_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    subject_ref,
                    event_type.strip()[:80],
                    action.strip()[:80],
                    outcome.strip()[:80],
                    metadata_json,
                    correlation_id.strip()[:120],
                    occurred_at,
                    previous_hash,
                    event_hash,
                ),
            )
            conn.commit()
        return event_id

    def export_subject_data(self, *, user_id: str) -> dict[str, object]:
        with self.store._connect() as conn:
            user = self.store._fetchone(
                conn,
                """
                SELECT user_id, phone_number, email, first_name, last_name, full_name,
                       address, city, country, zip_code, tax_number, identity_card_number,
                       date_of_birth, social_security_number, created_at, role, is_enabled
                FROM users WHERE user_id = ?
                """,
                (user_id,),
            )
            if user is None:
                raise KeyError(f"User {user_id} not found")
            case_rows = self.store._execute(
                conn,
                "SELECT case_id, title, status, created_at, updated_at FROM cases WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            case_ids = [str(row[0]) for row in case_rows]
            documents: list[dict[str, object]] = []
            communications: list[dict[str, object]] = []
            citations: list[dict[str, object]] = []
            for case_id in case_ids:
                for row in self.store._execute(
                    conn,
                    """
                    SELECT doc_id, kind, version, storage_uri, original_filename,
                           processing_status, created_at FROM case_documents WHERE case_id = ?
                    """,
                    (case_id,),
                ).fetchall():
                    documents.append(self._document_manifest(case_id=case_id, row=row))
                for row in self.store._execute(
                    conn,
                    """
                    SELECT communication_id, channel, transcript_uri, summary, created_at
                    FROM case_communications WHERE case_id = ? ORDER BY created_at
                    """,
                    (case_id,),
                ).fetchall():
                    transcript = self._read_text_if_local(str(row[2])) if row[2] else None
                    communications.append(
                        {
                            "case_id": case_id,
                            "communication_id": str(row[0]),
                            "channel": str(row[1]),
                            "summary": str(row[3]),
                            "transcript": transcript,
                            "created_at": str(row[4]),
                        }
                    )
                for row in self.store._execute(
                    conn,
                    """
                    SELECT citation_id, source_type, source_id, source_url, title,
                           citation_label, law_number, section, effective_from,
                           court, ecli, file_number, decision_date, retrieval_tool, created_at
                    FROM case_citations WHERE case_id = ? ORDER BY created_at
                    """,
                    (case_id,),
                ).fetchall():
                    citations.append(
                        dict(
                            zip(
                                (
                                    "citation_id", "source_type", "source_id", "source_url", "title",
                                    "citation_label", "law_number", "section", "effective_from", "court",
                                    "ecli", "file_number", "decision_date", "retrieval_tool", "created_at",
                                ),
                                row,
                                strict=True,
                            )
                        )
                    )
            subscriptions = self.store._execute(
                conn,
                """
                SELECT subscription_id, plan_code, status, starts_at, ends_at, created_at, updated_at
                FROM user_subscriptions WHERE user_id = ? ORDER BY created_at
                """,
                (user_id,),
            ).fetchall()
            model_usage = self.store._execute(
                conn,
                """
                SELECT usage_id, case_id, task_type, provider, model, route_type,
                       input_tokens, cached_input_tokens, output_tokens, total_tokens,
                       estimated_cost_eur, status, fallback_reason, request_started_at,
                       request_completed_at, question_sha256, created_at
                FROM ai_model_usage_ledger WHERE user_id = ? ORDER BY created_at
                """,
                (user_id,),
            ).fetchall()
            dsar_rows = self.store._execute(
                conn,
                """
                SELECT request_id, request_type, status, requested_at, completed_at,
                       result_manifest_json FROM data_subject_requests
                WHERE user_id = ? ORDER BY requested_at
                """,
                (user_id,),
            ).fetchall()
            restriction = self.store._fetchone(
                conn,
                """
                SELECT restricted, reason_code, requested_at, lifted_at
                FROM processing_restrictions WHERE user_id = ?
                """,
                (user_id,),
            )
            compliance_rows = self.store._execute(
                conn,
                """
                SELECT event_id, event_type, action, outcome, metadata_json,
                       correlation_id, occurred_at, previous_event_hash, event_hash
                FROM compliance_events WHERE subject_ref = ? ORDER BY occurred_at
                """,
                (_subject_ref(user_id),),
            ).fetchall()
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "generated_at": _now_iso(),
            "user": dict(
                zip(
                    (
                        "user_id", "phone_number", "email", "first_name", "last_name", "full_name",
                        "address", "city", "country", "zip_code", "tax_number", "identity_card_number",
                        "date_of_birth", "social_security_number", "created_at", "role", "is_enabled",
                    ),
                    user,
                    strict=True,
                )
            ),
            "cases": [
                dict(zip(("case_id", "title", "status", "created_at", "updated_at"), row, strict=True))
                for row in case_rows
            ],
            "documents_manifest": documents,
            "messages_and_communications": communications,
            "citations": citations,
            "subscriptions": [
                dict(
                    zip(
                        ("subscription_id", "plan_code", "status", "starts_at", "ends_at", "created_at", "updated_at"),
                        row,
                        strict=True,
                    )
                )
                for row in subscriptions
            ],
            "consent_events": [event.__dict__ for event in self.list_consents(user_id=user_id)],
            "processing_restriction": (
                dict(
                    zip(
                        ("restricted", "reason_code", "requested_at", "lifted_at"),
                        restriction,
                        strict=True,
                    )
                )
                if restriction is not None
                else None
            ),
            "data_subject_requests": [
                {
                    "request_id": str(row[0]),
                    "request_type": str(row[1]),
                    "status": str(row[2]),
                    "requested_at": str(row[3]),
                    "completed_at": str(row[4]) if row[4] is not None else None,
                    "result_manifest": _safe_json_object(row[5]),
                }
                for row in dsar_rows
            ],
            "model_usage_logs": [
                dict(
                    zip(
                        (
                            "usage_id", "case_id", "task_type", "provider", "model", "route_type",
                            "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens",
                            "estimated_cost_eur", "status", "fallback_reason", "request_started_at",
                            "request_completed_at", "question_sha256", "created_at",
                        ),
                        row,
                        strict=True,
                    )
                )
                for row in model_usage
            ],
            "compliance_event_log": [
                {
                    "event_id": str(row[0]),
                    "event_type": str(row[1]),
                    "action": str(row[2]),
                    "outcome": str(row[3]),
                    "metadata": _safe_json_object(row[4]),
                    "correlation_id": str(row[5]),
                    "occurred_at": str(row[6]),
                    "previous_event_hash": str(row[7]),
                    "event_hash": str(row[8]),
                }
                for row in compliance_rows
            ],
        }
        self.record_event(
            user_id=user_id,
            event_type="data_subject_right",
            action="export",
            outcome="completed",
            metadata={"case_count": len(case_rows), "document_count": len(documents)},
        )
        return payload

    def erase_subject_data(
        self, *, user_id: str, mode: str, correlation_id: str = ""
    ) -> dict[str, object]:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"delete", "anonymize"}:
            raise ValueError("DSAR erasure mode must be delete or anonymize")
        now = _now_iso()
        request_id = str(uuid.uuid4())
        with self.store._connect() as conn:
            user = self.store._fetchone(
                conn, "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            )
            if user is None:
                raise KeyError(f"User {user_id} not found")
            self.store._execute(
                conn,
                """
                INSERT INTO data_subject_requests(
                    request_id, user_id, request_type, status, requested_at, completed_at, result_manifest_json
                ) VALUES (?, ?, ?, 'processing', ?, NULL, '{}')
                """,
                (request_id, user_id, normalized_mode, now),
            )
            case_rows = self.store._execute(
                conn, "SELECT case_id FROM cases WHERE user_id = ?", (user_id,)
            ).fetchall()
            case_ids = [str(row[0]) for row in case_rows]
            storage_uris: list[str] = []
            for case_id in case_ids:
                storage_uris.extend(
                    str(row[0])
                    for row in self.store._execute(
                        conn, "SELECT storage_uri FROM case_documents WHERE case_id = ?", (case_id,)
                    ).fetchall()
                    if row[0]
                )
                storage_uris.extend(
                    str(row[0])
                    for row in self.store._execute(
                        conn, "SELECT transcript_uri FROM case_communications WHERE case_id = ?", (case_id,)
                    ).fetchall()
                    if row[0]
                )
            deleted_rows = 0
            for case_id in case_ids:
                for table in (
                    "case_document_deletion_events",
                    "case_citations",
                    "case_document_chunks",
                    "case_document_contents",
                    "document_shares",
                    "case_documents",
                    "case_communications",
                    "case_catalog_events",
                    "case_catalog_selections",
                ):
                    cursor = self.store._execute(conn, f"DELETE FROM {table} WHERE case_id = ?", (case_id,))
                    deleted_rows += max(int(cursor.rowcount or 0), 0)
                self.store._execute(
                    conn,
                    "UPDATE cases SET title = 'Anonymized case', status = 'deleted', updated_at = ? WHERE case_id = ?",
                    (now, case_id),
                )
            for table in (
                "device_auth_tokens",
                "mcp_oauth_authorization_codes",
                "mcp_otp_verifications",
                "user_mfa_settings",
                "mfa_login_challenges",
                "company_users",
                "ai_model_group_users",
                "ai_model_user_overrides",
                "user_subscriptions",
            ):
                cursor = self.store._execute(conn, f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
                deleted_rows += max(int(cursor.rowcount or 0), 0)
            subject_suffix = _subject_ref(user_id)[:20]
            self.store._execute(
                conn,
                """
                UPDATE users SET
                    phone_number = NULL, email = ?, first_name = NULL, last_name = NULL,
                    full_name = 'Deleted user', address = NULL, city = NULL, country = NULL,
                    zip_code = NULL, tax_number = NULL, identity_card_number = NULL,
                    date_of_birth = NULL, social_security_number = NULL,
                    data_processing_consent_at = NULL, data_processing_consent_version = NULL,
                    mcp_api_key_hash = NULL, mcp_api_key_expires_at = NULL,
                    password_hash = ?, is_enabled = 0
                WHERE user_id = ?
                """,
                (
                    f"deleted+{subject_suffix}@invalid.local",
                    hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                    user_id,
                ),
            )
            result = {
                "request_id": request_id,
                "mode": normalized_mode,
                "cases_anonymized": len(case_ids),
                "rows_erased": deleted_rows,
                "files_erased": 0,
            }
            self.store._execute(
                conn,
                """
                UPDATE data_subject_requests
                SET status = 'completed', completed_at = ?, result_manifest_json = ?
                WHERE request_id = ?
                """,
                (now, json.dumps(result, sort_keys=True), request_id),
            )
            conn.commit()
        files_erased = sum(1 for storage_uri in storage_uris if self._delete_local_artifact(storage_uri))
        result["files_erased"] = files_erased
        with self.store._connect() as conn:
            self.store._execute(
                conn,
                "UPDATE data_subject_requests SET result_manifest_json = ? WHERE request_id = ?",
                (json.dumps(result, sort_keys=True), request_id),
            )
            conn.commit()
        self.record_event(
            user_id=user_id,
            event_type="data_subject_right",
            action=normalized_mode,
            outcome="completed",
            metadata={"case_count": len(case_ids), "file_count": files_erased},
            correlation_id=correlation_id,
        )
        return result

    def run_retention(self, *, now: datetime | None = None) -> RetentionRunResult:
        current = now or datetime.now(timezone.utc)
        started_at = current.isoformat().replace("+00:00", "Z")
        run_id = str(uuid.uuid4())
        deleted: dict[str, int] = {}
        deleted_files = 0
        with self.store._connect() as conn:
            self.store._execute(
                conn,
                "INSERT INTO retention_runs(run_id, started_at, status) VALUES (?, ?, 'running')",
                (run_id, started_at),
            )
            expired_share_ids = [
                str(row[0])
                for row in self.store._execute(
                    conn, "SELECT share_id FROM document_shares WHERE expires_at < ?", (started_at,)
                ).fetchall()
            ]
            for share_id in expired_share_ids:
                self.store._execute(
                    conn, "DELETE FROM document_share_audit_events WHERE share_id = ?", (share_id,)
                )
                self.store._execute(conn, "DELETE FROM document_shares WHERE share_id = ?", (share_id,))
            deleted["expired_document_shares"] = len(expired_share_ids)
            for table in ("registration_codes", "device_auth_tokens", "mcp_oauth_authorization_codes", "mfa_login_challenges"):
                cursor = self.store._execute(conn, f"DELETE FROM {table} WHERE expires_at < ?", (started_at,))
                deleted[table] = max(int(cursor.rowcount or 0), 0)
            audit_cutoff = (current - timedelta(days=365)).isoformat().replace("+00:00", "Z")
            cursor = self.store._execute(
                conn, "DELETE FROM ai_model_usage_ledger WHERE created_at < ?", (audit_cutoff,)
            )
            deleted["ai_model_usage_ledger"] = max(int(cursor.rowcount or 0), 0)
            content_cutoff = (current - timedelta(days=30)).isoformat().replace("+00:00", "Z")
            expired_cases = [
                str(row[0])
                for row in self.store._execute(
                    conn,
                    "SELECT case_id FROM cases WHERE status = 'deleted' AND updated_at < ?",
                    (content_cutoff,),
                ).fetchall()
            ]
            for case_id in expired_cases:
                uris = self.store._execute(
                    conn,
                    "SELECT storage_uri FROM case_documents WHERE case_id = ? UNION ALL SELECT transcript_uri FROM case_communications WHERE case_id = ?",
                    (case_id, case_id),
                ).fetchall()
                deleted_files += sum(
                    1 for row in uris if row[0] and self._delete_local_artifact(str(row[0]))
                )
                for table in (
                    "case_document_deletion_events", "case_citations", "case_document_chunks",
                    "case_document_contents", "document_shares", "case_documents", "case_communications",
                    "case_catalog_events", "case_catalog_selections",
                ):
                    self.store._execute(conn, f"DELETE FROM {table} WHERE case_id = ?", (case_id,))
            deleted["deleted_case_content"] = len(expired_cases)
            completed_at = _now_iso()
            result_json = json.dumps({"deleted_rows": deleted, "deleted_files": deleted_files}, sort_keys=True)
            self.store._execute(
                conn,
                "UPDATE retention_runs SET completed_at = ?, status = 'completed', result_json = ? WHERE run_id = ?",
                (completed_at, result_json, run_id),
            )
            conn.commit()
        self.record_event(
            user_id="system",
            event_type="retention",
            action="enforce_policy",
            outcome="completed",
            metadata={"run_id": run_id, "deleted_file_count": deleted_files},
        )
        return RetentionRunResult(run_id, started_at, completed_at, deleted, deleted_files)

    def _document_manifest(self, *, case_id: str, row: tuple[object, ...]) -> dict[str, object]:
        payload: bytes | None = None
        try:
            payload = self.store.read_storage_bytes(storage_uri=str(row[3]))
        except (FileNotFoundError, OSError, ValueError):
            pass
        return {
            "case_id": case_id,
            "doc_id": str(row[0]),
            "kind": str(row[1]),
            "version": int(str(row[2])),
            "original_filename": str(row[4]),
            "processing_status": str(row[5]),
            "created_at": str(row[6]),
            "size_bytes": len(payload) if payload is not None else None,
            "sha256": hashlib.sha256(payload).hexdigest() if payload is not None else None,
        }

    def _read_text_if_local(self, storage_uri: str) -> str | None:
        try:
            return self.store.read_storage_text(storage_uri=storage_uri)
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _delete_local_artifact(self, storage_uri: str) -> bool:
        try:
            path = self.store._resolve_storage_path(storage_uri).resolve()
            root = self.store.blob_root.resolve()
            if not path.is_relative_to(root) or not path.is_file():
                return False
            path.unlink()
            return True
        except (FileNotFoundError, OSError, ValueError):
            return False


def build_ai_transparency_metadata(
    *,
    provider: str,
    model: str,
    generated_at: str | None = None,
    source_provenance: Sequence[Mapping[str, object]] | None = None,
    tool_provenance: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "ai_generated": True,
        "model_provider": provider.strip() or "unresolved",
        "model_name": model.strip() or "unresolved",
        "generated_at": generated_at or _now_iso(),
        "limitations_notice": (
            "AI output may be inaccurate, incomplete, or outdated and is not a final legal decision."
        ),
        "human_review_recommended": True,
        "source_provenance": [dict(item) for item in source_provenance or []],
        "tool_provenance": [dict(item) for item in tool_provenance or []],
    }


def _row_to_consent_event(row: tuple[object, ...]) -> ConsentEvent:
    return ConsentEvent(
        event_id=str(row[0]),
        user_id=str(row[1]),
        session_id=str(row[2]),
        scope=str(row[3]),
        notice_version=str(row[4]),
        granted=bool(row[5]),
        source=str(row[6]),
        country=str(row[7]),
        purpose=str(row[8]),
        captured_at=str(row[9]),
        expires_at=str(row[10]) if row[10] is not None else None,
        previous_event_id=str(row[11]) if row[11] is not None else None,
    )


def _subject_ref(user_id: str) -> str:
    return hashlib.sha256(f"jurisdigta-compliance:{user_id}".encode("utf-8")).hexdigest()


def _sanitize_audit_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for raw_key, value in metadata.items():
        key = str(raw_key).strip().lower()[:80]
        if not key or any(part in key for part in _PROHIBITED_AUDIT_KEY_PARTS):
            continue
        if isinstance(value, bool | int | float) or value is None:
            sanitized[key] = value
        elif isinstance(value, str):
            sanitized[key] = value.strip()[:160]
        elif isinstance(value, (list, tuple)):
            sanitized[key] = [str(item)[:80] for item in value[:20]]
    return sanitized


def _safe_json_object(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
