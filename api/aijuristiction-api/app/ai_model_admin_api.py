from __future__ import annotations

from dataclasses import asdict
import os
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.ollama_admin_service import (
    OllamaAdminService,
    OllamaInstalledModel,
    OllamaModelJob,
    OllamaModelJobRegistry,
    validate_ollama_registry_model_name,
)
from app.security import require_api_key
from aijurisdictionagents.api_db import (
    AIModelAdminAuditEvent,
    AIModelCredential,
    AIModelGroup,
    AIModelGroupMembership,
    AIModelProfile,
    AIModelProvider,
    AITaskRoutePolicy,
    AIModelRouteSelection,
    AIModelUserOverride,
    AdminUser,
    ApiDatabaseStore,
    User,
)

router = APIRouter(prefix="/v1/admin/ai-models", tags=["ai-model-admin"])
_DEFAULT_ADMIN_EMAIL = "mmaideveloper@gmail.com"
_LOCAL_DEFAULT_PROFILE_ID = "local_ollama_default"
_ollama_job_registry = OllamaModelJobRegistry()


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


class AdminUsersPageSummaryResponse(BaseModel):
    total: int
    limit: int
    offset: int


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
    model_parameters: dict[str, bool | int | float | str | None]
    enabled: bool
    created_at: str
    updated_at: str
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


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
    model_parameters: dict[str, bool | int | float | str | None] = Field(default_factory=dict)
    enabled: bool = True
    reason: str = ""


class AIModelProviderDeleteRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AIModelDeleteRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AIModelProfileResponse(BaseModel):
    model_profile_id: str
    provider_id: str
    model_code: str
    deployment_name: str
    model_parameters: dict[str, bool | int | float | str | None]
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
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


class AIModelProfileUpsertRequest(BaseModel):
    provider_id: str = Field(min_length=1)
    model_code: str = Field(min_length=1)
    deployment_name: str = ""
    model_parameters: dict[str, bool | int | float | str | None] = Field(default_factory=dict)
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
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


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
    deleted_at: str | None
    deleted_by_admin_user_id: str
    deleted_reason: str


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


class AIModelUserOverrideRequest(BaseModel):
    model_profile_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class AIModelUserOverrideDeleteRequest(BaseModel):
    reason: str = Field(min_length=1)


class AIModelUserOverrideResponse(BaseModel):
    override_id: str
    user_id: str
    model_profile_id: str
    enabled: bool
    created_by_admin_user_id: str
    updated_by_admin_user_id: str
    disabled_by_admin_user_id: str
    created_reason: str
    updated_reason: str
    disabled_reason: str
    created_at: str
    updated_at: str
    disabled_at: str | None


class AIModelEffectiveRouteResponse(BaseModel):
    route_type: str
    task_type: str
    plan_code: str
    provider_id: str | None
    provider_code: str | None
    provider_display_name: str | None
    model_profile_id: str | None
    model_code: str | None
    deployment_name: str | None
    is_external: bool
    is_local: bool
    requires_external_ack: bool
    reason: str


class AIModelUserOverrideDetailResponse(BaseModel):
    user: AdminUserSummaryResponse
    override: AIModelUserOverrideResponse | None
    effective_route: AIModelEffectiveRouteResponse


class AdminUserSearchResponse(BaseModel):
    items: list[AdminUserSummaryResponse]
    total: int
    limit: int


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
    users_page: AdminUsersPageSummaryResponse
    audit_events: list[AIModelAdminAuditEventResponse]
    route_priority: list[str]
    compliance_notes: list[str]
    grafana_url: str


class OllamaModelInventoryItemResponse(BaseModel):
    name: str
    model: str
    modified_at: str
    size: int
    digest: str
    details: dict[str, Any]
    installed: bool
    configured_profile_ids: list[str]
    active_policy_ids: list[str]
    is_default: bool
    is_running: bool
    removable: bool
    removal_blockers: list[str]


class OllamaModelInventoryResponse(BaseModel):
    base_url: str
    models: list[OllamaModelInventoryItemResponse]


class OllamaModelImportRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=500)


class OllamaModelDefaultRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class OllamaModelRemoveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class OllamaModelJobResponse(BaseModel):
    job_id: str
    action: str
    model: str
    status: str
    message: str
    created_at: str
    updated_at: str


def get_admin_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


def get_ollama_admin_service() -> OllamaAdminService:
    return OllamaAdminService()


def get_ollama_job_registry() -> OllamaModelJobRegistry:
    return _ollama_job_registry


def require_ai_model_admin(
    request: Request,
    store: ApiDatabaseStore = Depends(get_admin_store),
    _: None = Depends(require_api_key),
    cf_access_email: str | None = Header(default=None, alias="cf-access-authenticated-user-email"),
    admin_api_key: str | None = Header(default=None, alias="x-admin-api-key"),
    local_admin_user_id: str | None = Header(default=None, alias="x-jurisdigta-admin-user-id"),
    device_id: str | None = Header(default=None, alias="x-jurisdigta-device-id"),
    device_token: str | None = Header(default=None, alias="x-jurisdigta-device-token"),
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
    elif local_admin_user_id and device_id and device_token:
        user = store.authenticate_user_device_auth_token(
            user_id=local_admin_user_id.strip(),
            device_id=device_id,
            token=device_token,
        )
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
    users_limit = 25
    return AIModelAdminDashboardResponse(
        admin=admin,
        providers=[_provider_response(item) for item in store.list_ai_model_providers()],
        profiles=[_profile_response(item) for item in store.list_ai_model_profiles()],
        credentials=[_credential_response(item) for item in store.list_ai_model_credentials(reveal=False)],
        policies=[_policy_response(item) for item in store.list_ai_task_route_policies()],
        groups=[_group_response(item) for item in store.list_ai_model_groups()],
        memberships=[_membership_response(item) for item in store.list_ai_model_group_users()],
        users=[_user_summary_response(item) for item in store.list_users_for_admin(limit=users_limit)],
        users_page=AdminUsersPageSummaryResponse(
            total=store.count_users_for_admin(),
            limit=users_limit,
            offset=0,
        ),
        audit_events=[_audit_response(item) for item in store.list_ai_model_admin_audit_events(limit=25)],
        route_priority=[
            "enabled per-user model override",
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


@router.get("/users", response_model=AdminUserSearchResponse)
def search_ai_model_assignment_users(
    email: str,
    limit: int = 25,
    _: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AdminUserSearchResponse:
    bounded_limit = min(max(limit, 1), 100)
    if not email.strip():
        return AdminUserSearchResponse(items=[], total=0, limit=bounded_limit)
    users = store.list_users_for_admin(limit=bounded_limit, query=email)
    email_query = email.strip().lower()
    matches = [item for item in users if email_query in item.email.lower()]
    return AdminUserSearchResponse(
        items=[_user_summary_response(item) for item in matches],
        total=len(matches),
        limit=bounded_limit,
    )


@router.get("/users/{user_id}/model-override", response_model=AIModelUserOverrideDetailResponse)
def get_ai_model_user_override(
    user_id: str,
    task_type: str = "default",
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelUserOverrideDetailResponse:
    _ = admin
    user = _require_admin_target_user(store=store, user_id=user_id)
    return _user_override_detail_response(store=store, user=user, task_type=task_type)


@router.put("/users/{user_id}/model-override", response_model=AIModelUserOverrideDetailResponse)
def upsert_ai_model_user_override(
    user_id: str,
    payload: AIModelUserOverrideRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelUserOverrideDetailResponse:
    user = _require_admin_target_user(store=store, user_id=user_id)
    existing = store.get_ai_model_user_override(user_id=user.user_id)
    try:
        override = store.upsert_ai_model_user_override(
            user_id=user.user_id,
            model_profile_id=payload.model_profile_id,
            admin_user_id=admin.user_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    action = "user_override.create" if existing is None else "user_override.update"
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action=action,
        entity_type="ai_model_user_override",
        entity_id=user.user_id,
        old=_override_audit_summary(existing),
        new=_override_audit_summary(override),
        reason=payload.reason,
    )
    return _user_override_detail_response(store=store, user=user, task_type="default")


@router.delete("/users/{user_id}/model-override", response_model=AIModelUserOverrideDetailResponse)
def disable_ai_model_user_override(
    user_id: str,
    payload: AIModelUserOverrideDeleteRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelUserOverrideDetailResponse:
    user = _require_admin_target_user(store=store, user_id=user_id)
    existing = store.get_ai_model_user_override(user_id=user.user_id)
    try:
        override = store.disable_ai_model_user_override(
            user_id=user.user_id,
            admin_user_id=admin.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User model override not found") from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="user_override.disable",
        entity_type="ai_model_user_override",
        entity_id=user.user_id,
        old=_override_audit_summary(existing),
        new=_override_audit_summary(override),
        reason=payload.reason,
    )
    return _user_override_detail_response(store=store, user=user, task_type="default")


@router.post("/providers", response_model=AIModelProviderResponse)
def upsert_ai_model_provider(
    payload: AIModelProviderUpsertRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelProviderResponse:
    existing = {item.provider_code: item for item in store.list_ai_model_providers(include_deleted=True)}.get(
        payload.provider_code.strip().lower()
    )
    try:
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
            model_parameters=payload.model_parameters,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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


@router.delete("/providers/{provider_id}", response_model=AIModelProviderResponse)
def soft_delete_ai_model_provider(
    provider_id: str,
    payload: AIModelProviderDeleteRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelProviderResponse:
    existing = {item.provider_id: item for item in store.list_ai_model_providers(include_deleted=True)}.get(provider_id)
    try:
        provider = store.soft_delete_ai_model_provider(
            provider_id=provider_id,
            admin_user_id=admin.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="provider.soft_delete",
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
            model_parameters=payload.model_parameters,
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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


@router.delete("/profiles/{model_profile_id}", response_model=AIModelProfileResponse)
def soft_delete_ai_model_profile(
    model_profile_id: str,
    payload: AIModelDeleteRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelProfileResponse:
    existing = {item.model_profile_id: item for item in store.list_ai_model_profiles(include_deleted=True)}.get(model_profile_id)
    try:
        profile = store.soft_delete_ai_model_profile(
            model_profile_id=model_profile_id,
            admin_user_id=admin.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model profile not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="profile.soft_delete",
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


@router.get("/ollama/models", response_model=OllamaModelInventoryResponse)
def list_ollama_models(
    _: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
    ollama: OllamaAdminService = Depends(get_ollama_admin_service),
) -> OllamaModelInventoryResponse:
    try:
        models = ollama.list_models()
        running_model_names = ollama.list_running_model_names()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ollama service is unavailable") from exc
    profiles = store.list_ai_model_profiles()
    providers = store.list_ai_model_providers()
    policies = store.list_ai_task_route_policies()
    installed_model_names = {_ollama_model_name_key(item.name) for item in models}
    return OllamaModelInventoryResponse(
        base_url=ollama.base_url,
        models=[
            _ollama_inventory_item_response(
                model=item,
                running_model_names=running_model_names,
                profiles=profiles,
                providers=providers,
                policies=policies,
                installed=True,
            )
            for item in models
        ]
        + [
            _configured_ollama_inventory_item_response(
                model_name=model_name,
                profiles=profiles,
                providers=providers,
                policies=policies,
            )
            for model_name in _configured_ollama_profile_model_names(
                profiles=profiles,
                providers=providers,
                exclude_model_names=installed_model_names,
            )
        ],
    )


@router.post("/ollama/import", response_model=OllamaModelJobResponse)
def import_ollama_model(
    payload: OllamaModelImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
    ollama: OllamaAdminService = Depends(get_ollama_admin_service),
    jobs: OllamaModelJobRegistry = Depends(get_ollama_job_registry),
) -> OllamaModelJobResponse:
    try:
        model = validate_ollama_registry_model_name(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    job = jobs.start(action="pull", model=model)
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="ollama_pull_started",
        entity_type="ollama_model",
        entity_id=model,
        old=None,
        new={"job_id": job.job_id, "status": job.status},
        reason=payload.reason,
    )
    background_tasks.add_task(jobs.run, job_id=job.job_id, operation="pull", model=model, service=ollama)
    return _ollama_job_response(job)


@router.post("/ollama/models/{model_name:path}/default", response_model=AIModelProfileResponse)
def set_ollama_model_default(
    model_name: str,
    payload: OllamaModelDefaultRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
    ollama: OllamaAdminService = Depends(get_ollama_admin_service),
) -> AIModelProfileResponse:
    try:
        model = validate_ollama_registry_model_name(model_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        installed_models = ollama.list_models()
        installed_by_key = {_ollama_model_name_key(item.name): item.name for item in installed_models}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ollama service is unavailable") from exc
    canonical_model = installed_by_key.get(_ollama_model_name_key(model))
    if canonical_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ollama model is not installed")
    model = canonical_model

    providers = store.list_ai_model_providers()
    profiles = store.list_ai_model_profiles()
    policies = store.list_ai_task_route_policies()
    provider = _local_ollama_provider(providers)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Local Ollama provider is not configured")

    existing = _local_ollama_profile_for_model(model, profiles, providers)
    old_default_ids = {
        item.model_profile_id
        for item in profiles
        if _is_local_ollama_profile(item, providers) and item.is_default_for_free
    }
    profile = store.upsert_ai_model_profile(
        model_profile_id=existing.model_profile_id if existing else None,
        provider_id=existing.provider_id if existing else provider.provider_id,
        model_code=existing.model_code if existing else model,
        deployment_name=(existing.deployment_name if existing else model) or model,
        context_window_tokens=existing.context_window_tokens if existing else 0,
        input_price_per_1m=existing.input_price_per_1m if existing else 0,
        cached_input_price_per_1m=existing.cached_input_price_per_1m if existing else 0,
        output_price_per_1m=existing.output_price_per_1m if existing else 0,
        billing_currency=existing.billing_currency if existing else "EUR",
        effective_from=existing.effective_from if existing else None,
        effective_to=existing.effective_to if existing else None,
        eu_data_zone_capable=existing.eu_data_zone_capable if existing else True,
        is_default_for_free=True,
        enabled=True,
    )
    updated_policies = _move_default_local_policies(
        store=store,
        policies=policies,
        old_default_ids=old_default_ids,
        new_profile_id=profile.model_profile_id,
    )
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="ollama_default.set",
        entity_type="ollama_model",
        entity_id=model,
        old={
            "model_profile_id": existing.model_profile_id if existing else "",
            "default_profile_ids": sorted(old_default_ids),
        },
        new={
            "model_profile_id": profile.model_profile_id,
            "model_code": profile.model_code,
            "updated_policy_ids": [item.policy_id for item in updated_policies],
        },
        reason=payload.reason,
    )
    return _profile_response(profile)


@router.delete("/ollama/models/{model_name:path}", response_model=OllamaModelJobResponse)
def remove_ollama_model(
    model_name: str,
    payload: OllamaModelRemoveRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
    ollama: OllamaAdminService = Depends(get_ollama_admin_service),
    jobs: OllamaModelJobRegistry = Depends(get_ollama_job_registry),
) -> OllamaModelJobResponse:
    try:
        model = validate_ollama_registry_model_name(model_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        running_model_names = ollama.list_running_model_names()
        installed_models = ollama.list_models()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ollama service is unavailable") from exc
    installed_by_key = {_ollama_model_name_key(item.name): item.name for item in installed_models}
    canonical_model = installed_by_key.get(_ollama_model_name_key(model), model)
    is_installed = _ollama_model_name_key(model) in installed_by_key
    profiles = store.list_ai_model_profiles()
    providers = store.list_ai_model_providers()
    policies = store.list_ai_task_route_policies()
    blockers = _ollama_model_removal_blockers(
        model_name=canonical_model,
        profiles=profiles,
        providers=providers,
        policies=policies,
        running_model_names=running_model_names,
        installed=is_installed,
    )
    if blockers:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "Ollama model is in active use", "blockers": blockers})
    removed_profiles, updated_policies = _soft_delete_ollama_profiles_for_model(
        store=store,
        model_name=canonical_model,
        profiles=profiles,
        providers=providers,
        policies=policies,
        admin_user_id=admin.user_id,
        reason=payload.reason,
    )
    job = jobs.start(action="remove", model=canonical_model)
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="ollama_remove_started",
        entity_type="ollama_model",
        entity_id=canonical_model,
        old={"model": canonical_model, "removed_profile_ids": [item.model_profile_id for item in removed_profiles]},
        new={"job_id": job.job_id, "status": job.status, "updated_policy_ids": [item.policy_id for item in updated_policies]},
        reason=payload.reason,
    )
    if is_installed:
        background_tasks.add_task(jobs.run, job_id=job.job_id, operation="remove", model=canonical_model, service=ollama)
    else:
        jobs.complete(job_id=job.job_id, message="Configured Ollama model profile removed; model was not installed in Ollama.")
    return _ollama_job_response(job)


@router.get("/ollama/jobs/{job_id}", response_model=OllamaModelJobResponse)
def get_ollama_model_job(
    job_id: str,
    _: AdminContext = Depends(require_ai_model_admin),
    jobs: OllamaModelJobRegistry = Depends(get_ollama_job_registry),
) -> OllamaModelJobResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ollama model job not found")
    return _ollama_job_response(job)


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


@router.delete("/policies/{policy_id}", response_model=AITaskRoutePolicyResponse)
def soft_delete_ai_task_route_policy(
    policy_id: str,
    payload: AIModelDeleteRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AITaskRoutePolicyResponse:
    existing = {item.policy_id: item for item in store.list_ai_task_route_policies(include_deleted=True)}.get(policy_id)
    try:
        policy = store.soft_delete_ai_task_route_policy(
            policy_id=policy_id,
            admin_user_id=admin.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing policy not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="policy.soft_delete",
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


@router.delete("/groups/{model_group_id}", response_model=AIModelGroupResponse)
def soft_delete_ai_model_group(
    model_group_id: str,
    payload: AIModelDeleteRequest,
    request: Request,
    admin: AdminContext = Depends(require_ai_model_admin),
    store: ApiDatabaseStore = Depends(get_admin_store),
) -> AIModelGroupResponse:
    existing = {item.model_group_id: item for item in store.list_ai_model_groups(include_deleted=True)}.get(model_group_id)
    try:
        group = store.soft_delete_ai_model_group(
            model_group_id=model_group_id,
            admin_user_id=admin.user_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model group not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _record_audit(
        store=store,
        request=request,
        admin=admin,
        action="group.soft_delete",
        entity_type="ai_model_group",
        entity_id=model_group_id,
        old=existing,
        new=group,
        reason=payload.reason,
    )
    return _group_response(group)


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


def _require_admin_target_user(*, store: ApiDatabaseStore, user_id: str) -> User:
    user = store.find_user_by_id(user_id=user_id.strip())
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _user_override_detail_response(
    *,
    store: ApiDatabaseStore,
    user: User,
    task_type: str,
) -> AIModelUserOverrideDetailResponse:
    plan = store.get_effective_subscription_plan(user_id=user.user_id)
    route = store.resolve_ai_model_route(
        user_id=user.user_id,
        plan_code=plan.plan_code,
        task_type=task_type,
        external_acknowledged=True,
    )
    return AIModelUserOverrideDetailResponse(
        user=_user_summary_response(user),
        override=_override_response(store.get_ai_model_user_override(user_id=user.user_id)),
        effective_route=_route_response(route),
    )


def _route_response(route: AIModelRouteSelection) -> AIModelEffectiveRouteResponse:
    provider = route.provider
    profile = route.model_profile
    return AIModelEffectiveRouteResponse(
        route_type=route.route_type,
        task_type=route.task_type,
        plan_code=route.plan_code,
        provider_id=provider.provider_id if provider is not None else None,
        provider_code=provider.provider_code if provider is not None else None,
        provider_display_name=provider.display_name if provider is not None else None,
        model_profile_id=profile.model_profile_id if profile is not None else None,
        model_code=profile.model_code if profile is not None else None,
        deployment_name=profile.deployment_name if profile is not None else None,
        is_external=provider.is_external if provider is not None else False,
        is_local=provider.is_local if provider is not None else False,
        requires_external_ack=route.requires_external_ack,
        reason=route.reason,
    )


def _override_response(item: AIModelUserOverride | None) -> AIModelUserOverrideResponse | None:
    if item is None:
        return None
    return AIModelUserOverrideResponse(**asdict(item))


def _override_audit_summary(item: AIModelUserOverride | None) -> dict[str, Any]:
    if item is None:
        return {}
    return {
        "override_id": item.override_id,
        "target_user_id": item.user_id,
        "model_profile_id": item.model_profile_id,
        "enabled": item.enabled,
        "created_by_admin_user_id": item.created_by_admin_user_id,
        "updated_by_admin_user_id": item.updated_by_admin_user_id,
        "disabled_by_admin_user_id": item.disabled_by_admin_user_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "disabled_at": item.disabled_at,
    }


def _ollama_inventory_item_response(
    *,
    model: OllamaInstalledModel,
    running_model_names: set[str],
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
    policies: list[AITaskRoutePolicy],
    installed: bool,
) -> OllamaModelInventoryItemResponse:
    blockers = _ollama_model_removal_blockers(
        model_name=model.name,
        profiles=profiles,
        providers=providers,
        policies=policies,
        running_model_names=running_model_names,
        installed=installed,
    )
    configured_profile_ids = [
        item.model_profile_id
        for item in profiles
        if _is_local_ollama_profile(item, providers) and _profile_matches_ollama_model(item, model.name)
    ]
    active_policy_ids = [
        item.policy_id
        for item in policies
        if item.enabled and item.preferred_local_model_profile_id in configured_profile_ids
    ]
    is_default = installed and _is_ollama_model_default(model.name, profiles, providers)
    return OllamaModelInventoryItemResponse(
        name=model.name,
        model=model.model,
        modified_at=model.modified_at,
        size=model.size,
        digest=model.digest,
        details=model.details,
        installed=installed,
        configured_profile_ids=configured_profile_ids,
        active_policy_ids=active_policy_ids,
        is_default=is_default,
        is_running=model.name in running_model_names,
        removable=not blockers,
        removal_blockers=blockers,
    )


def _configured_ollama_inventory_item_response(
    *,
    model_name: str,
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
    policies: list[AITaskRoutePolicy],
) -> OllamaModelInventoryItemResponse:
    response = _ollama_inventory_item_response(
        model=OllamaInstalledModel(
            name=model_name,
            model=model_name,
            modified_at="",
            size=0,
            digest="",
            details={"configured_only": True},
        ),
        running_model_names=set(),
        profiles=profiles,
        providers=providers,
        policies=policies,
        installed=False,
    )
    blockers = set(response.removal_blockers)
    blockers.add("Model is configured in JurisDigta but is not installed in Ollama.")
    response.removal_blockers = sorted(blockers)
    response.removable = True
    response.is_default = False
    return response


def _configured_ollama_profile_model_names(
    *,
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
    exclude_model_names: set[str],
) -> list[str]:
    excluded_keys = {_ollama_model_name_key(name) for name in exclude_model_names}
    names = {
        name.strip()
        for profile in profiles
        if _is_local_ollama_profile(profile, providers)
        for name in _profile_ollama_model_names(profile)
    }
    return sorted(name for name in names if name and _ollama_model_name_key(name) not in excluded_keys)


def _local_ollama_provider(providers: list[AIModelProvider]) -> AIModelProvider | None:
    for provider in providers:
        provider_type = provider.provider_type.strip().lower()
        if provider.provider_code == "local_ollama" or provider.is_local or provider_type in {"ollama", "local_ollama"}:
            return provider
    return None


def _local_ollama_profile_for_model(
    model_name: str,
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
) -> AIModelProfile | None:
    return next(
        (
            item
            for item in profiles
            if _is_local_ollama_profile(item, providers) and _profile_matches_ollama_model(item, model_name)
        ),
        None,
    )


def _current_default_local_ollama_profile(
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
) -> AIModelProfile | None:
    return next(
        (
            item
            for item in profiles
            if item.enabled and item.is_default_for_free and _is_local_ollama_profile(item, providers)
        ),
        None,
    )


def _is_ollama_model_default(
    model_name: str,
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
) -> bool:
    return any(
        item.enabled
        and item.is_default_for_free
        and _is_local_ollama_profile(item, providers)
        and _profile_matches_ollama_model(item, model_name)
        for item in profiles
    )


def _move_default_local_policies(
    *,
    store: ApiDatabaseStore,
    policies: list[AITaskRoutePolicy],
    old_default_ids: set[str],
    new_profile_id: str,
) -> list[AITaskRoutePolicy]:
    candidate_old_ids = set(old_default_ids)
    candidate_old_ids.add(_LOCAL_DEFAULT_PROFILE_ID)
    updated: list[AITaskRoutePolicy] = []
    for policy in policies:
        should_follow_default = (
            policy.enabled
            and policy.preferred_local_model_profile_id != new_profile_id
            and (
                policy.preferred_local_model_profile_id in candidate_old_ids
                or policy.plan_code in {"", "free"}
            )
        )
        if not should_follow_default:
            continue
        updated.append(_upsert_policy_local_profile(store=store, policy=policy, new_profile_id=new_profile_id))
    return updated


def _move_policies_from_profiles(
    *,
    store: ApiDatabaseStore,
    policies: list[AITaskRoutePolicy],
    old_profile_ids: set[str],
    new_profile_id: str | None,
    clear_when_missing: bool = False,
) -> list[AITaskRoutePolicy]:
    if not old_profile_ids or (not new_profile_id and not clear_when_missing):
        return []
    updated: list[AITaskRoutePolicy] = []
    for policy in policies:
        if policy.enabled and policy.preferred_local_model_profile_id in old_profile_ids:
            updated.append(_upsert_policy_local_profile(store=store, policy=policy, new_profile_id=new_profile_id))
    return updated


def _upsert_policy_local_profile(
    *,
    store: ApiDatabaseStore,
    policy: AITaskRoutePolicy,
    new_profile_id: str | None,
) -> AITaskRoutePolicy:
    return store.upsert_ai_task_route_policy(
        policy_id=policy.policy_id,
        task_type=policy.task_type,
        plan_code=policy.plan_code,
        model_group_id=policy.model_group_id,
        preferred_external_model_profile_id=policy.preferred_external_model_profile_id,
        preferred_local_model_profile_id=new_profile_id,
        allow_external=policy.allow_external,
        require_external_ack=policy.require_external_ack,
        require_eu_data_zone=policy.require_eu_data_zone,
        fallback_local_on_error=policy.fallback_local_on_error,
        fallback_local_on_budget=policy.fallback_local_on_budget,
        max_cost_eur=policy.max_cost_eur,
        priority=policy.priority,
        enabled=policy.enabled,
    )


def _disable_non_default_ollama_profiles_for_model(
    *,
    store: ApiDatabaseStore,
    model_name: str,
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
) -> list[AIModelProfile]:
    disabled: list[AIModelProfile] = []
    for profile in profiles:
        if (
            profile.enabled
            and not profile.is_default_for_free
            and _is_local_ollama_profile(profile, providers)
            and _profile_matches_ollama_model(profile, model_name)
        ):
            disabled.append(
                store.upsert_ai_model_profile(
                    model_profile_id=profile.model_profile_id,
                    provider_id=profile.provider_id,
                    model_code=profile.model_code,
                    deployment_name=profile.deployment_name,
                    context_window_tokens=profile.context_window_tokens,
                    input_price_per_1m=profile.input_price_per_1m,
                    cached_input_price_per_1m=profile.cached_input_price_per_1m,
                    output_price_per_1m=profile.output_price_per_1m,
                    billing_currency=profile.billing_currency,
                    effective_from=profile.effective_from,
                    effective_to=profile.effective_to,
                    eu_data_zone_capable=profile.eu_data_zone_capable,
                    is_default_for_free=False,
                    enabled=False,
                )
            )
    return disabled


def _soft_delete_ollama_profiles_for_model(
    *,
    store: ApiDatabaseStore,
    model_name: str,
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
    policies: list[AITaskRoutePolicy],
    admin_user_id: str,
    reason: str,
) -> tuple[list[AIModelProfile], list[AITaskRoutePolicy]]:
    matching_profiles = [
        profile
        for profile in profiles
        if _is_local_ollama_profile(profile, providers) and _profile_matches_ollama_model(profile, model_name)
    ]
    old_profile_ids = {profile.model_profile_id for profile in matching_profiles}
    if not matching_profiles:
        return [], []
    removed: list[AIModelProfile] = []
    for profile in matching_profiles:
        if profile.is_default_for_free or profile.enabled:
            store.upsert_ai_model_profile(
                model_profile_id=profile.model_profile_id,
                provider_id=profile.provider_id,
                model_code=profile.model_code,
                deployment_name=profile.deployment_name,
                context_window_tokens=profile.context_window_tokens,
                input_price_per_1m=profile.input_price_per_1m,
                cached_input_price_per_1m=profile.cached_input_price_per_1m,
                output_price_per_1m=profile.output_price_per_1m,
                billing_currency=profile.billing_currency,
                effective_from=profile.effective_from,
                effective_to=profile.effective_to,
                eu_data_zone_capable=profile.eu_data_zone_capable,
                is_default_for_free=False,
                enabled=False,
            )
    current_default = _current_default_local_ollama_profile(
        [profile for profile in store.list_ai_model_profiles() if profile.model_profile_id not in old_profile_ids],
        providers,
    )
    updated_policies = _move_policies_from_profiles(
        store=store,
        policies=policies,
        old_profile_ids=old_profile_ids,
        new_profile_id=current_default.model_profile_id if current_default else None,
        clear_when_missing=True,
    )
    for profile in matching_profiles:
        try:
            removed.append(
                store.soft_delete_ai_model_profile(
                    model_profile_id=profile.model_profile_id,
                    admin_user_id=admin_user_id,
                    reason=reason,
                )
            )
        except ValueError:
            continue
    return removed, updated_policies


def _ollama_model_removal_blockers(
    *,
    model_name: str,
    profiles: list[AIModelProfile],
    providers: list[AIModelProvider],
    policies: list[AITaskRoutePolicy],
    running_model_names: set[str],
    installed: bool = True,
) -> list[str]:
    if not installed:
        return []
    blockers: list[str] = []
    matching_profiles = [
        item
        for item in profiles
        if _is_local_ollama_profile(item, providers) and _profile_matches_ollama_model(item, model_name)
    ]
    enabled_matching_profiles = [item for item in matching_profiles if item.enabled]
    for profile in enabled_matching_profiles:
        if profile.is_default_for_free:
            blockers.append(f"Profile {profile.model_profile_id} is marked as the free/default local model.")

    env_default = os.getenv("LOCAL_LLM_MODEL", "").strip()
    if env_default and env_default.lower() != "unknown-variable" and _ollama_model_name_key(env_default) == _ollama_model_name_key(model_name) and blockers:
        blockers.append("LOCAL_LLM_MODEL currently selects this model.")

    if _ollama_model_name_key(model_name) in {_ollama_model_name_key(item) for item in running_model_names} and blockers:
        blockers.append("Ollama reports this configured model as currently loaded.")

    return sorted(set(blockers))


def _is_local_ollama_profile(profile: AIModelProfile, providers: list[AIModelProvider]) -> bool:
    provider = {item.provider_id: item for item in providers}.get(profile.provider_id)
    if provider is None:
        return False
    provider_type = provider.provider_type.strip().lower()
    return provider.is_local or provider_type in {"ollama", "local_ollama"}


def _profile_matches_ollama_model(profile: AIModelProfile, model_name: str) -> bool:
    model_key = _ollama_model_name_key(model_name)
    return any(_ollama_model_name_key(name) == model_key for name in _profile_ollama_model_names(profile))


def _profile_ollama_model_names(profile: AIModelProfile) -> set[str]:
    return {profile.model_code.strip(), profile.deployment_name.strip()} - {""}


def _ollama_model_name_key(model_name: str) -> str:
    return model_name.strip().lower()


def _ollama_job_response(job: OllamaModelJob) -> OllamaModelJobResponse:
    return OllamaModelJobResponse(
        job_id=job.job_id,
        action=job.action,
        model=job.model,
        status=job.status,
        message=job.message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    data = asdict(value) if hasattr(value, "__dataclass_fields__") else dict(value)
    summary = {
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
    if "model_parameters" in summary:
        parameters = summary["model_parameters"]
        summary["model_parameter_names"] = sorted(parameters) if isinstance(parameters, dict) else []
        del summary["model_parameters"]
    return summary


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
