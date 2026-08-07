from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from aijurisdictionagents.api_db import ApiDatabaseStore, DocumentShare, generate_one_time_code
from app.cases_api import _render_generated_case_document_pdf_bytes, get_store
from app.services.email_scheduler import EmailScheduler


router = APIRouter(prefix="/v1/document-shares", tags=["document-shares"])
_GENERIC_ERROR = "This document link is unavailable or has expired."
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
}


class DocumentShareCodeResponse(BaseModel):
    message: str
    locale: str


class DocumentShareVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class DocumentShareVerifyResponse(BaseModel):
    session_token: str
    expires_at: str
    locale: str


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _active_share(raw_token: str, store: ApiDatabaseStore) -> DocumentShare:
    try:
        share = store.get_document_share_by_token_hash(token_hash=_hash_secret(raw_token))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_GENERIC_ERROR) from exc
    now = datetime.now(timezone.utc)
    if share.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_GENERIC_ERROR)
    if (_parse_time(share.expires_at) or now) <= now:
        store.expire_document_share(share_id=share.share_id)
        store.record_document_share_audit(
            share_id=share.share_id, action="share.expired", outcome="secrets_removed"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_GENERIC_ERROR)
    return share


def _otp_email(*, locale: str, code: str) -> tuple[str, str]:
    values = {
        "en": (
            "Your JurisDigta document verification code",
            f"Your verification code is {code}. It expires in 10 minutes. Do not share this code.",
        ),
        "sk": (
            "Overovací kód dokumentu JurisDigta",
            f"Váš overovací kód je {code}. Platí 10 minút. Tento kód s nikým nezdieľajte.",
        ),
        "de": (
            "Ihr JurisDigta-Dokumentprüfcode",
            f"Ihr Bestätigungscode lautet {code}. Er läuft in 10 Minuten ab. Geben Sie diesen Code nicht weiter.",
        ),
    }
    return values.get(locale, values["en"])


@router.post("/{share_token}/request-code", response_model=DocumentShareCodeResponse)
def request_document_share_code(
    share_token: str,
    store: ApiDatabaseStore = Depends(get_store),
) -> DocumentShareCodeResponse:
    share = _active_share(share_token, store)
    now = datetime.now(timezone.utc)
    last_sent = _parse_time(share.last_code_sent_at)
    if last_sent is not None and now - last_sent < timedelta(seconds=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another code.",
        )
    code = generate_one_time_code()
    expires_at = now + timedelta(minutes=10)
    store.set_document_share_code(
        share_id=share.share_id,
        code_hash=_hash_secret(code),
        code_expires_at=expires_at.isoformat(),
        sent_at=now.isoformat(),
    )
    email_subject, email_body = _otp_email(locale=share.locale, code=code)
    EmailScheduler.from_env().enqueue(
        recipient=share.recipient_email,
        subject=email_subject,
        body=email_body,
        metadata={"event": "one_time_code", "share_id": share.share_id, "locale": share.locale},
    )
    store.record_document_share_audit(
        share_id=share.share_id, action="code.requested", outcome="email_queued"
    )
    return DocumentShareCodeResponse(message="Verification code sent.", locale=share.locale)


@router.post("/{share_token}/verify", response_model=DocumentShareVerifyResponse)
def verify_document_share_code(
    share_token: str,
    payload: DocumentShareVerifyRequest,
    store: ApiDatabaseStore = Depends(get_store),
) -> DocumentShareVerifyResponse:
    share = _active_share(share_token, store)
    now = datetime.now(timezone.utc)
    code_expiry = _parse_time(share.code_expires_at)
    if share.code_attempts >= 5 or code_expiry is None or code_expiry <= now or not share.code_hash:
        store.record_document_share_audit(
            share_id=share.share_id, action="code.verified", outcome="rejected"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification code is invalid or expired.",
        )
    if not hmac.compare_digest(share.code_hash, _hash_secret(payload.code)):
        attempts = store.increment_document_share_code_attempts(share_id=share.share_id)
        store.record_document_share_audit(
            share_id=share.share_id, action="code.verified", outcome="invalid"
        )
        if attempts >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="The verification code is invalid or expired.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification code is invalid or expired.",
        )
    raw_session = secrets.token_urlsafe(32)
    session_expires_at = now + timedelta(minutes=30)
    store.activate_document_share_session(
        share_id=share.share_id,
        session_token_hash=_hash_secret(raw_session),
        session_expires_at=session_expires_at.isoformat(),
    )
    store.record_document_share_audit(
        share_id=share.share_id, action="code.verified", outcome="success"
    )
    return DocumentShareVerifyResponse(
        session_token=raw_session, expires_at=session_expires_at.isoformat(), locale=share.locale
    )


@router.get("/content/pdf")
def get_shared_document_pdf(
    authorization: str | None = Header(default=None),
    store: ApiDatabaseStore = Depends(get_store),
) -> Response:
    scheme, _, raw_session = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not raw_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_GENERIC_ERROR, headers=_NO_STORE_HEADERS
        )
    try:
        share = store.get_document_share_by_session_hash(
            session_token_hash=_hash_secret(raw_session)
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_GENERIC_ERROR, headers=_NO_STORE_HEADERS
        ) from exc
    now = datetime.now(timezone.utc)
    if (
        share.status != "active"
        or (_parse_time(share.expires_at) or now) <= now
        or (_parse_time(share.session_expires_at) or now) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_GENERIC_ERROR, headers=_NO_STORE_HEADERS
        )
    case = store.get_case(case_id=share.case_id)
    document = store.get_case_document(case_id=share.case_id, doc_id=share.doc_id)
    if document.kind != "generated_document":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_GENERIC_ERROR, headers=_NO_STORE_HEADERS
        )
    pdf = _render_generated_case_document_pdf_bytes(
        case=case,
        user_id=share.sender_user_id,
        document=document,
        store=store,
    )
    next_expiry = min(now + timedelta(minutes=30), _parse_time(share.expires_at) or now)
    store.touch_document_share_session(
        share_id=share.share_id, session_expires_at=next_expiry.isoformat()
    )
    store.record_document_share_audit(
        share_id=share.share_id, action="document.viewed", outcome="success"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={**_NO_STORE_HEADERS, "Content-Disposition": "inline; filename=document.pdf"},
    )
