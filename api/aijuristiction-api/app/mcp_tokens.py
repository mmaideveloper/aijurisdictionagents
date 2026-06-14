from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aijurisdictionagents.api_db import User


def create_mcp_api_token(*, user: User, expires_at: datetime) -> str:
    token_id = str(uuid4())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.user_id,
        "email": user.email,
        "exp": int(expires_at.timestamp()),
        "jti": token_id,
    }
    encoded_header = _base64url_json(header)
    encoded_payload = _base64url_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


def validate_mcp_api_token(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    encoded_header, encoded_payload, provided_signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign(signing_input)
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None
    try:
        header = _base64url_decode_json(encoded_header)
        payload = _base64url_decode_json(encoded_payload)
    except Exception:
        return None
    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(datetime.now(timezone.utc).timestamp()):
        return None
    if not isinstance(payload.get("sub"), str) or not isinstance(payload.get("email"), str):
        return None
    if not isinstance(payload.get("jti"), str):
        return None
    return payload


def _base64url_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url_encode(raw)


def _base64url_decode_json(value: str) -> dict[str, Any]:
    raw = _base64url_decode(value)
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("JWT part must decode to an object")
    return decoded


def _sign(value: str) -> str:
    digest = hmac.new(_jwt_secret(), value.encode("utf-8"), hashlib.sha256).digest()
    return _base64url_encode(digest)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _jwt_secret() -> bytes:
    secret = os.getenv("MCP_API_JWT_SECRET", "").strip()
    if not secret:
        db_option = os.getenv("DB_OPTION", "local").strip().lower()
        local_auth = os.getenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "").strip().lower() in {"1", "true", "yes", "on"}
        if db_option in {"local", "sqlite", ""} or local_auth:
            secret = "local-dev-mcp-jwt-secret-change-before-deploy"
        else:
            raise RuntimeError("MCP_API_JWT_SECRET must be set before issuing MCP JWT tokens.")
    return secret.encode("utf-8")
