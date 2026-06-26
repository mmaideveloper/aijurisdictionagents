from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.ai_model_admin_api import AdminContext, get_admin_store, require_ai_model_admin
from aijurisdictionagents.api_db import AdminUser, ApiDatabaseStore

router = APIRouter(prefix="/v1/admin/users", tags=["admin-users"])


class AdminUserResponse(BaseModel):
    user_id: str
    phone_number: str | None = None
    email: str
    full_name: str
    role: str
    is_enabled: bool
    created_at: str | None = None


class UpdateAdminUserRequest(BaseModel):
    role: str = Field(pattern="^(admin|user|Admin|User)$")
    is_enabled: bool
    reason: str = ""


@router.get("", response_model=list[AdminUserResponse])
def list_admin_users(
    query: str = "",
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> list[AdminUserResponse]:
    _ = admin
    return [_admin_user_response(item) for item in store.list_users_for_admin(limit=200, query=query)]


@router.patch("/{user_id}", response_model=AdminUserResponse)
def update_admin_user(
    user_id: str,
    payload: UpdateAdminUserRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AdminUserResponse:
    if user_id == admin.user_id and (payload.role.lower() != "admin" or not payload.is_enabled):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot remove their own admin access from this page.",
        )

    old = {item.user_id: item for item in store.list_users_for_admin(limit=500)}.get(user_id)
    try:
        updated = store.update_admin_user(
            user_id=user_id,
            role=payload.role,
            is_enabled=payload.is_enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc

    store.record_ai_model_admin_audit_event(
        admin_user_id=admin.user_id,
        admin_email=admin.email,
        action="update",
        entity_type="user",
        entity_id=user_id,
        old_value_summary=_summary(old),
        new_value_summary=_summary(updated),
        reason=payload.reason,
        correlation_id=str(getattr(request.state, "correlation_id", "")),
    )
    return _admin_user_response(updated)


def _admin_user_response(item: AdminUser) -> AdminUserResponse:
    return AdminUserResponse(**asdict(item))


def _summary(item: AdminUser | None) -> dict[str, object]:
    if item is None:
        return {}
    return {
        "user_id": item.user_id,
        "email": item.email,
        "role": item.role,
        "is_enabled": item.is_enabled,
    }
