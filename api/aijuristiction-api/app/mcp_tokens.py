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

MCP_TOKEN_SCOPE = "mcp:laws"
MCP_REFRESH_TOKEN_SCOPE = "offline_access"


def create_mcp_api_token(
    *,
    user: User,
    expires_at: datetime,
    audience: str | None = None,
    scope: str = MCP_TOKEN_SCOPE,
) -> str:
    token_id = str(uuid4())
    issued_at = int(datetime.now(timezone.utc).timestamp())
    resolved_audience = audience or default_mcp_resource_url()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.user_id,
        "aud": resolved_audience,
        "iss": _issuer_from_audience(resolved_audience),
        "scope": scope,
        "iat": issued_at,
        "exp": int(expires_at.timestamp()),
        "jti": token_id,
        "token_use": "access",
    }
    encoded_header = _base64url_json(header)
    encoded_payload = _base64url_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


def create_mcp_refresh_token(
    *,
    user: User,
    expires_at: datetime,
    audience: str | None = None,
) -> str:
    token_id = str(uuid4())
    issued_at = int(datetime.now(timezone.utc).timestamp())
    resolved_audience = audience or default_mcp_resource_url()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.user_id,
        "aud": resolved_audience,
        "iss": _issuer_from_audience(resolved_audience),
        "scope": MCP_REFRESH_TOKEN_SCOPE,
        "iat": issued_at,
        "exp": int(expires_at.timestamp()),
        "jti": token_id,
        "token_use": "refresh",
    }
    encoded_header = _base64url_json(header)
    encoded_payload = _base64url_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


def validate_mcp_api_token(token: str, *, audience: str, required_scope: str) -> dict[str, Any] | None:
    payload = _validate_mcp_token(token=token, audience=audience)
    if payload is None:
        return None
    if payload.get("token_use") not in {None, "access"}:
        return None
    scope = payload.get("scope")
    if not isinstance(scope, str) or required_scope not in scope.split():
        return None
    return payload


def validate_mcp_refresh_token(token: str, *, audience: str) -> dict[str, Any] | None:
    payload = _validate_mcp_token(token=token, audience=audience)
    if payload is None:
        return None
    if payload.get("token_use") != "refresh":
        return None
    if payload.get("scope") != MCP_REFRESH_TOKEN_SCOPE:
        return None
    return payload


def _validate_mcp_token(token: str, *, audience: str) -> dict[str, Any] | None:
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
    if not isinstance(payload.get("sub"), str):
        return None
    if payload.get("aud") != audience:
        return None
    if not isinstance(payload.get("jti"), str):
        return None
    return payload


def default_mcp_resource_url() -> str:
    base_url = os.getenv("MCP_PUBLIC_BASE_URL", "https://mcp.jurisdigta.eu").strip().rstrip("/")
    return f"{base_url}/MCP"


def _issuer_from_audience(audience: str) -> str:
    if audience.endswith("/MCP"):
        return audience[:-4]
    return audience.rstrip("/")


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
