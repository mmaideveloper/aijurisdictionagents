"""Consent-gated exports. Authorization is rechecked at execution and consumption."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator
from uuid import uuid4

from .api_db import ApiDatabaseStore


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExportDenied(PermissionError):
    pass


class CaseExports:
    def __init__(self, store: ApiDatabaseStore) -> None:
        self.store = store

    def admin_allowed(self, admin_id: str, conn: Any) -> bool:
        row = self.store._fetchone(conn, "SELECT u.is_enabled, u.role FROM users u JOIN case_export_permissions p ON p.user_id = u.user_id WHERE u.user_id = ?" + (" FOR SHARE OF u, p" if self.store.uses_postgres else ""), (admin_id,))
        return bool(row and row[0] and row[1] == "admin")

    def event(self, conn: Any, request_id: str, actor: str, action: str) -> None:
        self.store._execute(conn, "INSERT INTO case_export_events VALUES (?, ?, ?, ?, ?)", (str(uuid4()), request_id, actor, action, now()))

    @contextmanager
    def locked(self, request_id: str) -> Iterator[tuple[Any, Any]]:
        with self.store._connect() as conn:
            if not self.store.uses_postgres:
                conn.execute("BEGIN IMMEDIATE")
            suffix = " FOR UPDATE" if self.store.uses_postgres else ""
            row = self.store._fetchone(conn, "SELECT request_id, admin_id, purpose, created_at, expires_at, status, artifact_expires_at, artifact, case_count FROM case_export_requests WHERE request_id = ?" + suffix, (request_id,))
            if row is None:
                raise ExportDenied("Export unavailable")
            yield conn, row

    def request(self, admin_id: str, case_ids: list[str], purpose: str) -> str:
        ids = sorted(set(case_ids))
        if not ids or len(ids) > 50 or not 3 <= len(purpose.strip()) <= 500:
            raise ValueError("Select 1-50 cases and provide an export purpose")
        if self.store.case_cipher is None:
            raise ExportDenied("Encrypted export storage required")
        with self.store._connect() as conn:
            if not self.admin_allowed(admin_id, conn):
                raise ExportDenied("Dedicated case.export permission required")
        cases = [self.store.get_case(case_id=case_id) for case_id in ids]
        if any(case.status == "deleted" for case in cases):
            raise ExportDenied("Export unavailable")
        request_id = str(uuid4())
        encrypted_purpose = self.store.encrypt_case_text(ids[0], "export-purpose:" + request_id, purpose.strip())
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        with self.store._connect() as conn:
            if not self.admin_allowed(admin_id, conn):
                raise ExportDenied("Dedicated case.export permission required")
            self.store._execute(conn, "INSERT INTO case_export_requests(request_id, admin_id, purpose, created_at, expires_at, status, case_count) VALUES (?, ?, ?, ?, ?, 'pending', ?)", (request_id, admin_id, encrypted_purpose, now(), expires, len(ids)))
            for case in cases:
                self.store._execute(conn, "INSERT INTO case_export_grants(request_id, case_id, owner_id) VALUES (?, ?, ?)", (request_id, case.case_id, case.user_id))
                self.store._execute(conn, "INSERT INTO case_export_snapshots VALUES (?, ?, ?)", (request_id, case.case_id, case.updated_at.isoformat() if hasattr(case.updated_at, "isoformat") else str(case.updated_at)))
            self.event(conn, request_id, admin_id, "requested")
        return request_id

    def decide(self, request_id: str, owner_id: str, decision: str) -> None:
        if decision not in {"approved", "denied", "revoked"}:
            raise ValueError("Invalid consent decision")
        with self.locked(request_id) as (conn, row):
            grants = self.store._execute(conn, "SELECT decision FROM case_export_grants WHERE request_id = ? AND owner_id = ?", (request_id, owner_id)).fetchall()
            if not grants or row[4] <= now() or row[5] not in {"pending", "ready"}:
                raise ExportDenied("Export request is unavailable or no longer actionable")
            if decision == "approved" and any(item[0] != "pending" for item in grants):
                raise ExportDenied("Consent cannot be replayed")
            self.store._execute(conn, "UPDATE case_export_grants SET decision = ?, decided_at = ? WHERE request_id = ? AND owner_id = ?", (decision, now(), request_id, owner_id))
            if decision != "approved":
                self.store._execute(conn, "UPDATE case_export_requests SET status = ?, artifact = NULL WHERE request_id = ?", (decision, request_id))
            self.event(conn, request_id, owner_id, decision)

    def _authorized(self, conn: Any, row: Any) -> list[tuple[str, str]]:
        if row[4] <= now() or not self.admin_allowed(str(row[1]), conn):
            raise ExportDenied("Export permission or consent expired")
        rows = self.store._execute(conn, "SELECT g.case_id, g.owner_id, g.decision, c.user_id, c.status, u.is_enabled, c.updated_at, s.updated_at FROM case_export_grants g JOIN cases c ON c.case_id = g.case_id JOIN users u ON u.user_id = g.owner_id JOIN case_export_snapshots s ON s.request_id = g.request_id AND s.case_id = g.case_id WHERE g.request_id = ? ORDER BY g.case_id" + (" FOR SHARE OF c, u" if self.store.uses_postgres else ""), (row[0],)).fetchall()
        if len(rows) != row[8] or any(r[2] != "approved" or r[1] != r[3] or r[4] == "deleted" or not r[5] or str(r[6]) != str(r[7]) for r in rows):
            raise ExportDenied("Every case owner must approve this export")
        return [(str(r[0]), str(r[1])) for r in rows]

    def generate(self, request_id: str, builder: Callable[[list[tuple[str, str]]], bytes]) -> None:
        with self.locked(request_id) as (conn, row):
            if row[5] != "pending":
                raise ExportDenied("Export is not pending")
            cases = self._authorized(conn, row)
            payload = builder(cases)
            # Recheck time/permission after generation; never report success early.
            self._authorized(conn, row)
            assert self.store.case_cipher is not None
            encrypted = self.store.case_cipher.encrypt(cases[0][0], "export:" + request_id, payload)
            expires = min(str(row[4]), (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
            self.store._execute(conn, "UPDATE case_export_requests SET status = 'ready', artifact = ?, artifact_expires_at = ? WHERE request_id = ?", (encrypted, expires, request_id))
            self.event(conn, request_id, str(row[1]), "generated")

    def download(self, request_id: str, admin_id: str) -> bytes:
        with self.locked(request_id) as (conn, row):
            if row[1] != admin_id or row[5] != "ready" or not row[6] or row[6] <= now():
                raise ExportDenied("Export unavailable")
            cases = self._authorized(conn, row)
            assert self.store.case_cipher is not None
            payload = self.store.case_cipher.decrypt(cases[0][0], "export:" + request_id, str(row[7]))
            self.store._execute(conn, "UPDATE case_export_requests SET status = 'downloaded', artifact = NULL WHERE request_id = ?", (request_id,))
            self.event(conn, request_id, admin_id, "downloaded")
            return payload

    def fail(self, request_id: str) -> None:
        with self.locked(request_id) as (conn, row):
            if row[5] == "pending":
                self.store._execute(conn, "UPDATE case_export_requests SET status = 'failed', artifact = NULL WHERE request_id = ?", (request_id,))
                self.event(conn, request_id, "worker", "generation_failed")

    def cleanup(self) -> int:
        with self.store._connect() as conn:
            rows = self.store._execute(conn, "SELECT request_id FROM case_export_requests WHERE status IN ('pending', 'ready') AND (expires_at <= ? OR artifact_expires_at <= ?)", (now(), now())).fetchall()
        count = 0
        for item in rows:
            with self.locked(str(item[0])) as (conn, row):
                if row[5] in {"pending", "ready"} and (row[4] <= now() or (row[6] and row[6] <= now())):
                    self.store._execute(conn, "UPDATE case_export_requests SET artifact = NULL, status = 'expired' WHERE request_id = ?", (item[0],))
                    self.event(conn, str(item[0]), "worker", "expired_cleanup")
                    count += 1
        return count

    def listing(self, user_id: str, *, admin: bool = False) -> list[dict[str, Any]]:
        self.cleanup()
        with self.store._connect() as conn:
            if admin and not self.admin_allowed(user_id, conn):
                raise ExportDenied("Dedicated case.export permission required")
            query = "SELECT DISTINCT r.request_id, r.admin_id, r.purpose, r.created_at, r.expires_at, r.status, r.artifact_expires_at FROM case_export_requests r JOIN case_export_grants g ON g.request_id = r.request_id WHERE "
            query += "r.admin_id = ?" if admin else "g.owner_id = ?"
            rows = self.store._execute(conn, query + " ORDER BY r.created_at DESC", (user_id,)).fetchall()
            result = []
            for row in rows:
                grants = self.store._execute(conn, "SELECT case_id, owner_id, decision FROM case_export_grants WHERE request_id = ? ORDER BY case_id", (row[0],)).fetchall()
                if not grants:
                    continue
                recipient = self.store._fetchone(conn, "SELECT full_name, email FROM users WHERE user_id = ?", (row[1],))
                purpose = self.store.decrypt_case_text(str(grants[0][0]), "export-purpose:" + str(row[0]), str(row[2])) if row[2] else "Erased with case"
                result.append(dict(request_id=row[0], admin_id=row[1], admin_name=str(recipient[0] or "Administrator") if recipient else "Administrator", admin_email=str(recipient[1]) if recipient else "", purpose=purpose, created_at=row[3], expires_at=row[4], status=row[5], artifact_expires_at=row[6], cases=[dict(case_id=g[0], decision=g[2]) for g in grants if admin or g[1] == user_id]))
        return result
