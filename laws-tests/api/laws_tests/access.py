"""Deny by default. All content permissions are rechecked on every request."""

from fastapi import HTTPException


def bank_allowed(conn, user: dict, test_id: str) -> bool:
    if user.get("is_admin", False):
        return True
    return bool(
        conn.execute(
            """SELECT 1 FROM test_users u JOIN bank_access a USING(user_id)
        WHERE u.user_id=%s AND u.approved AND a.test_id=%s AND a.status='approved'""",
            (user["user_id"], test_id),
        ).fetchone()
    )


def require_bank(conn, user: dict, test_id: str) -> None:
    if not bank_allowed(conn, user, test_id):
        raise HTTPException(403, "Prístup k tejto banke musí schváliť administrátor.")


def audit(conn, actor: str, action: str, target: str) -> None:
    from uuid import uuid4

    conn.execute(
        "INSERT INTO bank_audit(id,actor_id,action,target_id) VALUES(%s,%s,%s,%s)",
        (uuid4(), actor, action, target),
    )
