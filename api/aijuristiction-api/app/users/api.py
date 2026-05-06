from __future__ import annotations

import importlib
import sqlite3
from types import ModuleType
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.security import require_api_key
from app.services.email_scheduler import EmailScheduler
from app.users.notifications import (
    queue_registration_email,
    queue_subscription_change_email,
    queue_subscription_status_email,
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


class UserProfileResponse(BaseModel):
    user_id: str
    phone_number: str | None = None
    email: str
    first_name: str | None = None
    last_name: str | None = None
    full_name: str
    data_processing_consent_at: str | None = None
    data_processing_consent_version: str | None = None


class SignUpRequest(BaseModel):
    phone_number: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    first_name: str | None = None
    last_name: str | None = None
    data_processing_consent_accepted: bool = False
    data_processing_consent_version: str | None = None


class SendRegistrationCodeRequest(BaseModel):
    email: str = Field(min_length=1)


class CompleteRegistrationRequest(SignUpRequest):
    verification_code: str = Field(min_length=4, max_length=8)


class SendSignInCodeRequest(BaseModel):
    phone_number: str = Field(min_length=1)
    device_id: str = Field(min_length=1)


class VerifySignInCodeRequest(SendSignInCodeRequest):
    verification_code: str = Field(min_length=4, max_length=8)


class DeviceSignInRequest(SendSignInCodeRequest):
    device_token: str = Field(min_length=1)


class SignInByPhoneRequest(BaseModel):
    phone_number: str = Field(min_length=1)


class SignInRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UpdateUserProfileRequest(BaseModel):
    phone_number: str = Field(min_length=1)
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None


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


_payment_sessions: dict[str, dict[str, str | int]] = {}
_ALLOWED_SUCCESS_PHONE = "+421944400166"


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
    if not store.verify_registration_code(
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
    is_valid = store.verify_registration_code(
        email=_sign_in_code_key(phone_number=payload.phone_number, device_id=payload.device_id),
        code=payload.verification_code,
    )
    if not is_valid:
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


@router.post("/sign-in", response_model=UserProfileResponse)
def sign_in(payload: SignInRequest, store: ApiDatabaseStore = Depends(get_user_store)) -> UserProfileResponse:
    user = store.authenticate_user(email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _to_user_profile_response(user)


@router.patch("/{user_id}", response_model=UserProfileResponse)
def update_user_profile(
    user_id: str,
    payload: UpdateUserProfileRequest,
    store: ApiDatabaseStore = Depends(get_user_store),
) -> UserProfileResponse:
    try:
        user = store.update_user(
            user_id=user_id,
            phone_number=payload.phone_number,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        if not _is_unique_constraint_error(exc):
            raise
        raise _conflict_from_integrity_error(exc) from exc
    return _to_user_profile_response(user)


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

    try:
        subscription = store.request_subscription_change(user_id=user_id, plan_code=plan_code)
        subscription = store.update_subscription_status(subscription_id=subscription.subscription_id, status="paying")
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

    if user.phone_number != _ALLOWED_SUCCESS_PHONE:
        payment["payment_status"] = "failed"
        item = store.update_subscription_status(subscription_id=subscription_id, status="canceled")
        queue_subscription_status_email(scheduler=scheduler, user=user, item=item)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": "Payment failed (simulated). Subscription was not upgraded.",
                "subscription": _to_subscription_response(item).model_dump(),
            },
        )

    payment["payment_status"] = "paid"
    item = store.update_subscription_status(subscription_id=subscription_id, status="paid")
    queue_subscription_status_email(scheduler=scheduler, user=user, item=item)
    return _to_subscription_response(item)


def _to_user_profile_response(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=user.user_id,
        phone_number=user.phone_number,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        data_processing_consent_at=user.data_processing_consent_at,
        data_processing_consent_version=user.data_processing_consent_version,
    )


def _to_device_auth_user_profile_response(*, user: User, token: str) -> DeviceAuthUserProfileResponse:
    return DeviceAuthUserProfileResponse(
        user_id=user.user_id,
        phone_number=user.phone_number,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        data_processing_consent_at=user.data_processing_consent_at,
        data_processing_consent_version=user.data_processing_consent_version,
        device_auth_token=token,
    )


def _now_if_accepted(accepted: bool) -> str | None:
    if not accepted:
        return None
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _sign_in_code_key(*, phone_number: str, device_id: str) -> str:
    return f"signin:{phone_number.strip()}:{device_id.strip()}"


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
