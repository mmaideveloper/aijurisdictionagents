from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.security import require_admin_api_key
from aijurisdictionagents.api_db import (
    AIModelCredential,
    AIModelProfile,
    AIModelProvider,
    ApiDatabaseStore,
)


router = APIRouter(
    prefix="/v1/admin/ai-models",
    tags=["admin-ai-models"],
    dependencies=[Depends(require_admin_api_key)],
)


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
    effective_from: str | None = None
    effective_to: str | None = None
    eu_data_zone_capable: bool
    is_default_for_free: bool
    enabled: bool


class AIModelCredentialResponse(BaseModel):
    credential_id: str
    provider_id: str
    credential_name: str
    secret_type: str
    secret_preview: str
    secret_value: str | None = None
    enabled: bool
    created_at: str
    updated_at: str
    last_revealed_at: str | None = None


class UpsertCredentialRequest(BaseModel):
    secret_value: str = Field(min_length=1)
    credential_name: str = "default"
    secret_type: str = "api_key"
    enabled: bool = True


class UpsertProviderRequest(BaseModel):
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


class UpsertProfileRequest(BaseModel):
    provider_id: str = Field(min_length=1)
    model_code: str = Field(min_length=1)
    deployment_name: str = ""
    model_parameters: dict[str, bool | int | float | str | None] = Field(default_factory=dict)
    context_window_tokens: int = 0
    input_price_per_1m: float = 0.0
    cached_input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0
    billing_currency: str = "USD"
    effective_from: str | None = None
    effective_to: str | None = None
    eu_data_zone_capable: bool = False
    is_default_for_free: bool = False
    enabled: bool = True


class CredentialEnabledRequest(BaseModel):
    enabled: bool


def get_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


@router.get("/providers", response_model=list[AIModelProviderResponse])
def list_model_providers(
    store: ApiDatabaseStore = Depends(get_store),
) -> list[AIModelProviderResponse]:
    return [_provider_response(provider) for provider in store.list_ai_model_providers()]


@router.get("/profiles", response_model=list[AIModelProfileResponse])
def list_model_profiles(
    provider_id: str | None = None,
    store: ApiDatabaseStore = Depends(get_store),
) -> list[AIModelProfileResponse]:
    return [
        _profile_response(profile)
        for profile in store.list_ai_model_profiles(provider_id=provider_id)
    ]


@router.put(
    "/providers/{provider_id}",
    response_model=AIModelProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
def upsert_model_provider(
    provider_id: str,
    payload: UpsertProviderRequest,
    store: ApiDatabaseStore = Depends(get_store),
) -> AIModelProviderResponse:
    try:
        provider = store.upsert_ai_model_provider(
            provider_id=provider_id,
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
    return _provider_response(provider)


@router.put(
    "/profiles/{model_profile_id}",
    response_model=AIModelProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def upsert_model_profile(
    model_profile_id: str,
    payload: UpsertProfileRequest,
    store: ApiDatabaseStore = Depends(get_store),
) -> AIModelProfileResponse:
    try:
        profile = store.upsert_ai_model_profile(
            model_profile_id=model_profile_id,
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _profile_response(profile)


@router.get("/credentials", response_model=list[AIModelCredentialResponse])
def list_model_credentials(
    provider_id: str | None = None,
    reveal: bool = False,
    store: ApiDatabaseStore = Depends(get_store),
) -> list[AIModelCredentialResponse]:
    return [
        _credential_response(credential, reveal=reveal)
        for credential in store.list_ai_model_credentials(
            provider_id=provider_id,
            reveal=reveal,
        )
    ]


@router.put(
    "/providers/{provider_id}/credentials",
    response_model=AIModelCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def upsert_model_credential(
    provider_id: str,
    payload: UpsertCredentialRequest,
    store: ApiDatabaseStore = Depends(get_store),
) -> AIModelCredentialResponse:
    credential = store.upsert_ai_model_credential(
        provider_id=provider_id,
        secret_value=payload.secret_value,
        credential_name=payload.credential_name,
        secret_type=payload.secret_type,
        enabled=payload.enabled,
    )
    return _credential_response(credential, reveal=False)


@router.patch(
    "/credentials/{credential_id}",
    response_model=AIModelCredentialResponse,
)
def set_model_credential_enabled(
    credential_id: str,
    payload: CredentialEnabledRequest,
    store: ApiDatabaseStore = Depends(get_store),
) -> AIModelCredentialResponse:
    credential = store.set_ai_model_credential_enabled(
        credential_id=credential_id,
        enabled=payload.enabled,
    )
    return _credential_response(credential, reveal=False)


def _provider_response(provider: AIModelProvider) -> AIModelProviderResponse:
    return AIModelProviderResponse(
        provider_id=provider.provider_id,
        provider_code=provider.provider_code,
        provider_type=provider.provider_type,
        display_name=provider.display_name,
        base_url=provider.base_url,
        api_version=provider.api_version,
        region=provider.region,
        data_zone=provider.data_zone,
        is_external=provider.is_external,
        is_local=provider.is_local,
        health_check_url=provider.health_check_url,
        model_parameters=provider.model_parameters,
        enabled=provider.enabled,
    )


def _profile_response(profile: AIModelProfile) -> AIModelProfileResponse:
    return AIModelProfileResponse(
        model_profile_id=profile.model_profile_id,
        provider_id=profile.provider_id,
        model_code=profile.model_code,
        deployment_name=profile.deployment_name,
        model_parameters=profile.model_parameters,
        context_window_tokens=profile.context_window_tokens,
        input_price_per_1m=profile.input_price_per_1m,
        cached_input_price_per_1m=profile.cached_input_price_per_1m,
        output_price_per_1m=profile.output_price_per_1m,
        billing_currency=profile.billing_currency,
        effective_from=profile.effective_from,
        effective_to=profile.effective_to,
        eu_data_zone_capable=profile.eu_data_zone_capable,
        is_default_for_free=profile.is_default_for_free,
        enabled=profile.enabled,
    )


def _credential_response(
    credential: AIModelCredential,
    *,
    reveal: bool,
) -> AIModelCredentialResponse:
    return AIModelCredentialResponse(
        credential_id=credential.credential_id,
        provider_id=credential.provider_id,
        credential_name=credential.credential_name,
        secret_type=credential.secret_type,
        secret_preview=credential.secret_preview,
        secret_value=credential.secret_value if reveal else None,
        enabled=credential.enabled,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
        last_revealed_at=credential.last_revealed_at,
    )
