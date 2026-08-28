from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.ai_model_admin_api import AdminContext, require_ai_model_admin
from app.flow_packs.models import (
    FlowPackCreateRequest,
    FlowPackCreateVersionRequest,
    FlowPackListResponse,
    FlowPackResponse,
    FlowPackUpdateRequest,
    FlowPackVersionListResponse,
)
from app.flow_packs.store import (
    FlowPackAmbiguousError,
    FlowPackNotFoundError,
    FlowPackImmutableError,
    FlowPackStore,
    FlowPackVersionConflictError,
)
from app.security import require_api_key

router = APIRouter(prefix="/v1/flow-packs", tags=["flow-packs"], dependencies=[Depends(require_api_key)])


@lru_cache(maxsize=1)
def get_flow_pack_store() -> FlowPackStore:
    return FlowPackStore.from_env()


@router.get("", response_model=FlowPackListResponse)
def list_flow_packs(
    include_deleted: bool = Query(default=False),
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackListResponse:
    return FlowPackListResponse(items=store.list(include_deleted=include_deleted, jurisdiction=jurisdiction))


@router.get("/{flow_key}/versions", response_model=FlowPackVersionListResponse)
def list_flow_pack_versions(
    flow_key: str,
    include_deleted: bool = Query(default=True),
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackVersionListResponse:
    return FlowPackVersionListResponse(
        flow_key=flow_key,
        versions=store.list_versions(flow_key=flow_key, jurisdiction=jurisdiction, include_deleted=include_deleted),
    )


@router.get("/{flow_key}/versions/{version}", response_model=FlowPackResponse)
def get_flow_pack_version(
    flow_key: str,
    version: int,
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackResponse:
    try:
        return store.get(flow_key=flow_key, version=version, jurisdiction=jurisdiction)
    except FlowPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FlowPackAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", response_model=FlowPackResponse, status_code=status.HTTP_201_CREATED)
def create_flow_pack(
    payload: FlowPackCreateRequest,
    _: AdminContext = Depends(require_ai_model_admin),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackResponse:
    try:
        return store.create(payload)
    except FlowPackVersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{flow_key}/versions", response_model=FlowPackResponse, status_code=status.HTTP_201_CREATED)
def create_flow_pack_version(
    flow_key: str,
    payload: FlowPackCreateVersionRequest,
    _: AdminContext = Depends(require_ai_model_admin),
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackResponse:
    try:
        return store.create_version(flow_key=flow_key, payload=payload, jurisdiction=jurisdiction)
    except FlowPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FlowPackVersionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except FlowPackAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/{flow_key}/versions/{version}", response_model=FlowPackResponse)
def update_flow_pack_version(
    flow_key: str,
    version: int,
    payload: FlowPackUpdateRequest,
    _: AdminContext = Depends(require_ai_model_admin),
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackResponse:
    try:
        return store.update(flow_key=flow_key, version=version, payload=payload, jurisdiction=jurisdiction)
    except FlowPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FlowPackAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FlowPackImmutableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{flow_key}/versions/{version}/enable", response_model=FlowPackResponse)
def enable_flow_pack_version(
    flow_key: str,
    version: int,
    _: AdminContext = Depends(require_ai_model_admin),
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackResponse:
    try:
        return store.set_enabled(flow_key=flow_key, version=version, enabled=True, jurisdiction=jurisdiction)
    except FlowPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FlowPackAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FlowPackImmutableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{flow_key}/versions/{version}/disable", response_model=FlowPackResponse)
def disable_flow_pack_version(
    flow_key: str,
    version: int,
    _: AdminContext = Depends(require_ai_model_admin),
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackResponse:
    try:
        return store.set_enabled(flow_key=flow_key, version=version, enabled=False, jurisdiction=jurisdiction)
    except FlowPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FlowPackAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{flow_key}/versions/{version}", response_model=FlowPackResponse)
def soft_delete_flow_pack_version(
    flow_key: str,
    version: int,
    _: AdminContext = Depends(require_ai_model_admin),
    jurisdiction: str | None = Query(default=None),
    store: FlowPackStore = Depends(get_flow_pack_store),
) -> FlowPackResponse:
    try:
        return store.soft_delete(flow_key=flow_key, version=version, jurisdiction=jurisdiction)
    except FlowPackNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FlowPackAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
