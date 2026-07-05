from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.ai_model_admin_api import AdminContext, get_admin_store, require_ai_model_admin
from app.cases_api import build_case_export_response
from aijurisdictionagents.api_db import AdminCaseUser, ApiDatabaseStore, Case

router = APIRouter(prefix="/v1/admin/cases", tags=["admin-cases"])


class AdminCaseUserResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    is_enabled: bool
    created_at: str | None = None


class AdminCaseUserSearchResponse(BaseModel):
    items: list[AdminCaseUserResponse]
    total: int
    limit: int


class AdminCaseResponse(BaseModel):
    case_id: str
    user_id: str
    target_user_email: str
    title: str
    status: str
    created_at: str
    updated_at: str


class AdminCaseListResponse(BaseModel):
    user: AdminCaseUserResponse
    cases: list[AdminCaseResponse]


class AdminCaseDeleteRequest(BaseModel):
    user_id: str = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=500)


class AdminCaseDeleteResponse(BaseModel):
    case: AdminCaseResponse
    deleted: bool


@router.get("/users", response_model=AdminCaseUserSearchResponse)
def search_admin_case_users(
    email: str,
    limit: int = 25,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AdminCaseUserSearchResponse:
    _ = admin
    bounded_limit = min(max(limit, 1), 100)
    users = store.search_case_users_for_admin(email=email, limit=bounded_limit)
    return AdminCaseUserSearchResponse(
        items=[_admin_case_user_response(item) for item in users],
        total=len(users),
        limit=bounded_limit,
    )


@router.get("/users/{user_id}/cases", response_model=AdminCaseListResponse)
def list_admin_user_cases(
    user_id: str,
    include_deleted: bool = True,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AdminCaseListResponse:
    _ = admin
    user = _get_admin_case_user(store=store, user_id=user_id)
    cases = store.list_cases(user_id=user_id, include_deleted=include_deleted)
    return AdminCaseListResponse(
        user=_admin_case_user_response(user),
        cases=[_admin_case_response(case=item, target_user_email=user.email) for item in cases],
    )


@router.delete("/{case_id}", response_model=AdminCaseDeleteResponse)
def delete_admin_case(
    case_id: str,
    payload: AdminCaseDeleteRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AdminCaseDeleteResponse:
    user = _get_admin_case_user(store=store, user_id=payload.user_id)
    try:
        before = store.get_case(case_id=case_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    if before.user_id != payload.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found for target user")

    try:
        after = store.soft_delete_case_for_admin(case_id=case_id, user_id=payload.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc

    store.record_ai_model_admin_audit_event(
        admin_user_id=admin.user_id,
        admin_email=admin.email,
        action="case.soft_delete",
        entity_type="case",
        entity_id=case_id,
        old_value_summary={
            "case_id": before.case_id,
            "title": before.title,
            "status": before.status,
            "created_at": before.created_at,
            "updated_at": before.updated_at,
            "target_user_id": user.user_id,
            "target_user_email": user.email,
        },
        new_value_summary={
            "case_id": after.case_id,
            "title": after.title,
            "status": after.status,
            "created_at": after.created_at,
            "updated_at": after.updated_at,
            "target_user_id": user.user_id,
            "target_user_email": user.email,
        },
        reason=payload.reason,
        correlation_id=str(getattr(request.state, "correlation_id", "")),
    )
    return AdminCaseDeleteResponse(
        case=_admin_case_response(case=after, target_user_email=user.email),
        deleted=before.status != "deleted" and after.status == "deleted",
    )


@router.get("/{case_id}/export")
def export_admin_case(
    case_id: str,
    user_id: str,
    reason: str,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> Response:
    normalized_reason = reason.strip()
    if len(normalized_reason) < 3:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Export reason is required")
    user = _get_admin_case_user(store=store, user_id=user_id)
    try:
        case = store.get_case(case_id=case_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    if case.user_id != user_id or case.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found for target user")

    store.record_ai_model_admin_audit_event(
        admin_user_id=admin.user_id,
        admin_email=admin.email,
        action="case.export",
        entity_type="case",
        entity_id=case_id,
        old_value_summary={
            "case_id": case.case_id,
            "title": case.title,
            "status": case.status,
            "target_user_id": user.user_id,
            "target_user_email": user.email,
        },
        new_value_summary={
            "exported": True,
            "case_id": case.case_id,
            "target_user_id": user.user_id,
            "target_user_email": user.email,
        },
        reason=normalized_reason,
        correlation_id=str(getattr(request.state, "correlation_id", "")),
    )
    return build_case_export_response(
        case=case,
        user_id=user_id,
        store=store,
        exported_by=f"admin:{admin.email}",
    )


def _get_admin_case_user(*, store: ApiDatabaseStore, user_id: str) -> AdminCaseUser:
    user = store.find_user_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminCaseUser(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_enabled=user.is_enabled,
        created_at=user.created_at,
    )


def _admin_case_user_response(item: AdminCaseUser) -> AdminCaseUserResponse:
    return AdminCaseUserResponse(**asdict(item))


def _admin_case_response(*, case: Case, target_user_email: str) -> AdminCaseResponse:
    return AdminCaseResponse(
        case_id=case.case_id,
        user_id=case.user_id,
        target_user_email=target_user_email,
        title=case.title,
        status=case.status,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )
