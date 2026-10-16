"""Versioned privacy controls. Policy denial never includes submitted content."""
from __future__ import annotations

from collections.abc import Sequence, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from .api_db import ApiDatabaseStore
    from .llm.base import LLMClient
    from .llm.turn_contracts import AgentTurnContext
    from .schemas import Document, Message

CONSENT_VERSION = "389-v1"
CONSENT_SCOPES = {
    "external_models": "Send necessary case content to an approved external AI provider.",
    "external_checks": "Send necessary case facts to external verification tools; per-run approval also applies.",
    "marketing": "Receive optional marketing communications; service messages are separate.",
    "sensitive_processing": "Process necessary sensitive case data where consent is the approved lawful condition.",
}
LIMITATIONS = "AI output may be inaccurate, incomplete or outdated. Verify sources and obtain human legal review before legally consequential actions."
_SUBJECT: ContextVar[tuple[PrivacyControls, str] | None] = ContextVar("privacy_subject", default=None)


class PrivacyDenied(PermissionError):
    """Stable reason code safe for API responses and operational logs."""


def privacy_problem(reason: str) -> dict[str, str]:
    if reason.startswith("consent_required:"):
        message = "This action needs your current consent. Review Privacy controls in My Profile before continuing."
    elif reason == "processing_restricted":
        message = "Processing is restricted for your account. Review Privacy controls in My Profile or contact the privacy team."
    else:
        message = "This action is blocked by your account's privacy policy. Sign in or contact the privacy team."
    return {"code": reason.split(":", 1)[0], "message": message}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_privacy(store: ApiDatabaseStore) -> None:
    root = Path(__file__).resolve().parents[2]
    asset = ("migrations/389_privacy_controls.sql" if store.uses_postgres else "privacy_schema.sql")
    script = (root / "databases" / "api" / asset).read_text(encoding="utf-8")
    with store._connect() as conn:
        required = {"privacy_consent_events", "privacy_subject_state", "privacy_requests", "privacy_compliance_events", "privacy_ai_artifacts", "privacy_file_cleanup"}
        if store.uses_postgres:
            tables = {str(row[0]) for row in store._execute(conn, "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()", ()).fetchall()}
        else:
            tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        if required <= tables:
            return
        if isinstance(conn, sqlite3.Connection):
            conn.executescript(script)
        else:
            conn.execute(script)


class PrivacyControls:
    def __init__(self, store: ApiDatabaseStore) -> None:
        self.store = store

    def event(self, event_type: str, outcome: str, *, count: int = 0) -> str:
        with self.store._connect() as conn:
            return self._event(conn, event_type, outcome, count=count)

    def _event(self, conn: Any, event_type: str, outcome: str, *, count: int = 0) -> str:
        # No subject identifiers, prompts, filenames, caller-supplied metadata or secrets.
        if event_type not in {"consent", "restriction", "dsar_export", "dsar_request", "dsar_review", "retention", "model_response", "policy_denial", "legal_hold"}:
            raise ValueError("Unknown compliance event type")
        if outcome not in {"granted", "revoked", "restricted", "released", "completed", "pending", "approved", "rejected", "blocked", "dry_run", "held"}:
            raise ValueError("Unknown compliance outcome")
        event_id = str(uuid4())
        self.store._execute(conn, "INSERT INTO privacy_compliance_events VALUES (?, ?, ?, ?, ?)",
                            (event_id, event_type, outcome, utcnow(), json.dumps({"count": max(0, count)})))
        return event_id

    def consent(self, user_id: str, scope: str, granted: bool, *, version: str, country: str = "") -> str:
        if scope not in CONSENT_SCOPES or version != CONSENT_VERSION:
            raise ValueError("Consent scope or notice version is not current")
        self.store.get_user(user_id=user_id)
        event_id = str(uuid4())
        with self.store._connect() as conn:
            self.store._execute(conn, "INSERT INTO privacy_consent_events(event_id, user_id, scope, text_version, granted, captured_at, source, country) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (event_id, user_id, scope, version, int(granted), utcnow(), "authenticated_api", country[:2].upper()))
            self._event(conn, "consent", "granted" if granted else "revoked")
        return event_id

    def has_consent(self, user_id: str, scope: str) -> bool:
        if scope not in CONSENT_SCOPES:
            return False
        with self.store._connect() as conn:
            row = self.store._fetchone(conn, "SELECT granted, text_version FROM privacy_consent_events WHERE user_id = ? AND scope = ? ORDER BY sequence_id DESC LIMIT 1", (user_id, scope))
        return bool(row and row[0] == 1 and row[1] == CONSENT_VERSION)

    def state(self, user_id: str) -> dict[str, bool]:
        with self.store._connect() as conn:
            row = self.store._fetchone(conn, "SELECT restricted, legal_hold, sensitive_consent_required FROM privacy_subject_state WHERE user_id = ?", (user_id,))
        return {"restricted": bool(row and row[0]), "legal_hold": bool(row and row[1]), "sensitive_consent_required": bool(row and row[2])}

    def set_policy(self, user_id: str, *, legal_hold: bool, sensitive_consent_required: bool) -> None:
        self.store.get_user(user_id=user_id)
        with self.store._connect() as conn:
            self.store._execute(conn, "INSERT INTO privacy_subject_state(user_id, restricted, legal_hold, sensitive_consent_required, updated_at) VALUES (?, 0, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET legal_hold = excluded.legal_hold, sensitive_consent_required = excluded.sensitive_consent_required, updated_at = excluded.updated_at",
                                (user_id, int(legal_hold), int(sensitive_consent_required), utcnow()))
        self.event("legal_hold", "held" if legal_hold else "released")

    def restrict(self, user_id: str, restricted: bool) -> None:
        self.store.get_user(user_id=user_id)
        with self.store._connect() as conn:
            self.store._execute(conn, "INSERT INTO privacy_subject_state(user_id, restricted, legal_hold, updated_at) VALUES (?, ?, 0, ?) ON CONFLICT(user_id) DO UPDATE SET restricted = excluded.restricted, updated_at = excluded.updated_at",
                                (user_id, int(restricted), utcnow()))
            self._event(conn, "restriction", "restricted" if restricted else "released")

    def require_processing(self, user_id: str, scope: str | None = None) -> None:
        if not user_id:
            raise PrivacyDenied("authenticated_subject_required")
        if not self.store.get_user(user_id=user_id).is_enabled:
            raise PrivacyDenied("subject_disabled")
        state = self.state(user_id)
        if state["restricted"]:
            self.event("policy_denial", "blocked")
            raise PrivacyDenied("processing_restricted")
        if state["sensitive_consent_required"] and not self.has_consent(user_id, "sensitive_processing"):
            self.event("policy_denial", "blocked")
            raise PrivacyDenied("consent_required:sensitive_processing:389-v1")
        if scope and not self.has_consent(user_id, scope):
            self.event("policy_denial", "blocked")
            raise PrivacyDenied(f"consent_required:{scope}:{CONSENT_VERSION}")

    def request_erasure(self, user_id: str, operation: str) -> str:
        if operation not in {"delete", "anonymize"}:
            raise ValueError("Unsupported privacy request")
        self.restrict(user_id, True)
        request_id = str(uuid4())
        now = utcnow()
        with self.store._connect() as conn:
            self.store._execute(conn, "INSERT INTO privacy_requests VALUES (?, ?, ?, ?, ?, ?)",
                                (request_id, user_id, operation, "pending_review", now, now))
        self.event("dsar_request", "pending")
        return request_id

    def review_erasure(self, request_id: str, approved: bool) -> str:
        with self.store._connect() as conn:
            row = self.store._fetchone(conn, "SELECT user_id, status FROM privacy_requests WHERE request_id = ?", (request_id,))
            if not row:
                raise KeyError("privacy_request_not_found")
            if row[1] != "pending_review":
                raise ValueError("Request has already been reviewed")
            hold = self.store._fetchone(conn, "SELECT legal_hold FROM privacy_subject_state WHERE user_id = ?", (row[0],))
            if approved and hold and hold[0]:
                raise PrivacyDenied("legal_hold_requires_owner_resolution")
            status = "approved_pending_execution" if approved else "rejected"
            updated = self.store._execute(conn, "UPDATE privacy_requests SET status = ?, updated_at = ? WHERE request_id = ? AND status = 'pending_review'", (status, utcnow(), request_id))
            if updated.rowcount != 1:
                raise ValueError("Request has already been reviewed")
            self._event(conn, "dsar_review", "approved" if approved else "rejected")
        return status

    def requests(self, user_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT request_id, user_id, operation, status, created_at, updated_at FROM privacy_requests"
        params: tuple[Any, ...] = ()
        if user_id is not None:
            query += " WHERE user_id = ?"
            params = (user_id,)
        with self.store._connect() as conn:
            cursor = self.store._execute(conn, query + " ORDER BY created_at", params)
            names = [item[0] for item in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]

    def record_artifact(self, artifact_id: str, case_id: str, metadata: dict[str, Any]) -> None:
        with self.store._connect() as conn:
            self.store._execute(conn, "INSERT INTO privacy_ai_artifacts VALUES (?, ?, ?) ON CONFLICT(artifact_id) DO UPDATE SET metadata_json = excluded.metadata_json",
                                (artifact_id, case_id, json.dumps(metadata)))

    def artifact(self, artifact_id: str, created_at: str) -> dict[str, Any]:
        with self.store._connect() as conn:
            row = self.store._fetchone(conn, "SELECT metadata_json FROM privacy_ai_artifacts WHERE artifact_id = ?", (artifact_id,))
        return json.loads(row[0]) if row else transparency(generated_at=created_at)

    def export(self, user_id: str) -> dict[str, Any]:
        """Export personal records, excluding authentication/processor credentials.

        Uses schema ownership columns, including derived workflow/diagnostic rows.
        Files and out-of-database surfaces are enumerated separately by the API.
        """
        self.store.get_user(user_id=user_id)
        with self.store._connect() as conn:
            if self.store.uses_postgres:
                metadata = self.store._execute(conn, "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = current_schema()", ()).fetchall()
            else:
                tables = self.store._execute(conn, "SELECT name FROM sqlite_master WHERE type = 'table'", ()).fetchall()
                metadata = [(table[0], col[1]) for table in tables for col in self.store._execute(conn, f'PRAGMA table_info("{table[0]}")', ()).fetchall()]
            columns: dict[str, set[str]] = {}
            for table, column in metadata:
                if str(table).replace("_", "").isalnum():
                    columns.setdefault(str(table), set()).add(str(column))
            data: dict[str, list[dict[str, Any]]] = {}
            for table, fields in columns.items():
                if table in {"device_auth_tokens", "registration_codes", "mcp_pending_signups", "mcp_oauth_authorization_codes", "mcp_otp_verifications", "user_mfa_settings", "mfa_login_challenges", "ai_model_credentials", "provider_credentials", "privacy_compliance_events"}:
                    continue
                clauses: list[str] = []
                params_list: list[str] = []
                for field in ("user_id", "sender_user_id", "uploaded_by_user_id", "actor_user_id"):
                    if field in fields:
                        clauses.append(f'"{field}" = ?')
                        params_list.append(user_id)
                if "case_id" in fields and table != "cases":
                    clauses.append('case_id IN (SELECT case_id FROM cases WHERE user_id = ?)')
                    params_list.append(user_id)
                if "session_id" in fields and "debug_trace_sessions" in columns and table != "debug_trace_sessions":
                    clauses.append('session_id IN (SELECT session_id FROM debug_trace_sessions WHERE user_id = ?)')
                    params_list.append(user_id)
                if not clauses:
                    continue
                cursor = self.store._execute(conn, f'SELECT * FROM "{table}" WHERE ' + " OR ".join(clauses), tuple(params_list))
                names = [item[0] for item in cursor.description]
                data[table] = [sanitize_export(dict(zip(names, row))) for row in cursor.fetchall()]
        self.event("dsar_export", "completed", count=sum(map(len, data.values())))
        return {"format_version": "389-v1", "generated_at": utcnow(), "records": data,
                "external_surfaces": ["email outbox and delivered mail", "operational logs and telemetry", "backups", "external processors"],
                "notice": "External surfaces require the operator workflow; this archive does not claim those systems are fully exported or erased."}


def sanitize_export(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_export(item) for key, item in value.items()
                if not any(part in key.lower() for part in ("password", "token", "secret", "credential", "api_key", "_hash", "storage_uri", "transcript_uri"))}
    if isinstance(value, (list, tuple)):
        return [sanitize_export(item) for item in value]
    if isinstance(value, str) and value[:1] in {"{", "["}:
        try:
            return sanitize_export(json.loads(value))
        except ValueError:
            return value
    if isinstance(value, bytes):
        return "[binary excluded]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def transparency(provider: str | None = None, model: str | None = None, *, generated_at: str | None = None) -> dict[str, Any]:
    return {"ai_generated": True, "model_provider": provider, "model_name": model,
            "generated_at": generated_at or utcnow(), "limitations_notice": LIMITATIONS,
            "human_review_recommended": True,
            "source_provenance": [], "source_provenance_status": "unavailable",
            "provenance_status": "recorded" if provider and model else "unavailable"}


class PrivacyCheckedClient:
    """Recheck restriction and revocation before every call on a reused route."""
    def __init__(self, client: LLMClient, controls: PrivacyControls, user_id: str, external: bool) -> None:
        self.client = client
        self.controls = controls
        self.user_id = user_id
        self.external = external

    def complete(self, agent_name: str, system_prompt: str, conversation: Sequence[Message], documents: Sequence[Document]) -> str:
        self.controls.require_processing(self.user_id, "external_models" if self.external else None)
        from .llm.base import private_model_io
        with private_model_io(), privacy_scope(self.controls, self.user_id):
            result = self.client.complete(agent_name, system_prompt, conversation, documents)
        self.controls.event("model_response", "completed")
        return result

    def complete_turn(self, agent_name: str, context: AgentTurnContext) -> str:
        """Typed calls must recheck live consent, never bypass via __getattr__."""
        self.controls.require_processing(self.user_id, "external_models" if self.external else None)
        from .llm.base import private_model_io
        with private_model_io(), privacy_scope(self.controls, self.user_id):
            result: str = getattr(self.client, "complete_turn")(agent_name, context)
        self.controls.event("model_response", "completed")
        return result

    def complete_tool_step(self, context: AgentTurnContext, history: Any, definitions: Any,
                           remaining_seconds: float, *, require_tool: bool = False,
                           initial_tool_id: str | None = None) -> Any:
        self.controls.require_processing(self.user_id, "external_models" if self.external else None)
        from .llm.base import private_model_io
        with private_model_io(), privacy_scope(self.controls, self.user_id):
            return getattr(self.client, "complete_tool_step")(context, history, definitions, remaining_seconds,
                                                              require_tool=require_tool,
                                                              initial_tool_id=initial_tool_id)

    def authorize_internal_tool(self) -> bool:
        self.controls.require_processing(self.user_id)
        return True

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)


@contextmanager
def privacy_scope(controls: PrivacyControls, user_id: str) -> Iterator[None]:
    token = _SUBJECT.set((controls, user_id))
    try:
        yield
    finally:
        _SUBJECT.reset(token)


def require_external_check() -> None:
    require_external_processing("external_checks")


def require_external_processing(scope: str) -> None:
    subject = _SUBJECT.get()
    if subject is None:
        raise PrivacyDenied("external_check_requires_authenticated_subject")
    subject[0].require_processing(subject[1], scope)
