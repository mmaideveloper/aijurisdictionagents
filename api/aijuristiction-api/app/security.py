from __future__ import annotations

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.auth.service import API_KEY_HEADER_NAME, validate_api_key

api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    validate_api_key(api_key)
