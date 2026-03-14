from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.security import require_api_key
from app.services.email_scheduler import EmailScheduler
from app.users.notifications import (
    queue_registration_email,
    queue_subscription_change_email,
    queue_subscription_status_email,
)

from aijurisdictionagents.api_db import ApiDatabaseStore, SubscriptionPlan, User, UserSubscription

router = APIRouter(prefix="/v1/users", tags=["users"], dependencies=[Depends(require_api_key)])


class UserProfileResponse(BaseModel):
    user_id: str
    phone_number: str | None = None
    email: str
    first_name: str | None = None
    last_name: str | None = None
    full_name: str


class SignUpRequest(BaseModel):
    phone_number: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    first_name: str | None = None
    last_name: str | None = None


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
        )
    except sqlite3.IntegrityError as exc:
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
    except sqlite3.IntegrityError as exc:
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
    except sqlite3.IntegrityError as exc:
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


def _to_user_profile_response(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=user.user_id,
        phone_number=user.phone_number,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
    )


def _to_plan_response(plan: SubscriptionPlan) -> SubscriptionPlanResponse:
    return SubscriptionPlanResponse(
        plan_code=plan.plan_code,
        display_name=plan.display_name,
        subscription_type=plan.subscription_type,
        price_eur=plan.price_eur,
        max_cases=plan.max_cases,
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


def _conflict_from_integrity_error(exc: sqlite3.IntegrityError) -> HTTPException:
    detail = "User already exists"
    message = str(exc).lower()
    if "phone_number" in message:
        detail = "Phone number is already registered"
    elif "email" in message:
        detail = "Email is already registered"
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
