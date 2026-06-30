from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.provider_credentials.models import (
    ProviderCredentialCreateRequest,
    ProviderCredentialListResponse,
    ProviderCredentialResponse,
    ProviderCredentialUpdateRequest,
)
from app.provider_credentials.store import (
    ProviderCredentialConflictError,
    ProviderCredentialNotFoundError,
    ProviderCredentialStore,
)
from app.security import require_api_key


router = APIRouter(
    prefix="/v1/provider-credentials",
    tags=["provider-credentials"],
    dependencies=[Depends(require_api_key)],
)


@lru_cache(maxsize=1)
def get_provider_credential_store() -> ProviderCredentialStore:
    return ProviderCredentialStore.from_env()


@router.get("", response_model=ProviderCredentialListResponse)
def list_provider_credentials(
    include_deleted: bool = Query(default=False),
    store: ProviderCredentialStore = Depends(get_provider_credential_store),
) -> ProviderCredentialListResponse:
    return ProviderCredentialListResponse(items=store.list(include_deleted=include_deleted))


@router.get("/{provider_key}", response_model=ProviderCredentialResponse)
def get_provider_credential(
    provider_key: str,
    include_deleted: bool = Query(default=False),
    store: ProviderCredentialStore = Depends(get_provider_credential_store),
) -> ProviderCredentialResponse:
    try:
        return store.get(provider_key=provider_key, include_deleted=include_deleted)
    except ProviderCredentialNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=ProviderCredentialResponse, status_code=status.HTTP_201_CREATED)
def create_provider_credential(
    payload: ProviderCredentialCreateRequest,
    store: ProviderCredentialStore = Depends(get_provider_credential_store),
) -> ProviderCredentialResponse:
    try:
        return store.create(payload)
    except ProviderCredentialConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{provider_key}", response_model=ProviderCredentialResponse)
def update_provider_credential(
    provider_key: str,
    payload: ProviderCredentialUpdateRequest,
    store: ProviderCredentialStore = Depends(get_provider_credential_store),
) -> ProviderCredentialResponse:
    try:
        return store.update(provider_key=provider_key, payload=payload)
    except ProviderCredentialNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{provider_key}", response_model=ProviderCredentialResponse)
def delete_provider_credential(
    provider_key: str,
    store: ProviderCredentialStore = Depends(get_provider_credential_store),
) -> ProviderCredentialResponse:
    try:
        return store.soft_delete(provider_key=provider_key)
    except ProviderCredentialNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
