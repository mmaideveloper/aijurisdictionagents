"""Create/revoke private device credentials for the approved synthetic E2E users."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from aijurisdictionagents.api_db import ApiDatabaseStore, User
from aijurisdictionagents.api_db.e2e_test_users import E2E_TEST_USER_EMAILS


def _approved_user(
    store: ApiDatabaseStore, user_id: str, email: str, *, require_enabled: bool = True
) -> User:
    user = store.get_user(user_id=user_id)
    if (
        email not in E2E_TEST_USER_EMAILS
        or user.email != email
        or (require_enabled and not user.is_enabled)
    ):
        raise ValueError("Browser credentials require an enabled approved synthetic account")
    return user


def _revoke(store: ApiDatabaseStore, records: list[dict[str, str]]) -> None:
    for record in records:
        _approved_user(store, record["userId"], record["email"], require_enabled=False)
        if not re.fullmatch(r"prod-e2e-[a-f0-9]{32}", record["deviceId"]):
            raise ValueError("Only task-specific E2E devices may be revoked")
    with store._connect() as conn:
        for record in records:
            store._execute(
                conn,
                "DELETE FROM device_auth_tokens WHERE user_id = ? AND device_id = ?",
                (record["userId"], record["deviceId"]),
            )
        conn.commit()


def create_fixture(store: ApiDatabaseStore, path: Path) -> None:
    users = []
    for email in sorted(E2E_TEST_USER_EMAILS):
        user = store.find_user_by_email(email=email)
        if user is None:
            raise ValueError("Provision the approved synthetic accounts first")
        users.append(_approved_user(store, user.user_id, email))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    records: list[dict[str, str]] = []
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for user in users:
                device_id = f"prod-e2e-{uuid4().hex}"
                token = store.issue_device_auth_token(
                    user_id=user.user_id, device_id=device_id, expires_in_days=1
                )
                records.append(
                    {
                        "userId": user.user_id,
                        "email": user.email,
                        "deviceId": device_id,
                        "deviceAuthToken": token,
                    }
                )
            json.dump({"users": records}, stream)
    except BaseException:
        try:
            _revoke(store, records)
        finally:
            path.unlink(missing_ok=True)
        raise


def revoke_fixture(store: ApiDatabaseStore, path: Path) -> None:
    records = json.loads(path.read_text(encoding="utf-8"))["users"]
    _revoke(store, records)
    path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "revoke"))
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    try:
        store = ApiDatabaseStore.from_env()
        operation = create_fixture if args.operation == "create" else revoke_fixture
        operation(store, args.file)
    except Exception as exc:
        # Never include fixture contents, tokens, connection strings or provider errors.
        print(
            f"Synthetic browser credential operation failed ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1
    print(f"Synthetic browser credentials: {args.operation} completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
