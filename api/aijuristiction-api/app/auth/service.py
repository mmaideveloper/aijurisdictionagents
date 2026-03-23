from __future__ import annotations

from fastapi import HTTPException, status


API_KEY_HEADER_NAME = "x-api-key"
HARDCODED_API_KEY = "aijuris"


def validate_api_key(api_key: str | None) -> None:
    if api_key != HARDCODED_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
