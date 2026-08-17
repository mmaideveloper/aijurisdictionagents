from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.case_types.models import (
    CaseTypeCreateRequest,
    CaseTypeListResponse,
    CaseTypeResolveResponse,
    CaseTypeResponse,
    CaseTypeUpdateRequest,
)
from app.document_templates.store import (
    CaseTypeConflictError,
    CaseTypeNotFoundError,
    DocumentTemplateNotFoundError,
    DocumentTemplateStore,
    get_document_template_store,
)
from app.security import require_api_key


router = APIRouter(
    prefix="/v1/case-types",
    tags=["case-types"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=CaseTypeListResponse)
def list_case_types(
    include_deleted: bool = Query(default=False),
    jurisdiction: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> CaseTypeListResponse:
    items = store.list_case_types(include_deleted=include_deleted, jurisdiction=jurisdiction)
    return CaseTypeListResponse(items=[CaseTypeResponse.from_definition(item) for item in items])


@router.get("/resolve/search", response_model=CaseTypeResolveResponse)
def resolve_case_type(
    request_text: str = Query(min_length=3),
    country: str = Query(min_length=2, max_length=8),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> CaseTypeResolveResponse:
    score, matched = store.resolve_case_type(request_text=request_text, country=country)
    return CaseTypeResolveResponse(
        matched=matched is not None,
        score=score,
        case_type=CaseTypeResponse.from_definition(matched) if matched is not None else None,
    )


@router.get("/{case_type_key}", response_model=CaseTypeResponse)
def get_case_type(
    case_type_key: str,
    jurisdiction: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> CaseTypeResponse:
    try:
        return CaseTypeResponse.from_definition(
            store.get_case_type(case_type_key=case_type_key, jurisdiction=jurisdiction)
        )
    except CaseTypeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CaseTypeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", response_model=CaseTypeResponse, status_code=status.HTTP_201_CREATED)
def create_case_type(
    payload: CaseTypeCreateRequest,
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> CaseTypeResponse:
    try:
        return CaseTypeResponse.from_definition(store.create_case_type(payload))
    except CaseTypeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{case_type_key}", response_model=CaseTypeResponse)
def update_case_type(
    case_type_key: str,
    payload: CaseTypeUpdateRequest,
    jurisdiction: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> CaseTypeResponse:
    try:
        return CaseTypeResponse.from_definition(
            store.update_case_type(
                case_type_key=case_type_key,
                payload=payload,
                jurisdiction=jurisdiction,
            )
        )
    except CaseTypeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CaseTypeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{case_type_key}", response_model=CaseTypeResponse)
def delete_case_type(
    case_type_key: str,
    jurisdiction: str | None = Query(default=None),
    store: DocumentTemplateStore = Depends(get_document_template_store),
) -> CaseTypeResponse:
    try:
        return CaseTypeResponse.from_definition(
            store.soft_delete_case_type(case_type_key=case_type_key, jurisdiction=jurisdiction)
        )
    except CaseTypeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CaseTypeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
