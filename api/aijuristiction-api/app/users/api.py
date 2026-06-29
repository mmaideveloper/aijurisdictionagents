from __future__ import annotations

import importlib
import os
import base64
import secrets
import sqlite3
from typing import cast
from types import ModuleType
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.mcp_tokens import create_mcp_api_token
from app.security import require_api_key
from app.services.email_scheduler import EmailScheduler
from app.services.subscription_invoices import build_subscription_invoice
from app.users.notifications import (
    queue_registration_email,
    queue_subscription_change_email,
    queue_subscription_status_email,
)
from app.users.totp import (
    generate_totp_secret,
    protect_totp_secret,
    reveal_totp_secret,
    totp_provisioning_uri,
    verify_totp_code,
)

from aijurisdictionagents.api_db import (
    ApiDatabaseStore,
    SubscriptionPlan,
    User,
    UserSubscription,
    generate_one_time_code,
)

try:
    _psycopg_module: ModuleType | None = importlib.import_module("psycopg")
except ModuleNotFoundError:  # pragma: no cover - optional for local sqlite-only runs
    _psycopg_module = None

router = APIRouter(prefix="/v1/users", tags=["users"], dependencies=[Depends(require_api_key)])
_GLOBAL_MFA_PURPOSE = "global_login"


class UserProfileResponse(BaseModel):
    user_id: str
    phone_number: str | None = None
    email: str
    first_name: str | None = None
    last_name: str | None = None
    full_name: str
    address: str | None = None
    city: str | None = None
    country: str | None = None
    zip_code: str | None = None
    tax_number: str | None = None
    identity_card_number: str | None = None
    date_of_birth: str | None = None
    social_security_number: str | None = None
    data_processing_consent_at: str | None = None
    data_processing_consent_version: str | None = None
    mcp_api_key_expires_at: str | None = None
    created_at: str | None = None
    mfa_email_otp_available: bool = True
    mfa_totp_enabled: bool = False
    mfa_totp_pending: bool = False
    mfa_totp_enabled_at: str | None = None
    role: str = "user"
    is_enabled: bool = True


class SignUpRequest(BaseModel):
    phone_number: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    first_name: str | None = None
    last_name: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    zip_code: str | None = None
    tax_number: str | None = None
    identity_card_number: str | None = None
    date_of_birth: str | None = None
    social_security_number: str | None = None
    data_processing_consent_accepted: bool = False
    data_processing_consent_version: str | None = None
    mcp_api_key_expires_at: str | None = None


class SendRegistrationCodeRequest(BaseModel):
    email: str = Field(min_length=1)


class CompleteRegistrationRequest(SignUpRequest):
    verification_code: str = Field(min_length=1, max_length=64)


class SendSignInCodeRequest(BaseModel):
    phone_number: str = Field(min_length=1)
    device_id: str = Field(min_length=1)


class VerifySignInCodeRequest(SendSignInCodeRequest):
    verification_code: str = Field(min_length=1, max_length=64)


class DeviceSignInRequest(SendSignInCodeRequest):
    device_token: str = Field(min_length=1)


class SignInByPhoneRequest(BaseModel):
    phone_number: str = Field(min_length=1)


class SignInRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    device_id: str | None = None
    verification_code: str | None = Field(default=None, max_length=64)


class SendEmailChangeCodeRequest(BaseModel):
    email: str = Field(min_length=1)


class CompleteEmailChangeRequest(SendEmailChangeCodeRequest):
    verification_code: str = Field(min_length=1, max_length=64)


class UpdateUserProfileRequest(BaseModel):
    phone_number: str = Field(min_length=1)
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    zip_code: str | None = None
    tax_number: str | None = None
    identity_card_number: str | None = None
    date_of_birth: str | None = None
    social_security_number: str | None = None


class SubscriptionPlanResponse(BaseModel):
    plan_code: str
    display_name: str
    subscription_type: str
    price_eur: int
    max_cases: int
    max_documents_per_case: int
    case_ttl_days: int | None = None


class UserSubscriptionResponse(BaseModel):
    subscription_id: str
    user_id: str
    plan_code: str
    status: str
    starts_at: str | None = None
    ends_at: str | None = None
    case_ids_json: str
    created_at: str
    updated_at: str


class SubscriptionChangeRequest(BaseModel):
    plan_code: str = Field(min_length=1)


class SubscriptionStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1)


class SubscriptionCheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1)
    payment_provider: str = Field(min_length=1, description="paypal or google_pay")


class SubscriptionCheckoutResponse(BaseModel):
    subscription_id: str
    plan_code: str
    payment_provider: str
    payment_id: str
    payment_status: str
    amount_eur: int
    checkout_url: str


class SubscriptionPaymentConfirmationRequest(BaseModel):
    payment_id: str = Field(min_length=1)


class DeviceAuthUserProfileResponse(UserProfileResponse):
    device_auth_token: str | None = None


class MCPApiKeyCreateRequest(BaseModel):
    expires_in_days: int = Field(default=1, ge=1, le=365)


class MCPApiKeyCreateResponse(BaseModel):
    user_id: str
    mcp_api_key: str
    mcp_api_key_expires_at: str


class MfaRequiredResponse(BaseModel):
    mfa_required: bool = True
    mfa_token: str
    user_id: str
    email: str
    methods: list[str]
    reuse_window_hours: int


class StartTotpEnrollmentResponse(BaseModel):
    user_id: str
    manual_setup_key: str
    provisioning_uri: str
    qr_code_uri: str
    totp_pending: bool


class ConfirmTotpEnrollmentRequest(BaseModel):
    verification_code: str = Field(min_length=1, max_length=64)


class DisableTotpRequest(BaseModel):
    password: str | None = None
    verification_code: str | None = None


class VerifyMfaRequest(BaseModel):
    mfa_token: str = Field(min_length=1)
    method: str = Field(min_length=1)
    verification_code: str = Field(min_length=1, max_length=64)
    device_id: str | None = None


class SendMfaEmailCodeRequest(BaseModel):
    mfa_token: str = Field(min_length=1)


_payment_sessions: dict[str, dict[str, str | int]] = {}
_DISABLED_SUBSCRIPTION_PLAN_CODES = {"basic", "premium"}


def get_user_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


def get_email_scheduler() -> EmailScheduler:
    return EmailScheduler.from_env()


@router.post("/sign-up", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def sign_up(
    payload: SignUpRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> UserProfileResponse:
    try:
        user = store.create_user(
            phone_number=payload.phone_number,
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            address=payload.address,
            city=payload.city,
            country=payload.country,
            zip_code=payload.zip_code,
            tax_number=payload.tax_number,
            identity_card_number=payload.identity_card_number,
            date_of_birth=payload.date_of_birth,
            social_security_number=payload.social_security_number,
            data_processing_consent_at=_now_if_accepted(payload.data_processing_consent_accepted),
            data_processing_consent_version=payload.data_processing_consent_version,
        )
    except Exception as exc:
        if not _is_unique_constraint_error(exc):
            raise
        raise _conflict_from_integrity_error(exc) from exc
    queue_registration_email(scheduler=scheduler, user=user)
    return _to_user_profile_response(user)


@router.post("/sign-up/send-code", status_code=status.HTTP_202_ACCEPTED)
def send_registration_code(
    payload: SendRegistrationCodeRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> dict[str, str]:
    code = generate_one_time_code()
    email = payload.email.strip().lower()
    store.save_registration_code(email=email, code=code)
    scheduler.enqueue(
        recipient=email,
        subject="Your registration code",
        body=(
            "Hello,\n\n"
            f"your one time registration code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "registration_code"},
    )
    return {"status": "code_sent"}


@router.post("/sign-up/complete", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def complete_registration(
    payload: CompleteRegistrationRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> UserProfileResponse:
    if not _accepts_any_local_auth_code() and not store.verify_registration_code(
        email=payload.email,
        code=payload.verification_code,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    if not payload.data_processing_consent_accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data processing consent is required")
    try:
        user = store.create_user(
            phone_number=payload.phone_number,
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            address=payload.address,
            city=payload.city,
            country=payload.country,
            zip_code=payload.zip_code,
            tax_number=payload.tax_number,
            identity_card_number=payload.identity_card_number,
            date_of_birth=payload.date_of_birth,
            social_security_number=payload.social_security_number,
            data_processing_consent_at=_now_if_accepted(payload.data_processing_consent_accepted),
            data_processing_consent_version=payload.data_processing_consent_version,
        )
    except Exception as exc:
        if not _is_unique_constraint_error(exc):
            raise
        raise _conflict_from_integrity_error(exc) from exc
    queue_registration_email(scheduler=scheduler, user=user)
    return _to_user_profile_response(user)


@router.post("/sign-in/phone", response_model=UserProfileResponse)
def sign_in_by_phone(
    payload: SignInByPhoneRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    user = store.find_user_by_phone(phone_number=payload.phone_number)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    return _to_user_profile_response(user)


@router.post("/sign-in/send-code", status_code=status.HTTP_202_ACCEPTED)
def send_sign_in_code(
    payload: SendSignInCodeRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> dict[str, str]:
    user = store.find_user_by_phone(phone_number=payload.phone_number)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    code = generate_one_time_code()
    store.save_registration_code(
        email=_sign_in_code_key(phone_number=payload.phone_number, device_id=payload.device_id),
        code=code,
    )
    scheduler.enqueue(
        recipient=user.email,
        subject="Your login code",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your one time login code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "sign_in_code", "user_id": user.user_id},
    )
    return {"status": "code_sent"}


@router.post("/sign-in/verify-code", response_model=DeviceAuthUserProfileResponse)
def verify_sign_in_code(
    payload: VerifySignInCodeRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> DeviceAuthUserProfileResponse:
    user = store.find_user_by_phone(phone_number=payload.phone_number)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    if not _accepts_any_local_auth_code() and not store.verify_registration_code(
        email=_sign_in_code_key(phone_number=payload.phone_number, device_id=payload.device_id),
        code=payload.verification_code,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    token = store.issue_device_auth_token(user_id=user.user_id, device_id=payload.device_id)
    return _to_device_auth_user_profile_response(user=user, token=token)


@router.post("/sign-in/device", response_model=DeviceAuthUserProfileResponse)
def sign_in_with_device_token(
    payload: DeviceSignInRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> DeviceAuthUserProfileResponse:
    user = store.authenticate_device_auth_token(
        phone_number=payload.phone_number,
        device_id=payload.device_id,
        token=payload.device_token,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device token")
    refreshed_token = store.issue_device_auth_token(user_id=user.user_id, device_id=payload.device_id)
    return _to_device_auth_user_profile_response(user=user, token=refreshed_token)


@router.post("/sign-in", response_model=DeviceAuthUserProfileResponse | MfaRequiredResponse)
def sign_in(
    payload: SignInRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> DeviceAuthUserProfileResponse | MfaRequiredResponse:
    user = store.authenticate_user(email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if _requires_mfa(store=store, user=user):
        mfa_token = secrets.token_urlsafe(32)
        store.create_mfa_login_challenge(user_id=user.user_id, token=mfa_token)
        return MfaRequiredResponse(
            mfa_token=mfa_token,
            user_id=user.user_id,
            email=user.email,
            methods=_available_mfa_methods(store=store, user=user),
            reuse_window_hours=_mfa_reuse_window_hours(),
        )
    device_id = (payload.device_id or "").strip()
    if device_id:
        otp_purpose = _web_sign_in_otp_purpose(device_id=device_id)
        if not store.has_valid_mcp_otp_verification(user_id=user.user_id, purpose=otp_purpose):
            verification_code = (payload.verification_code or "").strip()
            if not verification_code:
                _send_web_sign_in_code(store=store, scheduler=scheduler, user=user, device_id=device_id)
                raise HTTPException(
                    status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                    detail="OTP code required",
                )
            if not _accepts_any_local_auth_code() and not store.verify_registration_code(
                email=_web_sign_in_code_key(user_id=user.user_id, device_id=device_id),
                code=verification_code,
            ):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
            store.save_mcp_otp_verification(
                user_id=user.user_id,
                purpose=otp_purpose,
                expires_in_hours=_web_sign_in_otp_reuse_window_hours(),
            )
    token: str | None = None
    if device_id:
        token = store.issue_device_auth_token(user_id=user.user_id, device_id=device_id)
    return _to_device_auth_user_profile_response(user=user, token=token, store=store)


@router.post("/sign-in/mfa/send-email-code", status_code=status.HTTP_202_ACCEPTED)
def send_mfa_email_code(
    payload: SendMfaEmailCodeRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> dict[str, str]:
    user_id = _consume_and_reissue_mfa_challenge(store=store, token=payload.mfa_token)
    user = store.get_user(user_id=user_id)
    if not user.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    code = generate_one_time_code()
    store.save_registration_code(email=_mfa_email_code_key(user_id=user.user_id), code=code)
    scheduler.enqueue(
        recipient=user.email,
        subject="Your MFA login code",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your one time MFA login code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "mfa_email_code", "user_id": user.user_id},
    )
    return {"status": "code_sent"}


@router.post("/sign-in/mfa/verify", response_model=DeviceAuthUserProfileResponse)
def verify_mfa(
    payload: VerifyMfaRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> DeviceAuthUserProfileResponse:
    user_id = store.consume_mfa_login_challenge(token=payload.mfa_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired MFA challenge")
    user = store.get_user(user_id=user_id)
    if not user.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    method = payload.method.strip().lower()
    if method == "email":
        if not _accepts_any_local_auth_code() and not store.verify_registration_code(
            email=_mfa_email_code_key(user_id=user.user_id),
            code=payload.verification_code,
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    elif method == "totp":
        settings = store.get_user_mfa_settings(user_id=user.user_id)
        secret = reveal_totp_secret(settings.totp_secret_protected or "")
        if secret is None or not verify_totp_code(secret=secret, code=payload.verification_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported MFA method")
    _save_mfa_verification(store=store, user=user)
    token: str | None = None
    if payload.device_id:
        token = store.issue_device_auth_token(user_id=user.user_id, device_id=payload.device_id)
    return _to_device_auth_user_profile_response(user=user, token=token, store=store)


@router.patch("/{user_id}", response_model=UserProfileResponse)
def update_user_profile(
    user_id: str,
    payload: UpdateUserProfileRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    current = store.find_user_by_id(user_id=user_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")
    model_fields_set = getattr(payload, "model_fields_set", None)
    provided_fields: set[str] = (
        set(model_fields_set) if model_fields_set is not None else set(getattr(payload, "__fields_set__", set()))
    )
    try:
        user = store.update_user(
            user_id=user_id,
            phone_number=payload.phone_number,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            address=payload.address if "address" in provided_fields else current.address,
            city=payload.city if "city" in provided_fields else current.city,
            country=payload.country if "country" in provided_fields else current.country,
            zip_code=payload.zip_code if "zip_code" in provided_fields else current.zip_code,
            tax_number=payload.tax_number if "tax_number" in provided_fields else current.tax_number,
            identity_card_number=(
                payload.identity_card_number
                if "identity_card_number" in provided_fields
                else current.identity_card_number
            ),
            date_of_birth=payload.date_of_birth if "date_of_birth" in provided_fields else current.date_of_birth,
            social_security_number=(
                payload.social_security_number
                if "social_security_number" in provided_fields
                else current.social_security_number
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        if not _is_unique_constraint_error(exc):
            raise
        raise _conflict_from_integrity_error(exc) from exc
    return _to_user_profile_response(user, store=store)


@router.post("/{user_id}/mfa/totp/start", response_model=StartTotpEnrollmentResponse)
def start_totp_enrollment(
    user_id: str,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> StartTotpEnrollmentResponse:
    user = store.get_user(user_id=user_id)
    secret = generate_totp_secret()
    protected_secret = protect_totp_secret(secret)
    settings = store.start_user_totp_enrollment(user_id=user.user_id, protected_secret=protected_secret)
    uri = totp_provisioning_uri(secret=secret, email=user.email)
    return StartTotpEnrollmentResponse(
        user_id=user.user_id,
        manual_setup_key=secret,
        provisioning_uri=uri,
        qr_code_uri=_qr_code_uri(uri),
        totp_pending=settings.totp_pending,
    )


@router.post("/{user_id}/mfa/totp/confirm", response_model=UserProfileResponse)
def confirm_totp_enrollment(
    user_id: str,
    payload: ConfirmTotpEnrollmentRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    user = store.get_user(user_id=user_id)
    settings = store.get_user_mfa_settings(user_id=user.user_id)
    pending_secret = reveal_totp_secret(settings.pending_totp_secret_protected or "")
    if pending_secret is None or not verify_totp_code(secret=pending_secret, code=payload.verification_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    store.enable_user_totp(user_id=user.user_id)
    return _to_user_profile_response(user, store=store)


@router.delete("/{user_id}/mfa/totp", response_model=UserProfileResponse)
def disable_totp(
    user_id: str,
    payload: DisableTotpRequest | None = None,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    user = store.get_user(user_id=user_id)
    settings = store.get_user_mfa_settings(user_id=user.user_id)
    if settings.totp_enabled:
        code = payload.verification_code if payload is not None else None
        secret = reveal_totp_secret(settings.totp_secret_protected or "")
        if secret is None or not code or not verify_totp_code(secret=secret, code=code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid TOTP code is required")
    store.disable_user_totp(user_id=user.user_id)
    return _to_user_profile_response(user, store=store)


@router.post("/{user_id}/email-change/send-code", status_code=status.HTTP_202_ACCEPTED)
def send_email_change_code(
    user_id: str,
    payload: SendEmailChangeCodeRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> dict[str, str]:
    user = store.find_user_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")
    email = payload.email.strip().lower()
    existing = store.find_user_by_email(email=email)
    if existing is not None and existing.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    code = generate_one_time_code()
    store.save_registration_code(email=_email_change_code_key(user_id=user_id, email=email), code=code)
    scheduler.enqueue(
        recipient=email,
        subject="Your email change code",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your one time email change code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "email_change_code", "user_id": user_id},
    )
    return {"status": "code_sent"}


@router.post("/{user_id}/email-change/complete", response_model=UserProfileResponse)
def complete_email_change(
    user_id: str,
    payload: CompleteEmailChangeRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    user = store.find_user_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")
    email = payload.email.strip().lower()
    if not _accepts_any_local_auth_code() and not store.verify_registration_code(
        email=_email_change_code_key(user_id=user_id, email=email),
        code=payload.verification_code,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
    try:
        updated = store.update_user_email(user_id=user_id, email=email)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        if not _is_unique_constraint_error(exc):
            raise
        raise _conflict_from_integrity_error(exc) from exc
    return _to_user_profile_response(updated)


@router.post("/{user_id}/mcp-api-key", response_model=MCPApiKeyCreateResponse)
def create_user_mcp_api_key(
    user_id: str,
    payload: MCPApiKeyCreateRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> MCPApiKeyCreateResponse:
    user = store.get_user(user_id=user_id)
    expires_at_dt = (datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)).replace(microsecond=0)
    raw_key = create_mcp_api_token(user=user, expires_at=expires_at_dt)
    expires_at = expires_at_dt.isoformat()
    store.set_user_mcp_api_key(user_id=user_id, api_key=raw_key, expires_at=expires_at)
    return MCPApiKeyCreateResponse(
        user_id=user_id,
        mcp_api_key=raw_key,
        mcp_api_key_expires_at=expires_at,
    )


@router.delete("/{user_id}/mcp-api-key", response_model=UserProfileResponse)
def delete_user_mcp_api_key(
    user_id: str,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    user = store.clear_user_mcp_api_key(user_id=user_id)
    return _to_user_profile_response(user)


@router.get("/{user_id}", response_model=UserProfileResponse)
def get_user_profile(
    user_id: str,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    user = store.get_user(user_id=user_id)
    return _to_user_profile_response(user, store=store)


@router.get("/subscriptions/plans", response_model=list[SubscriptionPlanResponse])
def list_subscription_plans(
    store: ApiDatabaseStore = Depends(get_user_store),
) -> list[SubscriptionPlanResponse]:
    return [_to_plan_response(plan) for plan in store.list_subscription_plans()]


@router.get("/{user_id}/subscriptions", response_model=list[UserSubscriptionResponse])
def list_user_subscriptions(
    user_id: str,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> list[UserSubscriptionResponse]:
    return [_to_subscription_response(item) for item in store.list_user_subscriptions(user_id=user_id)]


@router.post("/{user_id}/subscriptions", response_model=UserSubscriptionResponse, status_code=status.HTTP_201_CREATED)
def request_subscription_change(
    user_id: str,
    payload: SubscriptionChangeRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> UserSubscriptionResponse:
    _ensure_subscription_plan_enabled(payload.plan_code)
    try:
        item = store.request_subscription_change(user_id=user_id, plan_code=payload.plan_code)
    except Exception as exc:
        if not _is_integrity_error(exc):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan code") from exc

    user = store.find_user_by_id(user_id=user_id)
    if user is not None:
        queue_subscription_change_email(scheduler=scheduler, user=user, item=item)
    return _to_subscription_response(item)


@router.patch("/subscriptions/{subscription_id}", response_model=UserSubscriptionResponse)
def update_subscription_status(
    subscription_id: str,
    payload: SubscriptionStatusUpdateRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> UserSubscriptionResponse:
    try:
        item = store.update_subscription_status(subscription_id=subscription_id, status=payload.status)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = store.find_user_by_id(user_id=item.user_id)
    if user is None:
        return _to_subscription_response(item)

    queue_subscription_status_email(scheduler=scheduler, user=user, item=item)
    return _to_subscription_response(item)


@router.post(
    "/{user_id}/subscriptions/checkout",
    response_model=SubscriptionCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
def checkout_subscription_change(
    user_id: str,
    payload: SubscriptionCheckoutRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> SubscriptionCheckoutResponse:
    provider = payload.payment_provider.strip().lower()
    if provider not in {"paypal", "google_pay"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported payment provider. Use paypal or google_pay",
        )

    plans = {plan.plan_code: plan for plan in store.list_subscription_plans()}
    plan_code = payload.plan_code.strip().lower()
    if plan_code not in plans:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan code")
    _ensure_subscription_checkout_enabled(plan_code)

    try:
        subscription = store.request_subscription_change(user_id=user_id, plan_code=plan_code)
    except Exception as exc:
        if not _is_integrity_error(exc):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan code") from exc

    payment_id = f"PAY-{uuid4()}"
    checkout_token = str(uuid4())
    checkout_base = "https://www.sandbox.paypal.com/checkoutnow"
    if provider == "google_pay":
        checkout_base = "https://pay.google.com/gp/p/ui/pay"
    checkout_url = f"{checkout_base}?token={checkout_token}&paymentId={payment_id}"

    _payment_sessions[payment_id] = {
        "subscription_id": subscription.subscription_id,
        "user_id": user_id,
        "payment_provider": provider,
        "plan_code": plan_code,
        "payment_status": "pending",
        "amount_eur": plans[plan_code].price_eur,
    }

    return SubscriptionCheckoutResponse(
        subscription_id=subscription.subscription_id,
        plan_code=plan_code,
        payment_provider=provider,
        payment_id=payment_id,
        payment_status="pending",
        amount_eur=plans[plan_code].price_eur,
        checkout_url=checkout_url,
    )


@router.post("/subscriptions/{subscription_id}/confirm-payment", response_model=UserSubscriptionResponse)
def confirm_subscription_payment(
    subscription_id: str,
    payload: SubscriptionPaymentConfirmationRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
    scheduler: EmailScheduler = Depends(get_email_scheduler),
) -> UserSubscriptionResponse:
    payment = _payment_sessions.get(payload.payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    if payment["subscription_id"] != subscription_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment does not match subscription")

    user_id = str(payment["user_id"])
    try:
        user = store.get_user(user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    payment["payment_status"] = "paid"
    item = store.update_subscription_status(subscription_id=subscription_id, status="paid")
    plan = next((plan for plan in store.list_subscription_plans() if plan.plan_code == item.plan_code), None)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan code")
    invoice = build_subscription_invoice(
        user=user,
        subscription=item,
        plan=plan,
        payment_provider=str(payment["payment_provider"]),
        payment_id=payload.payment_id,
    )
    queue_subscription_status_email(scheduler=scheduler, user=user, item=item, invoice=invoice)
    return _to_subscription_response(item)


def _to_user_profile_response(user: User, store: ApiDatabaseStore | None = None) -> UserProfileResponse:
    mfa_settings = store.get_user_mfa_settings(user_id=user.user_id) if store is not None else None
    return UserProfileResponse(
        user_id=user.user_id,
        phone_number=user.phone_number,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        address=user.address,
        city=user.city,
        country=user.country,
        zip_code=user.zip_code,
        tax_number=user.tax_number,
        identity_card_number=user.identity_card_number,
        date_of_birth=user.date_of_birth,
        social_security_number=user.social_security_number,
        data_processing_consent_at=user.data_processing_consent_at,
        data_processing_consent_version=user.data_processing_consent_version,
        mcp_api_key_expires_at=user.mcp_api_key_expires_at,
        created_at=user.created_at,
        mfa_totp_enabled=bool(mfa_settings and mfa_settings.totp_enabled),
        mfa_totp_pending=bool(mfa_settings and mfa_settings.totp_pending),
        mfa_totp_enabled_at=mfa_settings.totp_enabled_at if mfa_settings else None,
        role=user.role,
        is_enabled=user.is_enabled,
    )


def _to_device_auth_user_profile_response(
    *,
    user: User,
    token: str | None,
    store: ApiDatabaseStore | None = None,
) -> DeviceAuthUserProfileResponse:
    profile = _to_user_profile_response(user, store=store)
    return DeviceAuthUserProfileResponse(**profile.model_dump(), device_auth_token=token)


def _ensure_subscription_plan_enabled(plan_code: str) -> None:
    if plan_code.strip().lower() in _DISABLED_SUBSCRIPTION_PLAN_CODES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This subscription plan is coming soon.",
        )


def _ensure_subscription_checkout_enabled(plan_code: str) -> None:
    normalized = plan_code.strip().lower()
    if normalized == "case":
        return
    if normalized in _DISABLED_SUBSCRIPTION_PLAN_CODES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This subscription plan is coming soon.",
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Checkout is available only for the Case plan.",
    )


def _now_if_accepted(accepted: bool) -> str | None:
    if not accepted:
        return None
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _sign_in_code_key(*, phone_number: str, device_id: str) -> str:
    return f"signin:{phone_number.strip()}:{device_id.strip()}"


def _email_change_code_key(*, user_id: str, email: str) -> str:
    return f"email-change:{user_id.strip()}:{email.strip().lower()}"


def _web_sign_in_code_key(*, user_id: str, device_id: str) -> str:
    return f"web-signin:{user_id.strip()}:{device_id.strip()}"


def _web_sign_in_otp_purpose(*, device_id: str) -> str:
    return f"web-login:{device_id.strip().lower()}"


def _web_sign_in_otp_reuse_window_hours() -> int:
    raw_value = os.getenv("MCP_OTP_REUSE_WINDOW_HOURS", "24").strip()
    try:
        return max(int(raw_value), 1)
    except ValueError:
        return 24


def _send_web_sign_in_code(
    *,
    store: ApiDatabaseStore,
    scheduler: EmailScheduler,
    user: User,
    device_id: str,
) -> None:
    code = generate_one_time_code()
    store.save_registration_code(
        email=_web_sign_in_code_key(user_id=user.user_id, device_id=device_id),
        code=code,
    )
    scheduler.enqueue(
        recipient=user.email,
        subject="Your JurisDigta login code",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your one time JurisDigta login code is: {code}\n"
            "The code expires in 30 minutes.\n"
        ),
        metadata={"event": "sign_in_code", "user_id": user.user_id, "channel": "web"},
    )


def _mfa_email_code_key(*, user_id: str) -> str:
    return f"mfa-login:{user_id.strip()}"


def _mfa_reuse_window_hours() -> int:
    raw_value = os.getenv("MFA_REUSE_WINDOW_HOURS", "0").strip()
    try:
        value = int(raw_value)
    except ValueError:
        return 0
    return max(0, min(value, 168))


def _requires_mfa(*, store: ApiDatabaseStore, user: User) -> bool:
    settings = store.get_user_mfa_settings(user_id=user.user_id)
    if not settings.totp_enabled:
        return False
    if _mfa_reuse_window_hours() < 1:
        return True
    return not store.has_valid_mfa_verification(user_id=user.user_id, purpose=_GLOBAL_MFA_PURPOSE)


def _save_mfa_verification(*, store: ApiDatabaseStore, user: User) -> None:
    reuse_window_hours = _mfa_reuse_window_hours()
    if reuse_window_hours < 1:
        return
    store.save_mfa_verification(
        user_id=user.user_id,
        purpose=_GLOBAL_MFA_PURPOSE,
        expires_in_hours=reuse_window_hours,
    )


def _available_mfa_methods(*, store: ApiDatabaseStore, user: User) -> list[str]:
    methods = ["email"]
    if store.get_user_mfa_settings(user_id=user.user_id).totp_enabled:
        methods.append("totp")
    return methods


def _consume_and_reissue_mfa_challenge(*, store: ApiDatabaseStore, token: str) -> str:
    user_id = store.consume_mfa_login_challenge(token=token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired MFA challenge")
    store.create_mfa_login_challenge(user_id=user_id, token=token)
    return cast(str, user_id)


def _qr_code_uri(provisioning_uri: str) -> str:
    try:
        import qrcode  # type: ignore[import-untyped]
        import qrcode.image.svg  # type: ignore[import-untyped]
    except ModuleNotFoundError:
        return ""
    factory = qrcode.image.svg.SvgPathImage
    image = qrcode.make(provisioning_uri, image_factory=factory)
    svg = cast(str, image.to_string(encoding="unicode"))
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _accepts_any_local_auth_code() -> bool:
    return os.getenv("LOCAL_AUTH_ACCEPT_ANY_CODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _to_plan_response(plan: SubscriptionPlan) -> SubscriptionPlanResponse:
    return SubscriptionPlanResponse(
        plan_code=plan.plan_code,
        display_name=plan.display_name,
        subscription_type=plan.subscription_type,
        price_eur=plan.price_eur,
        max_cases=plan.max_cases,
        max_documents_per_case=plan.max_documents_per_case,
        case_ttl_days=plan.case_ttl_days,
    )


def _to_subscription_response(item: UserSubscription) -> UserSubscriptionResponse:
    return UserSubscriptionResponse(
        subscription_id=item.subscription_id,
        user_id=item.user_id,
        plan_code=item.plan_code,
        status=item.status,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        case_ids_json=item.case_ids_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _is_integrity_error(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    if _psycopg_module is not None and isinstance(exc, _psycopg_module.IntegrityError):
        return True
    return False


def _is_unique_constraint_error(exc: Exception) -> bool:
    if not _is_integrity_error(exc):
        return False
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message or "phone_number" in message or "email" in message


def _conflict_from_integrity_error(exc: Exception) -> HTTPException:
    detail = "User already exists"
    message = str(exc).lower()
    if "phone_number" in message:
        detail = "Phone number is already registered"
    elif "email" in message:
        detail = "Email is already registered"
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
