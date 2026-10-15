"""Fail-closed retention execution and retryable local file cleanup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .api_db import ApiDatabaseStore
from .privacy import PrivacyDenied, utcnow


def retention_candidates(store: ApiDatabaseStore, policy: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    with store._connect() as conn:
        for status, key in (("completed", "completed_case_days"), ("deleted", "deleted_case_days")):
            days = policy.get(key)
            if days is None:
                continue
            if isinstance(days, bool) or not isinstance(days, int) or days < 1:
                raise ValueError(f"{key} must be a positive integer or null")
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            rows = store._execute(conn, "SELECT case_id, user_id FROM cases WHERE lower(status) = ? AND updated_at < ? AND NOT EXISTS (SELECT 1 FROM privacy_subject_state p WHERE p.user_id = cases.user_id AND p.legal_hold = 1)", (status, cutoff)).fetchall()
            candidates.extend((str(row[0]), str(row[1])) for row in rows)
    return candidates


def require_approved_policy(policy: dict[str, Any]) -> None:
    if policy.get("approved") is not True or not policy.get("owner_approval_reference"):
        raise PrivacyDenied("retention_policy_requires_owner_approval")


def purge_case(store: ApiDatabaseStore, case_id: str, user_id: str) -> bool:
    """Queue files transactionally with row removal; cleanup can be retried."""
    with store._connect() as conn:
        row = store._fetchone(conn, "SELECT user_id FROM cases WHERE case_id = ?", (case_id,))
        if row is None:
            return False
        if row[0] != user_id:
            raise PrivacyDenied("case_ownership_mismatch")
        hold = store._fetchone(conn, "SELECT legal_hold FROM privacy_subject_state WHERE user_id = ?", (user_id,))
        if hold and hold[0]:
            raise PrivacyDenied("legal_hold_requires_owner_resolution")
        uris = store._execute(conn, "SELECT storage_uri FROM case_documents WHERE case_id = ? UNION SELECT transcript_uri FROM case_communications WHERE case_id = ? AND transcript_uri IS NOT NULL", (case_id, case_id)).fetchall()
        for uri in uris:
            store._execute(conn, "INSERT INTO privacy_file_cleanup VALUES (?, ?, ?, ?)", (str(uuid4()), uri[0], "pending", utcnow()))
        # Model usage totals remain for billing; erase associated content and links.
        store._execute(conn, "UPDATE ai_model_usage_ledger SET user_id = '', subscription_id = '', case_id = '', session_id = '', question_id = '', question_preview = '', question_sha256 = '', answer_id = '', audit_metadata_json = '{}' WHERE case_id = ?", (case_id,))
        store._execute(conn, "DELETE FROM privacy_ai_artifacts WHERE case_id = ?", (case_id,))
        store._execute(conn, "DELETE FROM case_speech_overrides WHERE case_id = ?", (case_id,))
        store._execute(conn, "DELETE FROM cases WHERE case_id = ? AND user_id = ?", (case_id, user_id))
    return True


def cleanup_files(store: ApiDatabaseStore) -> dict[str, int]:
    removed = 0
    pending = 0
    with store._connect() as conn:
        rows = store._execute(conn, "SELECT cleanup_id, storage_uri FROM privacy_file_cleanup WHERE status = 'pending'", ()).fetchall()
    for cleanup_id, uri in rows:
        with store._connect() as conn:
            referenced = store._fetchone(conn, "SELECT 1 FROM case_documents WHERE storage_uri = ? UNION SELECT 1 FROM case_communications WHERE transcript_uri = ?", (uri, uri))
        if referenced or store.storage_option != "local":
            pending += 1
            continue
        try:
            target = store._resolve_storage_path(str(uri))
            if target == store.blob_root.resolve() or not target.name:
                raise ValueError("Invalid cleanup target")
            target.unlink(missing_ok=True)
        except (OSError, ValueError):
            pending += 1
            continue
        with store._connect() as conn:
            store._execute(conn, "DELETE FROM privacy_file_cleanup WHERE cleanup_id = ?", (cleanup_id,))
        removed += 1
    return {"files_removed": removed, "files_pending": pending}
