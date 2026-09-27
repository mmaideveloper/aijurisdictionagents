"""Minimal central identity adapter; never reads names, email or password hashes."""

import hmac
from datetime import UTC, datetime
from types import SimpleNamespace

from aijurisdictionagents.api_db.store import _hash_one_time_code, _is_future_iso_datetime

from .db import connect


class Identity:
    def __init__(self, url: str):
        self.url = url

    def find_user_by_id(self, *, user_id: str):
        with connect(self.url) as conn:
            row = conn.execute("SELECT user_id,is_enabled FROM users WHERE user_id=%s", (user_id,)).fetchone()
        return SimpleNamespace(**row) if row else None

    def authenticate_user_device_auth_token(self, *, user_id: str, device_id: str, token: str):
        user = self.find_user_by_id(user_id=user_id.strip())
        if not user or not user.is_enabled or not token.strip() or not device_id.strip():
            return None
        with connect(self.url) as conn:
            row = conn.execute(
                "SELECT token_hash,expires_at FROM device_auth_tokens WHERE user_id=%s AND device_id=%s",
                (user.user_id, device_id.strip()),
            ).fetchone()
            if not row or not _is_future_iso_datetime(str(row["expires_at"])):
                return None
            if not hmac.compare_digest(row["token_hash"], _hash_one_time_code(token.strip())):
                return None
            conn.execute(
                "UPDATE device_auth_tokens SET last_used_at=%s WHERE user_id=%s AND device_id=%s",
                (datetime.now(UTC).isoformat(), user.user_id, device_id.strip()),
            )
        return user
