from __future__ import annotations

from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.security import require_api_key

from aijurisdictionagents.api_db import (
    ApiDatabaseStore,
    Case,
    CaseCommunication,
    CaseDocument,
)

router = APIRouter(prefix='/v1/cases', tags=['cases'], dependencies=[Depends(require_api_key)])
_MAX_ACTIVE_CASES = 5


class CaseResponse(BaseModel):
    case_id: str
    user_id: str
    company_id: str | None = None
    title: str
    status: str
    created_at: str
    updated_at: str


class CreateCaseRequest(BaseModel):
    user_id: str = Field(min_length=1)
    title: str = Field(min_length=1)


class UpdateCaseRequest(BaseModel):
    user_id: str = Field(min_length=1)
    title: str = Field(min_length=1)


class CaseHistoryMessageResponse(BaseModel):
    communication_id: str
    role: str
    content: str
    agent_name: str | None = None
    created_at: str


class CaseDocumentResponse(BaseModel):
    doc_id: str
    kind: str
    version: int
    original_filename: str
    processing_status: str
    processing_error: str | None = None
    processed_at: str | None = None
    created_at: str


class CaseHistoryResponse(BaseModel):
    messages: list[CaseHistoryMessageResponse]
    has_more: bool
    documents: list[CaseDocumentResponse]


class CaseDocumentUploadResponse(BaseModel):
    uploaded: list[CaseDocumentResponse]
    document_limit: int
    processed_document_count: int
    unprocessed_document_count: int


class CaseDocumentContextResponse(BaseModel):
    processed_documents: list[str]
    unprocessed_documents: list[str]


def get_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


@router.get('', response_model=list[CaseResponse])
def list_cases(user_id: str, store: ApiDatabaseStore = Depends(get_store)) -> list[CaseResponse]:
    return [_to_case_response(item) for item in store.list_cases(user_id=user_id)]


@router.post('', response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(payload: CreateCaseRequest, store: ApiDatabaseStore = Depends(get_store)) -> CaseResponse:
    active = store.count_active_cases(user_id=payload.user_id)
    if active >= _MAX_ACTIVE_CASES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Maximum number of cases reached ({_MAX_ACTIVE_CASES})',
        )
    case = store.create_case(user_id=payload.user_id, company_id=None, title=payload.title.strip())
    return _to_case_response(case)


@router.patch('/{case_id}', response_model=CaseResponse)
def rename_case(case_id: str, payload: UpdateCaseRequest, store: ApiDatabaseStore = Depends(get_store)) -> CaseResponse:
    try:
        case = store.update_case_title(case_id=case_id, user_id=payload.user_id, title=payload.title.strip())
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_case_response(case)


@router.delete('/{case_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: str, user_id: str, store: ApiDatabaseStore = Depends(get_store)) -> None:
    try:
        store.soft_delete_case(case_id=case_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get('/{case_id}/history', response_model=CaseHistoryResponse)
def get_case_history(
    case_id: str,
    user_id: str,
    offset: int = 0,
    limit: int = 5,
    store: ApiDatabaseStore = Depends(get_store),
) -> CaseHistoryResponse:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    bounded_limit = min(max(limit, 1), 20)
    bounded_offset = max(offset, 0)
    communications = store.list_case_communications(
        case_id=case_id,
        limit=bounded_limit + 1,
        offset=bounded_offset,
    )
    has_more = len(communications) > bounded_limit
    visible = communications[:bounded_limit]
    messages = [
        _to_case_history_message_response(store=store, communication=item)
        for item in reversed(visible)
    ]
    documents = [
        _to_case_document_response(item)
        for item in store.list_case_documents(case_id=case_id)
    ]
    return CaseHistoryResponse(messages=messages, has_more=has_more, documents=documents)


@router.post('/{case_id}/documents', response_model=CaseDocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_case_documents(
    case_id: str,
    user_id: str = Query(..., min_length=1),
    files: list[UploadFile] = File(...),
    store: ApiDatabaseStore = Depends(get_store),
) -> CaseDocumentUploadResponse:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    limit = store.get_document_upload_limit(user_id=user_id)
    existing = store.count_case_documents(case_id=case_id)
    if existing + len(files) > limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Document limit reached for this case ({limit}).',
        )
    uploaded: list[CaseDocumentResponse] = []
    next_version = existing + 1
    for file in files:
        filename = Path(file.filename or 'document').name or 'document'
        payload = await file.read()
        doc_id = store.add_case_document(
            case_id=case_id,
            kind='uploaded',
            version=next_version,
            original_filename=filename,
            payload=payload,
            uploaded_by_user_id=user_id,
        )
        uploaded.append(_to_case_document_response(store.get_case_document(case_id=case_id, doc_id=doc_id)))
        next_version += 1
    context = _document_context(case_id=case_id, store=store)
    return CaseDocumentUploadResponse(
        uploaded=uploaded,
        document_limit=limit,
        processed_document_count=len(context.processed_documents),
        unprocessed_document_count=len(context.unprocessed_documents),
    )


@router.get('/{case_id}/documents/context', response_model=CaseDocumentContextResponse)
def get_case_document_context(
    case_id: str,
    user_id: str,
    store: ApiDatabaseStore = Depends(get_store),
) -> CaseDocumentContextResponse:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    return _document_context(case_id=case_id, store=store)


@router.get('/{case_id}/documents/{doc_id}')
def download_case_document(
    case_id: str,
    doc_id: str,
    user_id: str,
    store: ApiDatabaseStore = Depends(get_store),
) -> Response:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    try:
        document = store.get_case_document(case_id=case_id, doc_id=doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    payload = store.read_storage_bytes(storage_uri=document.storage_uri)
    media_type = guess_type(document.original_filename)[0] or 'application/octet-stream'
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            'Content-Disposition': f'attachment; filename="{document.original_filename}"',
        },
    )


def _to_case_response(case: Case) -> CaseResponse:
    return CaseResponse(
        case_id=case.case_id,
        user_id=case.user_id,
        company_id=case.company_id,
        title=case.title,
        status=case.status,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _ensure_case_access(*, case_id: str, user_id: str, store: ApiDatabaseStore) -> Case:
    try:
        case = store.get_case(case_id=case_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if case.user_id != user_id or case.status == 'deleted':
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'Case {case_id} not found')
    return case


def _to_case_history_message_response(
    *, store: ApiDatabaseStore, communication: CaseCommunication
) -> CaseHistoryMessageResponse:
    content = communication.summary
    if communication.transcript_uri:
        content = store.read_storage_text(storage_uri=communication.transcript_uri)
    role = 'assistant'
    agent_name: str | None = None
    normalized = content.strip()
    upper = normalized.upper()
    if upper.startswith('USER:'):
        role = 'user'
        normalized = normalized[5:].strip()
    elif upper.startswith('ASSISTANT:'):
        role = 'assistant'
        normalized = normalized[10:].strip()
    elif upper.startswith('SYSTEM:'):
        role = 'system'
        normalized = normalized[7:].strip()
    if normalized.endswith(')') and '(agent=' in normalized:
        prefix, _, suffix = normalized.rpartition('(agent=')
        agent_name = suffix[:-1].strip() or None
        normalized = prefix.strip()
    return CaseHistoryMessageResponse(
        communication_id=communication.communication_id,
        role=role,
        content=normalized,
        agent_name=agent_name,
        created_at=communication.created_at,
    )


def _to_case_document_response(document: CaseDocument) -> CaseDocumentResponse:
    return CaseDocumentResponse(
        doc_id=document.doc_id,
        kind=document.kind,
        version=document.version,
        original_filename=document.original_filename,
        processing_status=document.processing_status,
        processing_error=document.processing_error,
        processed_at=document.processed_at,
        created_at=document.created_at,
    )


def _document_context(*, case_id: str, store: ApiDatabaseStore) -> CaseDocumentContextResponse:
    processed: list[str] = []
    unprocessed: list[str] = []
    for document in store.list_case_documents(case_id=case_id):
        if document.kind != 'uploaded':
            continue
        if document.processing_status == 'processed':
            processed.append(document.original_filename)
        else:
            unprocessed.append(document.original_filename)
    return CaseDocumentContextResponse(
        processed_documents=processed,
        unprocessed_documents=unprocessed,
    )
