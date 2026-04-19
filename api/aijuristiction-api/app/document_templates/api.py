from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.document_templates.models import (
    DocumentTemplateCreateRequest,
    DocumentTemplateListResponse,
    DocumentTemplateMatchResponse,
    DocumentTemplateResponse,
    DocumentTemplateUpdateRequest,
)
from app.document_templates.store import (
    DocumentTemplateAmbiguousError,
    DocumentTemplateConflictError,
    DocumentTemplateNotFoundError,
    DocumentTemplateStore,
)
from app.security import require_api_key


router = APIRouter(
    prefix="/v1/document-templates",
    tags=["document-templates"],
    dependencies=[Depends(require_api_key)],
)


@lru_cache(maxsize=1)
def get_document_template_store() -> DocumentTemplateStore:
    return DocumentTemplateStore.from_env()


@router.get("", response_model=DocumentTemplateListResponse)
def list_document_templates(
    include_deleted: bool = Query(default=False),
    jurisdiction: str | None = Query(default=None),
    category: str | None = Query(default=None),
    template_kind: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateListResponse:
    items = store.list(
        include_deleted=include_deleted,
        jurisdiction=jurisdiction,
        category=category,
        template_kind=template_kind,
    )
    return DocumentTemplateListResponse(items=[DocumentTemplateResponse.from_definition(item) for item in items])


@router.get("/{template_key}", response_model=DocumentTemplateResponse)
def get_document_template(
    template_key: str,
    jurisdiction: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(
            store.get(template_key=template_key, jurisdiction=jurisdiction)
        )
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentTemplateAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", response_model=DocumentTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_document_template(
    payload: DocumentTemplateCreateRequest,
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(store.create(payload))
    except DocumentTemplateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{template_key}", response_model=DocumentTemplateResponse)
def update_document_template(
    template_key: str,
    payload: DocumentTemplateUpdateRequest,
    jurisdiction: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(
            store.update(template_key=template_key, payload=payload, jurisdiction=jurisdiction)
        )
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentTemplateAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{template_key}", response_model=DocumentTemplateResponse)
def delete_document_template(
    template_key: str,
    jurisdiction: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateResponse:
    try:
        return DocumentTemplateResponse.from_definition(
            store.soft_delete(template_key=template_key, jurisdiction=jurisdiction)
        )
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentTemplateAmbiguousError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/match/search", response_model=DocumentTemplateMatchResponse)
def match_document_template(
    request_text: str = Query(min_length=3),
    country: str = Query(min_length=2, max_length=8),
    template_kind: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> DocumentTemplateMatchResponse:
    score, matched = store.find_best_match(
        request_text=request_text,
        country=country,
        template_kind=template_kind,
    )
    return DocumentTemplateMatchResponse(
        matched=matched is not None,
        score=score,
        template=DocumentTemplateResponse.from_definition(matched) if matched is not None else None,
    )

