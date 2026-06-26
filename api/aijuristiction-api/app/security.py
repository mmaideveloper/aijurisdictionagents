from __future__ import annotations

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.auth.service import API_KEY_HEADER_NAME, validate_api_key

api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)
admin_api_key_header = APIKeyHeader(name="x-admin-api-key", auto_error=False)


def require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    validate_api_key(api_key)


def require_admin_api_key(
    _api_key: None = Security(require_api_key),
    admin_api_key: str | None = Security(admin_api_key_header),
) -> None:
    expected = (
        os.getenv("JURISDIGTA_ADMIN_API_KEY", "").strip()
        or os.getenv("ADMIN_API_KEY", "").strip()
    )
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured.",
        )
    if admin_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key is invalid.",
        )
