from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.email import EmailNotificationService

CONTACT_RECIPIENT = "info@jurisdigta.eu"
TURNSTILE_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
_LINK_RE = re.compile(r"\b(?:https?://|www\.|\.ru\b|\.cn\b)", re.IGNORECASE)

router = APIRouter(prefix="/v1/contact", tags=["contact"])
_rate_limit_hits: dict[str, list[float]] = {}


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=120)
    company: str | None = Field(default=None, max_length=120)
    topic: str = Field(min_length=2, max_length=120)
    message: str = Field(min_length=5, max_length=1200)
    website: str | None = Field(default=None, max_length=200)
    started_at: int | None = None
    turnstile_token: str | None = Field(default=None, max_length=4096)


class ContactResponse(BaseModel):
    status: str
    recipient: str


def get_contact_email_service() -> EmailNotificationService:
    return EmailNotificationService.from_env()


@router.post("", response_model=ContactResponse, status_code=status.HTTP_202_ACCEPTED)
def send_contact_request(
    payload: ContactRequest,
    request: Request,
    email_service: EmailNotificationService = Depends(get_contact_email_service),
) -> ContactResponse:
    normalized_email = payload.email.strip().lower()
    if not _EMAIL_RE.match(normalized_email) or ".." in normalized_email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email address")
    if payload.website and payload.website.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request rejected")
    if _LINK_RE.search(payload.message):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot contain web links")
    client_ip = _client_ip(request)
    _enforce_contact_rate_limit(client_ip)
    _verify_turnstile_token(payload.turnstile_token, remote_ip=client_ip)

    subject = f"JurisDigta contact request: {payload.topic.strip()}"
    body = _build_contact_email_body(payload=payload, request=request, normalized_email=normalized_email)
    email_service.send_email(
        recipient=CONTACT_RECIPIENT,
        subject=subject,
        body=body,
    )
    return ContactResponse(status="sent", recipient=CONTACT_RECIPIENT)


def _verify_turnstile_token(token: str | None, *, remote_ip: str | None) -> None:
    if not _contact_captcha_required():
        return

    secret_key = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    if not secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CAPTCHA is not configured",
        )
    if not token or not token.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CAPTCHA verification is required")

    payload = {
        "secret": secret_key,
        "response": token.strip(),
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    body = urlencode(payload).encode("utf-8")
    request = UrlRequest(
        TURNSTILE_SITEVERIFY_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CAPTCHA verification failed",
        ) from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CAPTCHA verification failed",
        ) from exc
    if not bool(result.get("success")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CAPTCHA verification failed")


def _contact_captcha_required() -> bool:
    value = os.getenv("CONTACT_CAPTCHA_REQUIRED", "").strip().lower()
    if value:
        return value in {"1", "true", "yes", "on"}
    return bool(os.getenv("TURNSTILE_SECRET_KEY", "").strip())


def _enforce_contact_rate_limit(client_ip: str | None) -> None:
    if not client_ip:
        return
    max_requests = _env_int("CONTACT_RATE_LIMIT_MAX_REQUESTS", default=5)
    window_seconds = _env_int("CONTACT_RATE_LIMIT_WINDOW_SECONDS", default=600)
    if max_requests <= 0 or window_seconds <= 0:
        return

    now = time.monotonic()
    cutoff = now - window_seconds
    hits = [hit for hit in _rate_limit_hits.get(client_ip, []) if hit >= cutoff]
    if len(hits) >= max_requests:
        _rate_limit_hits[client_ip] = hits
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many contact requests",
        )
    hits.append(now)
    _rate_limit_hits[client_ip] = hits


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    if request.client is None:
        return None
    return request.client.host


def _build_contact_email_body(
    *,
    payload: ContactRequest,
    request: Request,
    normalized_email: str,
) -> str:
    values: dict[str, Any] = {
        "Name": payload.name.strip(),
        "Email": normalized_email,
        "Organization": (payload.company or "").strip() or "-",
        "Topic": payload.topic.strip(),
        "Origin": request.headers.get("origin", "-"),
        "User-Agent": request.headers.get("user-agent", "-"),
    }
    lines = [f"{key}: {value}" for key, value in values.items()]
    lines.extend(["", payload.message.strip()])
    return "\n".join(lines)
