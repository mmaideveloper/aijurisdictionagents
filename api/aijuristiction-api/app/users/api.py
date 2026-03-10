from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.security import require_api_key

from aijurisdictionagents.api_db import ApiDatabaseStore, User

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


def get_user_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


@router.post("/sign-up", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpRequest, store: ApiDatabaseStore = Depends(get_user_store)) -> UserProfileResponse:
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


def _to_user_profile_response(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=user.user_id,
        phone_number=user.phone_number,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
    )


def _conflict_from_integrity_error(exc: sqlite3.IntegrityError) -> HTTPException:
    detail = "User already exists"
    message = str(exc).lower()
    if "phone_number" in message:
        detail = "Phone number is already registered"
    elif "email" in message:
        detail = "Email is already registered"
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
