from __future__ import annotations

from dataclasses import asdict
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.security import require_api_key
from aijurisdictionagents.api_db import (
    AIModelAdminAuditEvent,
    AIModelCredential,
    AIModelGroup,
    AIModelGroupMembership,
    AIModelProfile,
    AIModelProvider,
    AITaskRoutePolicy,
    AdminUser,
    ApiDatabaseStore,
    User,
)

router = APIRouter(prefix="/v1/admin/ai-models", tags=["ai-model-admin"])
_DEFAULT_ADMIN_EMAIL = "mmaideveloper@gmail.com"


class AdminContext(BaseModel):
    user_id: str
    email: str


class AdminUserSummaryResponse(BaseModel):
    user_id: str
    phone_number: str | None = None
    email: str
    full_name: str
    role: str = "user"
    is_enabled: bool = True
    created_at: str | None = None


class AIModelProviderResponse(BaseModel):
    provider_id: str
    provider_code: str
    provider_type: str
    display_name: str
    base_url: str
    api_version: str
    region: str
    data_zone: str
    is_external: bool
    is_local: bool
    health_check_url: str
    enabled: bool
    created_at: str
    updated_at: str


class AIModelProviderUpsertRequest(BaseModel):
    provider_code: str = Field(min_length=1)
    provider_type: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    base_url: str = ""
    api_version: str = ""
    region: str = ""
    data_zone: str = ""
    is_external: bool = False
    is_local: bool = False
    health_check_url: str = ""
    enabled: bool = True
    reason: str = ""


class AIModelProfileResponse(BaseModel):
    model_profile_id: str
    provider_id: str
    model_code: str
    deployment_name: str
    context_window_tokens: int
    input_price_per_1m: float
    cached_input_price_per_1m: float
    output_price_per_1m: float
    billing_currency: str
    effective_from: str | None
    effective_to: str | None
    eu_data_zone_capable: bool
    is_default_for_free: bool
    enabled: bool
    created_at: str
    updated_at: str


class AIModelProfileUpsertRequest(BaseModel):
    provider_id: str = Field(min_length=1)
    model_code: str = Field(min_length=1)
    deployment_name: str = ""
    context_window_tokens: int = Field(default=0, ge=0)
    input_price_per_1m: float = Field(default=0.0, ge=0)
    cached_input_price_per_1m: float = Field(default=0.0, ge=0)
    output_price_per_1m: float = Field(default=0.0, ge=0)
    billing_currency: str = "USD"
    effective_from: str | None = None
    effective_to: str | None = None
    eu_data_zone_capable: bool = False
    is_default_for_free: bool = False
    enabled: bool = True
    model_profile_id: str | None = None
    reason: str = ""


class AIModelCredentialResponse(BaseModel):
    credential_id: str
    provider_id: str
    credential_name: str
    secret_type: str
    secret_preview: str
    secret_value: str | None
    enabled: bool
    created_at: str
    updated_at: str
    last_revealed_at: str | None


class AIModelCredentialUpsertRequest(BaseModel):
    credential_name: str = "default"
    secret_type: str = "api_key"
    secret_value: str = Field(min_length=1)
    enabled: bool = True
    credential_id: str | None = None
    reason: str = ""


class AIModelCredentialPatchRequest(BaseModel):
    enabled: bool
    reason: str = ""


class AITaskRoutePolicyResponse(BaseModel):
    policy_id: str
    task_type: str
    plan_code: str
    model_group_id: str | None
    preferred_external_model_profile_id: str | None
    preferred_local_model_profile_id: str | None
    allow_external: bool
    require_external_ack: bool
    require_eu_data_zone: bool
    fallback_local_on_error: bool
    fallback_local_on_budget: bool
    max_cost_eur: float
    priority: int
    enabled: bool
    created_at: str
    updated_at: str


class AITaskRoutePolicyUpsertRequest(BaseModel):
    task_type: str = Field(default="default", min_length=1)
    plan_code: str = ""
    model_group_id: str | None = None
    preferred_external_model_profile_id: str | None = None
    preferred_local_model_profile_id: str | None = None
    allow_external: bool = False
    require_external_ack: bool = True
    require_eu_data_zone: bool = True
    fallback_local_on_error: bool = True
    fallback_local_on_budget: bool = True
    max_cost_eur: float = Field(default=0.0, ge=0)
    priority: int = 0
    enabled: bool = True
    policy_id: str | None = None
    reason: str = ""


class AIModelGroupResponse(BaseModel):
    model_group_id: str
    group_code: str
    display_name: str
    priority: int
    enabled: bool
    created_at: str
    updated_at: str


class AIModelGroupUpsertRequest(BaseModel):
    group_code: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    priority: int = 0
    enabled: bool = True
    model_group_id: str | None = None
    reason: str = ""


class AIModelGroupMembershipResponse(BaseModel):
    model_group_id: str
    user_id: str
    email: str
    full_name: str
    created_at: str


class AIModelGroupMembershipRequest(BaseModel):
    user_id: str = Field(min_length=1)
    reason: str = ""


class AIModelAdminAuditEventResponse(BaseModel):
    audit_event_id: str
    admin_user_id: str
    admin_email: str
    action: str
    entity_type: str
    entity_id: str
    old_value_summary: str
    new_value_summary: str
    reason: str
    correlation_id: str
    created_at: str


class AIModelAdminDashboardResponse(BaseModel):
    admin: AdminContext
    providers: list[AIModelProviderResponse]
    profiles: list[AIModelProfileResponse]
    credentials: list[AIModelCredentialResponse]
    policies: list[AITaskRoutePolicyResponse]
    groups: list[AIModelGroupResponse]
    memberships: list[AIModelGroupMembershipResponse]
    users: list[AdminUserSummaryResponse]
    audit_events: list[AIModelAdminAuditEventResponse]
    route_priority: list[str]
    compliance_notes: list[str]
    grafana_url: str


def get_admin_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


def require_ai_model_admin(
    request: Request,
    store: ApiDatabaseStore = Depends(get_admin_store),
    _: None = Depends(require_api_key),
    cf_access_email: str | None = Header(default=None, alias="cf-access-authenticated-user-email"),
    admin_api_key: str | None = Header(default=None, alias="x-admin-api-key"),
    local_admin_user_id: str | None = Header(default=None, alias="x-jurisdigta-admin-user-id"),
) -> AdminContext:
    if _legacy_admin_key_valid(admin_api_key):
        return AdminContext(user_id="", email="legacy-admin-key")

    admin_emails = _configured_admin_emails()
    candidate_email = (cf_access_email or "").strip().lower()
    candidate_user_id = ""
    candidate_is_admin_role = False
    if candidate_email:
        user = store.find_user_by_email(email=candidate_email)
        if user is not None:
            candidate_user_id = user.user_id
            candidate_is_admin_role = user.role == "admin" and user.is_enabled
    elif local_admin_user_id and _is_local_request(request):
        user = store.find_user_by_id(user_id=local_admin_user_id.strip())
        if user is not None:
            candidate_email = user.email.strip().lower()
            candidate_user_id = user.user_id
            candidate_is_admin_role = user.role == "admin" and user.is_enabled

    if not candidate_email or (candidate_email not in admin_emails and not candidate_is_admin_role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required")
    return AdminContext(user_id=candidate_user_id, email=candidate_email)


@router.get("", response_model=AIModelAdminDashboardResponse)
def get_ai_model_admin_dashboard(
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelAdminDashboardResponse:
    return AIModelAdminDashboardResponse(
        admin=admin,
        providers=[_provider_response(item) for item in store.list_ai_model_providers()],
        profiles=[_profile_response(item) for item in store.list_ai_model_profiles()],
        credentials=[_credential_response(item) for item in store.list_ai_model_credentials(reveal=False)],
        policies=[_policy_response(item) for item in store.list_ai_task_route_policies()],
        groups=[_group_response(item) for item in store.list_ai_model_groups()],
        memberships=[_membership_response(item) for item in store.list_ai_model_group_users()],
        users=[_user_summary_response(item) for item in store.list_users_for_admin(limit=200)],
        audit_events=[_audit_response(item) for item in store.list_ai_model_admin_audit_events(limit=25)],
        route_priority=[
            "user local override",
            "highest-priority active group policy",
            "default paid model policy",
            "local fallback",
        ],
        compliance_notes=[
            "External model enablement can move case data outside JurisDigta-controlled infrastructure.",
            "Keep provider secrets in backend secret storage; this API never returns secret values.",
            "Admin policy changes are audited with actor, entity, summaries, reason, and correlation id.",
        ],
        grafana_url=os.getenv("GRAFANA_ROOT_URL", "https://admin.jurisdigta.eu/grafana/").strip(),
    )


@router.post("/providers", response_model=AIModelProviderResponse)
def upsert_ai_model_provider(
    payload: AIModelProviderUpsertRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelProviderResponse:
    existing = {item.provider_code: item for item in store.list_ai_model_providers()}.get(
        payload.provider_code.strip().lower()
    )
    provider = store.upsert_ai_model_provider(
        provider_code=payload.provider_code,
        provider_type=payload.provider_type,
        display_name=payload.display_name,
        base_url=payload.base_url,
        api_version=payload.api_version,
        region=payload.region,
        data_zone=payload.data_zone,
        is_external=payload.is_external,
        is_local=payload.is_local,
        health_check_url=payload.health_check_url,
        enabled=payload.enabled,
    )
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="upsert",
        entity_type="ai_model_provider",
        entity_id=provider.provider_id,
        old=existing,
        new=provider,
        reason=payload.reason,
    )
    return _provider_response(provider)


@router.post("/profiles", response_model=AIModelProfileResponse)
def upsert_ai_model_profile(
    payload: AIModelProfileUpsertRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelProfileResponse:
    existing = {item.model_profile_id: item for item in store.list_ai_model_profiles()}.get(
        payload.model_profile_id or f"{payload.provider_id}:{payload.model_code.strip()}"
    )
    try:
        profile = store.upsert_ai_model_profile(
            provider_id=payload.provider_id,
            model_code=payload.model_code,
            deployment_name=payload.deployment_name,
            context_window_tokens=payload.context_window_tokens,
            input_price_per_1m=payload.input_price_per_1m,
            cached_input_price_per_1m=payload.cached_input_price_per_1m,
            output_price_per_1m=payload.output_price_per_1m,
            billing_currency=payload.billing_currency,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            eu_data_zone_capable=payload.eu_data_zone_capable,
            is_default_for_free=payload.is_default_for_free,
            enabled=payload.enabled,
            model_profile_id=payload.model_profile_id,
        )
    except Exception as exc:
        if "foreign key" not in str(exc).lower():
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider does not exist") from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="upsert",
        entity_type="ai_model_profile",
        entity_id=profile.model_profile_id,
        old=existing,
        new=profile,
        reason=payload.reason,
    )
    return _profile_response(profile)


@router.get("/credentials", response_model=list[AIModelCredentialResponse])
def list_ai_model_credentials(
    reveal: bool = False,
    _: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> list[AIModelCredentialResponse]:
    return [_credential_response(item) for item in store.list_ai_model_credentials(reveal=reveal)]


@router.post("/providers/{provider_id}/credentials", response_model=AIModelCredentialResponse)
def upsert_ai_model_credential(
    provider_id: str,
    payload: AIModelCredentialUpsertRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelCredentialResponse:
    existing = {item.credential_id: item for item in store.list_ai_model_credentials()}.get(
        payload.credential_id or f"{provider_id}:{payload.secret_type.strip().lower()}:{payload.credential_name.strip().lower()}"
    )
    try:
        credential = store.upsert_ai_model_credential(
            provider_id=provider_id,
            credential_name=payload.credential_name,
            secret_type=payload.secret_type,
            secret_value=payload.secret_value,
            enabled=payload.enabled,
            credential_id=payload.credential_id,
        )
    except Exception as exc:
        if "foreign key" not in str(exc).lower():
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider does not exist") from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="upsert",
        entity_type="ai_model_credential",
        entity_id=credential.credential_id,
        old=existing,
        new=credential,
        reason=payload.reason,
    )
    return _credential_response(credential)


@router.patch("/credentials/{credential_id}", response_model=AIModelCredentialResponse)
def patch_ai_model_credential(
    credential_id: str,
    payload: AIModelCredentialPatchRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelCredentialResponse:
    existing = {item.credential_id: item for item in store.list_ai_model_credentials()}.get(credential_id)
    try:
        credential = store.set_ai_model_credential_enabled(
            credential_id=credential_id,
            enabled=payload.enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found") from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="update",
        entity_type="ai_model_credential",
        entity_id=credential.credential_id,
        old=existing,
        new=credential,
        reason=payload.reason,
    )
    return _credential_response(credential)


@router.post("/policies", response_model=AITaskRoutePolicyResponse)
def upsert_ai_task_route_policy(
    payload: AITaskRoutePolicyUpsertRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AITaskRoutePolicyResponse:
    if payload.allow_external and not payload.preferred_external_model_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="preferred_external_model_profile_id is required when external routing is enabled",
        )
    existing = {item.policy_id: item for item in store.list_ai_task_route_policies()}.get(
        payload.policy_id or f"{payload.task_type}:{payload.plan_code}:{payload.model_group_id or 'default'}"
    )
    policy = store.upsert_ai_task_route_policy(
        task_type=payload.task_type,
        plan_code=payload.plan_code,
        model_group_id=payload.model_group_id,
        preferred_external_model_profile_id=payload.preferred_external_model_profile_id,
        preferred_local_model_profile_id=payload.preferred_local_model_profile_id,
        allow_external=payload.allow_external,
        require_external_ack=payload.require_external_ack,
        require_eu_data_zone=payload.require_eu_data_zone,
        fallback_local_on_error=payload.fallback_local_on_error,
        fallback_local_on_budget=payload.fallback_local_on_budget,
        max_cost_eur=payload.max_cost_eur,
        priority=payload.priority,
        enabled=payload.enabled,
        policy_id=payload.policy_id,
    )
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="upsert",
        entity_type="ai_task_route_policy",
        entity_id=policy.policy_id,
        old=existing,
        new=policy,
        reason=payload.reason,
    )
    return _policy_response(policy)


@router.post("/groups", response_model=AIModelGroupResponse)
def upsert_ai_model_group(
    payload: AIModelGroupUpsertRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelGroupResponse:
    existing = {item.group_code: item for item in store.list_ai_model_groups()}.get(
        payload.group_code.strip().lower()
    )
    group = store.upsert_ai_model_group(
        group_code=payload.group_code,
        display_name=payload.display_name,
        priority=payload.priority,
        enabled=payload.enabled,
        model_group_id=payload.model_group_id,
    )
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="upsert",
        entity_type="ai_model_group",
        entity_id=group.model_group_id,
        old=existing,
        new=group,
        reason=payload.reason,
    )
    return _group_response(group)


@router.delete("/groups/{model_group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_model_group(
    model_group_id: str,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> None:
    existing = {item.model_group_id: item for item in store.list_ai_model_groups()}.get(model_group_id)
    store.delete_ai_model_group(model_group_id=model_group_id)
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="delete",
        entity_type="ai_model_group",
        entity_id=model_group_id,
        old=existing,
        new=None,
        reason="Deleted from admin model-management page.",
    )


@router.post("/groups/{model_group_id}/members", response_model=AIModelGroupMembershipResponse)
def add_ai_model_group_member(
    model_group_id: str,
    payload: AIModelGroupMembershipRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelGroupMembershipResponse:
    try:
        membership = store.add_ai_model_group_user(model_group_id=model_group_id, user_id=payload.user_id)
    except Exception as exc:
        if "foreign key" not in str(exc).lower():
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group or user does not exist") from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="add_member",
        entity_type="ai_model_group_membership",
        entity_id=f"{model_group_id}:{payload.user_id}",
        old=None,
        new=membership,
        reason=payload.reason,
    )
    return _membership_response(membership)


@router.delete("/groups/{model_group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_ai_model_group_member(
    model_group_id: str,
    user_id: str,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> None:
    existing = {
        f"{item.model_group_id}:{item.user_id}": item for item in store.list_ai_model_group_users()
    }.get(f"{model_group_id}:{user_id}")
    store.remove_ai_model_group_user(model_group_id=model_group_id, user_id=user_id)
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="remove_member",
        entity_type="ai_model_group_membership",
        entity_id=f"{model_group_id}:{user_id}",
        old=existing,
        new=None,
        reason="Removed from admin model-management page.",
    )


def _configured_admin_emails() -> set[str]:
    raw = os.getenv("JURISDIGTA_ADMIN_EMAILS", "").strip()
    if not raw or raw.lower() == "unknown-variable":
        raw = os.getenv("JURISDIGTA_UNLIMITED_ACCESS_EMAILS", "").strip()
    if not raw or raw.lower() == "unknown-variable":
        raw = _DEFAULT_ADMIN_EMAIL
    return {item.strip().lower() for item in raw.replace(";", ",").split(",") if item.strip()}


def _is_local_request(request: Request) -> bool:
    host = (request.client.host if request.client else "").strip().lower()
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _legacy_admin_key_valid(value: str | None) -> bool:
    expected = os.getenv("JURISDIGTA_ADMIN_API_KEY", "").strip() or os.getenv("ADMIN_API_KEY", "").strip()
    return bool(expected and value and value.strip() == expected)


def _record_audit(
    *,
    store: ApiDatabaseStore,
    request: Request,
    admin: AdminContext,
    action: str,
    entity_type: str,
    entity_id: str,
    old: Any,
    new: Any,
    reason: str,
) -> None:
    store.record_ai_model_admin_audit_event(
        admin_user_id=admin.user_id,
        admin_email=admin.email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value_summary=_summary(old),
        new_value_summary=_summary(new),
        reason=reason,
        correlation_id=str(getattr(request.state, "correlation_id", "")),
    )


def _summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    data = asdict(value) if hasattr(value, "__dataclass_fields__") else dict(value)
    return {
        key: item
        for key, item in data.items()
        if key
        not in {
            "mcp_api_key_hash",
            "password_hash",
            "question_preview",
            "audit_metadata",
            "protected_secret",
            "secret_value",
        }
    }


def _provider_response(item: AIModelProvider) -> AIModelProviderResponse:
    return AIModelProviderResponse(**asdict(item))


def _profile_response(item: AIModelProfile) -> AIModelProfileResponse:
    return AIModelProfileResponse(**asdict(item))


def _credential_response(item: AIModelCredential) -> AIModelCredentialResponse:
    return AIModelCredentialResponse(
        credential_id=item.credential_id,
        provider_id=item.provider_id,
        credential_name=item.credential_name,
        secret_type=item.secret_type,
        secret_preview=item.secret_preview,
        secret_value=item.secret_value,
        enabled=item.enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
        last_revealed_at=item.last_revealed_at,
    )


def _policy_response(item: AITaskRoutePolicy) -> AITaskRoutePolicyResponse:
    return AITaskRoutePolicyResponse(**asdict(item))


def _group_response(item: AIModelGroup) -> AIModelGroupResponse:
    return AIModelGroupResponse(**asdict(item))


def _membership_response(item: AIModelGroupMembership) -> AIModelGroupMembershipResponse:
    return AIModelGroupMembershipResponse(**asdict(item))


def _audit_response(item: AIModelAdminAuditEvent) -> AIModelAdminAuditEventResponse:
    return AIModelAdminAuditEventResponse(**asdict(item))


def _user_summary_response(item: AdminUser | User) -> AdminUserSummaryResponse:
    return AdminUserSummaryResponse(
        user_id=item.user_id,
        phone_number=item.phone_number,
        email=item.email,
        full_name=item.full_name,
        role=item.role,
        is_enabled=item.is_enabled,
        created_at=item.created_at,
    )
