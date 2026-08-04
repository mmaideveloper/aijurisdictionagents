from __future__ import annotations

import logging
import os
import base64
import hashlib
import html
import io
import json
import re
import threading
import unicodedata
import zipfile
from mimetypes import guess_type
from pathlib import Path
from datetime import datetime, timedelta, timezone
import secrets
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.chat.api import (
    _build_professional_document_pdf,
    _load_case_documents_for_llm,
    _sanitize_generated_legal_document_body,
    _user_visible_text,
)
from app.security import require_api_key

from aijurisdictionagents.api_db import (
    AIModelUsageAuditEntry,
    ApiDatabaseStore,
    Case,
    CaseCitation,
    CaseCommunication,
    CaseDocument,
)
from services.document_processor.service import DocumentProcessor
from services.document_processor.runtime import render_documents_for_prompt
from app.services.email_scheduler import EmailScheduler

router = APIRouter(prefix='/v1/cases', tags=['cases'], dependencies=[Depends(require_api_key)])
_LOGGER = logging.getLogger(__name__)
_STORE_LOCK = threading.Lock()
_STORE_CACHE: dict[tuple[str, str, str, str, str], ApiDatabaseStore] = {}
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _document_processor_mode() -> str:
    value = os.getenv(
        "DOCUMENT_PROCESSOR_OPTION",
        os.getenv("DOCUMENT_PROCESSOR", "api"),
    ).strip().lower()
    if value in {"", "api", "local"}:
        return "api"
    if value == "azure":
        return "azure"
    return "api"


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
    citations: list["CaseCitationResponse"] = Field(default_factory=list)


class CaseCitationResponse(BaseModel):
    id: str
    case_id: str
    question_message_id: str | None = None
    answer_message_id: str | None = None
    source_type: str
    source_id: str | None = None
    source_url: str | None = None
    title: str
    citation_label: str | None = None
    law_number: str | None = None
    section: str | None = None
    effective_from: str | None = None
    court: str | None = None
    ecli: str | None = None
    file_number: str | None = None
    decision_date: str | None = None
    snippet: str | None = None
    retrieval_tool: str | None = None
    relevance_score: float | None = None
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
    citations: list[CaseCitationResponse] = Field(default_factory=list)


class CaseCitationsResponse(BaseModel):
    case_id: str
    citations: list[CaseCitationResponse]


class CaseAIModelAuditEntryResponse(BaseModel):
    usage_id: str
    session_id: str
    question_id: str
    question_preview: str
    question_sha256: str
    answer_id: str
    task_type: str
    provider: str
    model: str
    route_type: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_eur: float
    status: str
    fallback_reason: str
    request_started_at: str
    request_completed_at: str
    latency_ms: int
    audit_metadata: dict[str, object]


class CaseAIModelAuditResponse(BaseModel):
    case_id: str
    has_more: bool
    entries: list[CaseAIModelAuditEntryResponse]


class CaseDocumentUploadResponse(BaseModel):
    uploaded: list[CaseDocumentResponse]
    document_limit: int
    processed_document_count: int
    unprocessed_document_count: int


class CaseDocumentContextResponse(BaseModel):
    processed_documents: list[str]
    unprocessed_documents: list[str]


class SendCaseDocumentsEmailRequest(BaseModel):
    user_id: str = Field(min_length=1)
    recipient: str = Field(min_length=3)
    case_subject: str = Field(default="")
    version: str = Field(default="v1")
    doc_ids: list[str] | None = None
    correlation_id: str | None = None
    locale: str = Field(default="en", max_length=8)


class SendCaseDocumentsEmailResponse(BaseModel):
    email_id: str
    recipient: str
    case_subject: str
    attachment_count: int
    correlation_id: str
    share_id: str
    share_url: str
    expires_at: str


class CaseDocumentDebugStoredResponse(BaseModel):
    doc_id: str
    original_filename: str
    storage_uri: str
    processing_status: str
    processed_at: str | None = None
    extracted_characters: int
    embedding_model: str
    embedding_dimensions: int
    vector_present: bool
    chunk_count: int
    vector_preview: str


class CaseDocumentDebugPromptChunkResponse(BaseModel):
    doc_id: str
    path: str
    content: str


class CaseDocumentDebugResponse(BaseModel):
    case_id: str
    user_id: str
    db_option: str
    uses_postgres: bool
    storage_option: str
    document_processor: str
    query: str
    stored_documents: list[CaseDocumentDebugStoredResponse]
    selected_prompt_chunks: list[CaseDocumentDebugPromptChunkResponse]
    prompt_preview: str


class CaseExportWarning(BaseModel):
    code: str
    message: str
    artifact: str | None = None


def _store_cache_key() -> tuple[str, str, str, str, str]:
    return (
        os.getenv("DB_OPTION", "local").strip().lower(),
        os.getenv("DB_LOCAL", "").strip(),
        os.getenv("DB_CLOUD", "").strip(),
        os.getenv("STORAGE_OPTION", "local").strip().lower(),
        os.getenv("STORE_LOCAL", "").strip(),
    )


def get_store() -> ApiDatabaseStore:
    cache_key = _store_cache_key()
    with _STORE_LOCK:
        store = _STORE_CACHE.get(cache_key)
        if store is None:
            store = ApiDatabaseStore.from_env()
            store.initialize()
            _STORE_CACHE[cache_key] = store
        return store


@router.get('', response_model=list[CaseResponse])
def list_cases(user_id: str, store: ApiDatabaseStore = Depends(get_store)) -> list[CaseResponse]:
    return [_to_case_response(item) for item in store.list_cases(user_id=user_id)]


@router.post('', response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(payload: CreateCaseRequest, store: ApiDatabaseStore = Depends(get_store)) -> CaseResponse:
    max_active_cases = store.get_case_limit(user_id=payload.user_id)
    active = store.count_active_cases(user_id=payload.user_id)
    if active >= max_active_cases:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Maximum number of cases reached ({max_active_cases})',
        )
    case = store.create_case(user_id=payload.user_id, company_id=None, title=payload.title.strip())
    return _to_case_response(case)


@router.patch('/{case_id}', response_model=CaseResponse)
def rename_case(case_id: str, payload: UpdateCaseRequest, store: ApiDatabaseStore = Depends(get_store)) -> CaseResponse:
    _ensure_case_write_access(case_id=case_id, user_id=payload.user_id, store=store)
    try:
        case = store.update_case_title(case_id=case_id, user_id=payload.user_id, title=payload.title.strip())
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_case_response(case)


@router.delete('/{case_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: str, user_id: str, store: ApiDatabaseStore = Depends(get_store)) -> None:
    _ensure_case_write_access(case_id=case_id, user_id=user_id, store=store)
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
    list_citations = getattr(store, "list_case_citations", None)
    case_citations = (
        list_citations(case_id=case_id, limit=500) if callable(list_citations) else []
    )
    citations_by_answer_id: dict[str, list[CaseCitationResponse]] = {}
    for citation in case_citations:
        if not citation.answer_message_id:
            continue
        citations_by_answer_id.setdefault(citation.answer_message_id, []).append(
            _to_case_citation_response(citation)
        )
    messages = [
        _to_case_history_message_response(
            store=store,
            communication=item,
            citations=citations_by_answer_id.get(item.communication_id, []),
        )
        for item in reversed(visible)
    ]
    documents = [
        _to_case_document_response(item)
        for item in store.list_case_documents(case_id=case_id)
    ]
    return CaseHistoryResponse(
        messages=messages,
        has_more=has_more,
        documents=documents,
        citations=[_to_case_citation_response(item) for item in case_citations],
    )


@router.get('/{case_id}/citations', response_model=CaseCitationsResponse)
def get_case_citations(
    case_id: str,
    user_id: str,
    store: ApiDatabaseStore = Depends(get_store),
) -> CaseCitationsResponse:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    return CaseCitationsResponse(
        case_id=case_id,
        citations=[
            _to_case_citation_response(item)
            for item in store.list_case_citations(case_id=case_id, limit=500)
        ],
    )


@router.get('/{case_id}/ai-model-audit', response_model=CaseAIModelAuditResponse)
def get_case_ai_model_audit(
    case_id: str,
    user_id: str,
    offset: int = 0,
    limit: int = 50,
    store: ApiDatabaseStore = Depends(get_store),
) -> CaseAIModelAuditResponse:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    bounded_limit = min(max(limit, 1), 200)
    bounded_offset = max(offset, 0)
    entries = store.list_ai_model_usage_audit(
        case_id=case_id,
        limit=bounded_limit + 1,
        offset=bounded_offset,
    )
    has_more = len(entries) > bounded_limit
    visible_entries = entries[:bounded_limit]
    return CaseAIModelAuditResponse(
        case_id=case_id,
        has_more=has_more,
        entries=[_to_case_ai_model_audit_entry_response(item) for item in visible_entries],
    )


@router.get('/{case_id}/export')
def export_case(
    case_id: str,
    user_id: str,
    request: Request,
    store: ApiDatabaseStore = Depends(get_store),
) -> Response:
    case = _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    _ensure_paid_case_export_access(user_id=user_id, store=store)
    return build_case_export_response(
        case=case,
        user_id=user_id,
        store=store,
        exported_by="case-owner",
        correlation_id=str(request.state.correlation_id),
    )


@router.post('/{case_id}/documents', response_model=CaseDocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_case_documents(
    case_id: str,
    user_id: str = Query(..., min_length=1),
    files: list[UploadFile] = File(...),
    store: ApiDatabaseStore = Depends(get_store),
) -> CaseDocumentUploadResponse:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    _ensure_case_write_access(case_id=case_id, user_id=user_id, store=store)
    limit = store.get_document_upload_limit(user_id=user_id)
    existing = store.count_case_documents(case_id=case_id)
    if existing + len(files) > limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Document limit reached for this case ({limit}).',
        )
    uploaded: list[CaseDocumentResponse] = []
    uploaded_documents: list[CaseDocument] = []
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
        stored_document = store.get_case_document(case_id=case_id, doc_id=doc_id)
        uploaded_documents.append(stored_document)
        uploaded.append(_to_case_document_response(stored_document))
        next_version += 1
    if _document_processor_mode() != "azure" and uploaded_documents:
        processor = DocumentProcessor(store)
        processor.process_documents(uploaded_documents)
        uploaded = [
            _to_case_document_response(
                store.get_case_document(case_id=case_id, doc_id=document.doc_id)
            )
            for document in uploaded_documents
        ]
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


@router.get('/{case_id}/documents/debug', response_model=CaseDocumentDebugResponse)
def get_case_document_debug(
    case_id: str,
    user_id: str,
    query: str = "",
    store: ApiDatabaseStore = Depends(get_store),
) -> CaseDocumentDebugResponse:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    contents_by_doc_id = {
        doc_id: {
            "original_filename": name,
            "extracted_text": text,
            "embedding_vector": vector,
        }
        for doc_id, name, text, vector in store.list_case_document_contents(case_id=case_id)
    }
    all_chunks = store.list_case_document_chunks(case_id=case_id)
    chunks_by_doc_id: dict[str, int] = {}
    first_chunk_by_doc_id: dict[str, tuple[str, int]] = {}
    for chunk in all_chunks:
        chunks_by_doc_id[chunk.doc_id] = chunks_by_doc_id.get(chunk.doc_id, 0) + 1
        first_chunk_by_doc_id.setdefault(
            chunk.doc_id,
            (chunk.embedding_model, chunk.embedding_dimensions),
        )

    stored_documents: list[CaseDocumentDebugStoredResponse] = []
    for document in store.list_case_documents(case_id=case_id):
        if document.kind != 'uploaded':
            continue
        content_entry = contents_by_doc_id.get(document.doc_id)
        embedding_vector = str(content_entry["embedding_vector"]) if content_entry else ""
        extracted_text = str(content_entry["extracted_text"]) if content_entry else ""
        embedding_model, embedding_dimensions = first_chunk_by_doc_id.get(document.doc_id, ("", 0))
        stored_documents.append(
            CaseDocumentDebugStoredResponse(
                doc_id=document.doc_id,
                original_filename=document.original_filename,
                storage_uri=document.storage_uri,
                processing_status=document.processing_status,
                processed_at=document.processed_at,
                extracted_characters=len(extracted_text),
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
                vector_present=bool(embedding_vector.strip()),
                chunk_count=chunks_by_doc_id.get(document.doc_id, 0),
                vector_preview=embedding_vector[:120],
            )
        )

    selected_documents, _processed_names, _unprocessed_names = _load_case_documents_for_llm(
        case_id=case_id,
        query=query,
    )
    selected_prompt_chunks = [
        CaseDocumentDebugPromptChunkResponse(
            doc_id=item.doc_id,
            path=item.path,
            content=item.content,
        )
        for item in selected_documents
    ]
    prompt_preview = render_documents_for_prompt(
        [(item.path, item.content) for item in selected_documents],
        max_chars=4000,
        per_document_chars=900,
    )
    return CaseDocumentDebugResponse(
        case_id=case_id,
        user_id=user_id,
        db_option=store.db_option,
        uses_postgres=store.uses_postgres,
        storage_option=store.storage_option,
        document_processor=_document_processor_mode(),
        query=query,
        stored_documents=stored_documents,
        selected_prompt_chunks=selected_prompt_chunks,
        prompt_preview=prompt_preview,
    )


@router.get('/{case_id}/documents/{doc_id}')
def download_case_document(
    case_id: str,
    doc_id: str,
    user_id: str,
    disposition: str = Query(default="attachment", pattern="^(attachment|inline)$"),
    store: ApiDatabaseStore = Depends(get_store),
) -> Response:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    try:
        document = store.get_case_document(case_id=case_id, doc_id=doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        payload = store.read_storage_bytes(storage_uri=document.storage_uri)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stored payload is unavailable for document {doc_id}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Case storage backend is not reachable for this document",
        ) from exc
    media_type = guess_type(document.original_filename)[0] or 'application/octet-stream'
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            'Content-Disposition': f'{disposition}; filename="{document.original_filename}"',
        },
    )


@router.get('/{case_id}/documents/{doc_id}/pdf')
def download_generated_case_document_pdf(
    case_id: str,
    doc_id: str,
    user_id: str,
    disposition: str = Query(default="attachment", pattern="^(attachment|inline)$"),
    store: ApiDatabaseStore = Depends(get_store),
) -> Response:
    case = _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    try:
        document = store.get_case_document(case_id=case_id, doc_id=doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    visible_content = _generated_case_document_storage_content(document=document, store=store) or (
        _generated_case_document_visible_content(case_id=case_id, doc_id=document.doc_id, store=store)
    )
    document_type = _generated_case_document_type(visible_content)
    filename = _generated_case_document_filename(
        case_title=case.title,
        doc_id=document.doc_id,
        document_type=document_type,
    )
    pdf_content = _render_generated_case_document_pdf_bytes(
        case=case,
        user_id=user_id,
        document=document,
        store=store,
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            'Content-Disposition': f'{disposition}; filename="{filename}"',
        },
    )


@router.post('/{case_id}/documents/send-email', response_model=SendCaseDocumentsEmailResponse)
def send_case_documents_email(
    case_id: str,
    payload: SendCaseDocumentsEmailRequest,
    store: ApiDatabaseStore = Depends(get_store),
) -> SendCaseDocumentsEmailResponse:
    case = _ensure_case_access(case_id=case_id, user_id=payload.user_id, store=store)
    requested_doc_ids = {item.strip() for item in payload.doc_ids or [] if item.strip()}
    documents = [
        item
        for item in store.list_case_documents(case_id=case_id)
        if item.kind == "generated_document"
        and (not requested_doc_ids or item.doc_id in requested_doc_ids)
    ]
    if len(documents) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Select exactly one generated document to share.",
        )
    correlation_id = (payload.correlation_id or str(uuid4())).strip()
    subject = (payload.case_subject or case.title).strip() or f"Case {case.case_id}"
    locale = _document_share_locale(payload.locale)
    raw_token = secrets.token_urlsafe(32)
    share_id = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=_document_share_lifetime_days())
    store.create_document_share(
        share_id=share_id,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        case_id=case_id,
        doc_id=documents[0].doc_id,
        sender_user_id=payload.user_id,
        recipient_email=payload.recipient,
        locale=locale,
        expires_at=expires_at.isoformat(),
    )
    share_url = f"{_case_deep_link_base_url()}/shared-documents/{quote(raw_token, safe='')}"
    email_content = _document_share_email_content(locale=locale, share_url=share_url, expires_at=expires_at)
    scheduler = EmailScheduler.from_env()
    email_id = scheduler.enqueue(
        recipient=payload.recipient.strip().lower(),
        subject=email_content["subject"],
        body=email_content["plain"],
        metadata={
            "event": "document_share_invitation",
            "case_id": case_id,
            "share_id": share_id,
            "html_body": email_content["html"],
            "locale": locale,
        },
    )
    store.record_document_share_audit(share_id=share_id, action="share.created", outcome="email_queued")
    return SendCaseDocumentsEmailResponse(
        email_id=email_id,
        recipient=payload.recipient.strip().lower(),
        case_subject=subject,
        attachment_count=0,
        correlation_id=correlation_id,
        share_id=share_id,
        share_url=share_url,
        expires_at=expires_at.isoformat(),
    )


@router.delete('/{case_id}/documents/shares/{share_id}', status_code=status.HTTP_204_NO_CONTENT)
def revoke_case_document_share(
    case_id: str,
    share_id: str,
    user_id: str,
    store: ApiDatabaseStore = Depends(get_store),
) -> Response:
    _ensure_case_access(case_id=case_id, user_id=user_id, store=store)
    if not store.revoke_document_share(share_id=share_id, sender_user_id=user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document share not found.")
    store.record_document_share_audit(share_id=share_id, action="share.revoked", outcome="success")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def build_case_export_response(
    *,
    case: Case,
    user_id: str,
    store: ApiDatabaseStore,
    exported_by: str,
    correlation_id: str,
) -> Response:
    export = _build_case_export_zip(
        case=case,
        user_id=user_id,
        store=store,
        exported_by=exported_by,
        correlation_id=correlation_id,
    )
    filename = f"{_safe_filename(case.title or case.case_id)}_{case.case_id}_case_export.zip"
    return Response(
        content=export,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Case-Export-Schema": "jurisdigta.case-export.v1",
        },
    )


def _build_case_export_zip(
    *,
    case: Case,
    user_id: str,
    store: ApiDatabaseStore,
    exported_by: str,
    correlation_id: str,
) -> bytes:
    warnings: list[CaseExportWarning] = []
    checksums: dict[str, str] = {}
    files: dict[str, bytes] = {}
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    communications = store.list_case_communications(case_id=case.case_id, limit=None, offset=0)
    chronological_messages = list(reversed(communications))
    messages = [
        _case_export_message_dict(store=store, communication=item)
        for item in chronological_messages
    ]
    documents = store.list_case_documents(case_id=case.case_id)
    audit_entries = [
        _case_export_ai_model_audit_dict(item)
        for item in store.list_ai_model_usage_audit(case_id=case.case_id, limit=500, offset=0)
    ]
    citations = _collect_case_export_citations(messages=messages, audit_entries=audit_entries)

    case_payload = {
        "schema": "jurisdigta.case-export.case.v1",
        "case_id": case.case_id,
        "user_id": case.user_id,
        "company_id": case.company_id,
        "title": case.title,
        "status": case.status,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
    }
    document_manifest: list[dict[str, object]] = []

    files["case.json"] = _json_bytes(case_payload)
    files["messages.jsonl"] = "\n".join(_json_line(item) for item in messages).encode("utf-8")
    files["ai-model-audit.json"] = _json_bytes(
        {
            "schema": "jurisdigta.case-export.ai-model-audit.v1",
            "case_id": case.case_id,
            "entries": audit_entries,
        }
    )
    files["citations.json"] = _json_bytes(
        {
            "schema": "jurisdigta.case-export.citations.v1",
            "case_id": case.case_id,
            "items": citations,
        }
    )

    for index, document in enumerate(documents, start=1):
        source_artifact = _case_export_document_artifact_path(
            document=document,
            index=index,
            rendered=False,
        )
        document_entry: dict[str, object] = {
            "doc_id": document.doc_id,
            "kind": document.kind,
            "version": document.version,
            "original_filename": document.original_filename,
            "processing_status": document.processing_status,
            "processing_error": document.processing_error,
            "processed_at": document.processed_at,
            "created_at": document.created_at,
            "source_artifact": source_artifact,
        }
        try:
            files[source_artifact] = store.read_storage_bytes(storage_uri=document.storage_uri)
        except FileNotFoundError:
            warnings.append(
                CaseExportWarning(
                    code="document_payload_missing",
                    message=f"Stored payload is unavailable for document {document.doc_id}.",
                    artifact=source_artifact,
                )
            )
        except ValueError:
            warnings.append(
                CaseExportWarning(
                    code="document_storage_unavailable",
                    message=f"Storage backend is unavailable for document {document.doc_id}.",
                    artifact=source_artifact,
                )
            )

        if document.kind == "generated_document":
            rendered_artifact = _case_export_document_artifact_path(
                document=document,
                index=index,
                rendered=True,
                case_title=case.title,
            )
            document_entry["rendered_pdf_artifact"] = rendered_artifact
            try:
                rendered_pdf = _render_generated_case_document_pdf_bytes(
                    case=case,
                    user_id=user_id,
                    document=document,
                    store=store,
                )
                files[rendered_artifact] = rendered_pdf
            except HTTPException as exc:
                warnings.append(
                    CaseExportWarning(
                        code="generated_pdf_unavailable",
                        message=str(exc.detail),
                        artifact=rendered_artifact,
                    )
                )
        document_manifest.append(document_entry)

    manifest = {
        "schema": "jurisdigta.case-export.v1",
        "generated_at": generated_at,
        "exported_by": exported_by,
        "correlation_id": correlation_id,
        "case_id": case.case_id,
        "user_id": user_id,
        "case_title": case.title,
        "artifact_count": 0,
        "message_count": len(messages),
        "document_count": len(documents),
        "ai_model_audit_count": len(audit_entries),
        "models_used": _case_export_models_used(audit_entries),
        "citation_count": len(citations),
        "documents": document_manifest,
    }
    files["warnings.json"] = _json_bytes(
        {
            "schema": "jurisdigta.case-export.warnings.v1",
            "case_id": case.case_id,
            "items": [_warning_dict(item) for item in warnings],
        }
    )
    files["manifest.json"] = _json_bytes({**manifest, "artifact_count": len(files) + 2})

    for path, payload in sorted(files.items()):
        checksums[path] = hashlib.sha256(payload).hexdigest()
    checksums_payload = "".join(
        f"{digest}  {path}\n" for path, digest in sorted(checksums.items())
    ).encode("utf-8")
    files["sha256sums.txt"] = checksums_payload

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            _writestr_deterministic(archive, path, files[path])
    return buffer.getvalue()


def _case_export_models_used(
    audit_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return a privacy-minimized model summary while detailed usage stays in the audit file."""
    grouped: dict[tuple[str, str, str, str], int] = {}
    for entry in audit_entries:
        key = (
            str(entry.get("provider") or "unknown"),
            str(entry.get("model") or "unknown"),
            str(entry.get("route_type") or "unknown"),
            str(entry.get("status") or "unknown"),
        )
        grouped[key] = grouped.get(key, 0) + 1
    return [
        {
            "provider": provider,
            "model": model,
            "route_type": route_type,
            "status": status,
            "usage_count": count,
        }
        for (provider, model, route_type, status), count in sorted(grouped.items())
    ]


def _render_generated_case_document_pdf_bytes(
    *,
    case: Case,
    user_id: str,
    document: CaseDocument,
    store: ApiDatabaseStore,
) -> bytes:
    visible_content = _generated_case_document_storage_content(document=document, store=store)
    if not visible_content:
        visible_content = _generated_case_document_visible_content(
            case_id=case.case_id,
            doc_id=document.doc_id,
            store=store,
        )
    if not visible_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rendered PDF content is unavailable for document {document.doc_id}",
        )
    visible_content = _clean_generated_case_document_pdf_content(visible_content)
    return _build_professional_document_pdf(
        title=_generated_case_document_title(visible_content),
        lines=visible_content.splitlines(),
        country="SK",
        language="SK",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        case_id=case.case_id,
        session_id=getattr(document, "session_id", None),
        user_id=user_id,
        footer_line="JurisDigta generated case document",
        verification_score=None,
    )


def _case_export_message_dict(
    *,
    store: ApiDatabaseStore,
    communication: CaseCommunication,
) -> dict[str, object]:
    response = _to_case_history_message_response(store=store, communication=communication)
    return {
        "communication_id": response.communication_id,
        "role": response.role,
        "content": response.content,
        "agent_name": response.agent_name,
        "created_at": response.created_at,
    }


def _case_export_ai_model_audit_dict(item: AIModelUsageAuditEntry) -> dict[str, object]:
    return {
        "usage_id": item.usage_id,
        "case_id": item.case_id,
        "user_id": item.user_id,
        "subscription_id": item.subscription_id,
        "plan_code": item.plan_code,
        "task_type": item.task_type,
        "model_group_id": item.model_group_id,
        "provider": item.provider,
        "model": item.model,
        "route_type": item.route_type,
        "input_tokens": item.input_tokens,
        "cached_input_tokens": item.cached_input_tokens,
        "output_tokens": item.output_tokens,
        "total_tokens": item.total_tokens,
        "estimated_cost_eur": item.estimated_cost_eur,
        "provider_currency": item.provider_currency,
        "request_started_at": item.request_started_at,
        "request_completed_at": item.request_completed_at,
        "latency_ms": item.latency_ms,
        "status": item.status,
        "fallback_reason": item.fallback_reason,
        "session_id": item.session_id,
        "question_id": item.question_id,
        "question_preview": item.question_preview,
        "question_sha256": item.question_sha256,
        "answer_id": item.answer_id,
        "audit_metadata": item.audit_metadata,
        "created_at": item.created_at,
    }


def _collect_case_export_citations(
    *,
    messages: list[dict[str, object]],
    audit_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    seen: set[str] = set()
    citations: list[dict[str, object]] = []
    for entry in audit_entries:
        metadata = entry.get("audit_metadata")
        for candidate in _find_law_citations(metadata):
            key = _json_line(candidate)
            if key not in seen:
                seen.add(key)
                citations.append(candidate)
    for message in messages:
        content = str(message.get("content") or "")
        for candidate in _extract_visible_citation_lines(content):
            key = str(candidate.get("text") or "")
            if key and key not in seen:
                seen.add(key)
                citations.append(candidate)
    return citations


def _find_law_citations(value: object) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "law_citations" and isinstance(nested, list):
                citations.extend(item for item in nested if isinstance(item, dict))
            else:
                citations.extend(_find_law_citations(nested))
    elif isinstance(value, list):
        for nested in value:
            citations.extend(_find_law_citations(nested))
    return citations


def _extract_visible_citation_lines(content: str) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    capture = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if lowered in {"pravne citacie", "právne citácie", "legal citations"}:
            capture = True
            continue
        if capture and not line:
            continue
        if capture and line:
            if len(line) > 500:
                line = line[:500]
            citations.append({"source": "visible_message", "text": line})
            if len(citations) >= 20:
                break
    return citations


def _case_export_document_artifact_path(
    *,
    document: CaseDocument,
    index: int,
    rendered: bool,
    case_title: str = "",
) -> str:
    if rendered:
        filename = _generated_case_document_filename(
            case_title=case_title,
            doc_id=document.doc_id,
            document_type="dokument",
        )
        return f"documents/generated/rendered-pdf/{index:04d}_{_safe_filename(filename)}"
    folder = "generated/source" if document.kind == "generated_document" else _safe_filename(document.kind)
    return f"documents/{folder}/{index:04d}_{_safe_filename(document.original_filename)}"


def _ensure_paid_case_export_access(*, user_id: str, store: ApiDatabaseStore) -> None:
    plan = store.get_effective_subscription_plan(user_id=user_id)
    if plan.plan_code == "free" or plan.price_eur <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Case export is available only for active paid subscriptions.",
        )


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = normalized.strip(".-")
    return normalized[:120] or "case-export"


def _json_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _warning_dict(item: CaseExportWarning) -> dict[str, str | None]:
    return {"code": item.code, "message": item.message, "artifact": item.artifact}


def _writestr_deterministic(archive: zipfile.ZipFile, path: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=_ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, payload)


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


def _ensure_case_write_access(*, case_id: str, user_id: str, store: ApiDatabaseStore) -> None:
    try:
        block = store.get_case_write_block_detail(case_id=case_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if block is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=block.to_api_detail())


def _read_case_communication_content(
    *, store: ApiDatabaseStore, communication: CaseCommunication
) -> str:
    content: str = communication.summary
    transcript_uri = communication.transcript_uri
    if transcript_uri is None or not transcript_uri.strip():
        return content
    try:
        return str(store.read_storage_text(storage_uri=transcript_uri))
    except FileNotFoundError:
        _LOGGER.info(
            'Case communication transcript not found; using summary fallback',
            extra={
                'case_id': communication.case_id,
                'communication_id': communication.communication_id,
                'transcript_uri': transcript_uri,
            },
        )
        return content
    except Exception:
        _LOGGER.warning(
            'Falling back to case communication summary because transcript could not be read',
            extra={
                'case_id': communication.case_id,
                'communication_id': communication.communication_id,
                'transcript_uri': transcript_uri,
            },
            exc_info=True,
        )
        return content


def _to_case_history_message_response(
    *,
    store: ApiDatabaseStore,
    communication: CaseCommunication,
    citations: list[CaseCitationResponse] | None = None,
) -> CaseHistoryMessageResponse:
    content = _read_case_communication_content(store=store, communication=communication)
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
    if role == 'assistant':
        normalized = _user_visible_text(normalized)
    return CaseHistoryMessageResponse(
        communication_id=communication.communication_id,
        role=role,
        content=normalized,
        agent_name=agent_name,
        created_at=communication.created_at,
        citations=citations or [],
    )


def _to_case_citation_response(citation: CaseCitation) -> CaseCitationResponse:
    return CaseCitationResponse(
        id=citation.citation_id,
        case_id=citation.case_id,
        question_message_id=citation.question_message_id,
        answer_message_id=citation.answer_message_id,
        source_type=citation.source_type,
        source_id=citation.source_id,
        source_url=citation.source_url,
        title=citation.title,
        citation_label=citation.citation_label,
        law_number=citation.law_number,
        section=citation.section,
        effective_from=citation.effective_from,
        court=citation.court,
        ecli=citation.ecli,
        file_number=citation.file_number,
        decision_date=citation.decision_date,
        snippet=citation.snippet,
        retrieval_tool=citation.retrieval_tool,
        relevance_score=citation.relevance_score,
        created_at=citation.created_at,
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


def _to_case_ai_model_audit_entry_response(
    item: AIModelUsageAuditEntry,
) -> CaseAIModelAuditEntryResponse:
    return CaseAIModelAuditEntryResponse(
        usage_id=item.usage_id,
        session_id=item.session_id,
        question_id=item.question_id,
        question_preview=item.question_preview,
        question_sha256=item.question_sha256,
        answer_id=item.answer_id,
        task_type=item.task_type,
        provider=item.provider,
        model=item.model,
        route_type=item.route_type,
        input_tokens=item.input_tokens,
        cached_input_tokens=item.cached_input_tokens,
        output_tokens=item.output_tokens,
        total_tokens=item.total_tokens,
        estimated_cost_eur=item.estimated_cost_eur,
        status=item.status,
        fallback_reason=item.fallback_reason,
        request_started_at=item.request_started_at,
        request_completed_at=item.request_completed_at,
        latency_ms=item.latency_ms,
        audit_metadata=dict(item.audit_metadata),
    )


def _generated_case_document_visible_content(
    *, case_id: str, doc_id: str, store: ApiDatabaseStore
) -> str:
    marker = f"/documents/{doc_id}"
    for communication in store.list_case_communications(case_id=case_id, limit=100, offset=0):
        raw_content = _read_case_communication_content(
            store=store,
            communication=communication,
        )
        if marker not in raw_content:
            continue
        normalized = raw_content.strip()
        upper = normalized.upper()
        if upper.startswith('ASSISTANT:'):
            normalized = normalized[10:].strip()
        elif upper.startswith('USER:') or upper.startswith('SYSTEM:'):
            continue
        if normalized.endswith(')') and '(agent=' in normalized:
            normalized = normalized.rpartition('(agent=')[0].strip()
        visible = _user_visible_text(normalized).strip()
        if visible:
            return _extract_generated_case_document_body(visible) or visible
    return _latest_generated_case_document_visible_content(case_id=case_id, store=store)


def _generated_case_document_storage_content(*, document: CaseDocument, store: ApiDatabaseStore) -> str:
    if document.kind != "generated_document":
        return ""
    try:
        return str(store.read_storage_text(storage_uri=document.storage_uri)).strip()
    except FileNotFoundError:
        _LOGGER.info(
            "Generated case document payload not found; falling back to communication content",
            extra={"doc_id": document.doc_id, "storage_uri": document.storage_uri},
        )
    except Exception:
        _LOGGER.warning(
            "Generated case document payload could not be read; falling back to communication content",
            extra={"doc_id": document.doc_id, "storage_uri": document.storage_uri},
            exc_info=True,
        )
    return ""


def _clean_generated_case_document_pdf_content(content: str) -> str:
    stripped = content.strip()
    if not stripped:
        return ""
    extracted = _extract_generated_case_document_body(stripped)
    if extracted:
        return extracted
    sanitized = _sanitize_generated_legal_document_body(stripped)
    if sanitized and _looks_like_generated_case_document_body(sanitized):
        return sanitized
    return stripped


def _latest_generated_case_document_visible_content(
    *, case_id: str, store: ApiDatabaseStore
) -> str:
    for communication in store.list_case_communications(case_id=case_id, limit=100, offset=0):
        raw_content = _read_case_communication_content(
            store=store,
            communication=communication,
        )
        normalized = raw_content.strip()
        upper = normalized.upper()
        if upper.startswith('ASSISTANT:'):
            normalized = normalized[10:].strip()
        elif upper.startswith('USER:') or upper.startswith('SYSTEM:'):
            continue
        if normalized.endswith(')') and '(agent=' in normalized:
            normalized = normalized.rpartition('(agent=')[0].strip()
        visible = _user_visible_text(normalized).strip()
        if not _looks_like_generated_case_document_message(visible):
            continue
        return _extract_generated_case_document_body(visible) or visible
    return ""


def _generated_case_document_title(content: str) -> str:
    document_type = _generated_case_document_type(content)
    if document_type:
        return document_type
    for line in content.splitlines():
        stripped = line.strip().strip("*#:- ")
        if stripped:
            return stripped[:120]
    return "Case document"


def _generated_case_document_type(content: str) -> str:
    normalized = _normalize_for_filename(content)
    type_markers = (
        ("splnomocnenie", "Splnomocnenie"),
        ("power of attorney", "Power of Attorney"),
        ("potvrdenie", "Potvrdenie"),
        ("predzalobna vyzva", "Predžalobná výzva"),
        ("najomna zmluva", "Nájomná zmluva"),
        ("zaloba", "Žaloba"),
        ("navrh", "Návrh"),
        ("zmluva", "Zmluva"),
    )
    for marker, display_name in type_markers:
        if marker in normalized:
            return display_name
    return "Dokument"


def _generated_case_document_filename(
    *, case_title: str, doc_id: str, document_type: str
) -> str:
    case_slug = _filename_slug(case_title, fallback="case")
    type_slug = _filename_slug(document_type, fallback="document")
    guid = doc_id.strip() or str(uuid4())
    return f"{case_slug}_{guid}_{type_slug}.pdf"


def _filename_slug(value: str, *, fallback: str) -> str:
    normalized = _normalize_for_filename(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug[:80].strip("-") or fallback


def _normalize_for_filename(value: str) -> str:
    without_accents = unicodedata.normalize("NFKD", value)
    ascii_text = without_accents.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def _looks_like_generated_case_document_message(content: str) -> bool:
    normalized = " ".join(content.lower().split())
    if not normalized:
        return False
    if (
        ("splnomocnenie" in normalized or "power of attorney" in normalized)
        and ("dokumenty su pripravene" in normalized or "finalne verzie" in normalized)
    ):
        return True
    document_markers = (
        "splnomocnenie",
        "potvrdenie o zaplaten",
        "potvrdenie o platbe",
        "predžalobná výzva",
        "predzalobna vyzva",
        "nájomná zmluva",
        "najomna zmluva",
        "zmluva",
        "žaloba",
        "zaloba",
        "návrh",
        "navrh",
    )
    ready_markers = (
        "konečná verzia dokumentu",
        "konecna verzia dokumentu",
        "dokument je pripraven",
        "pripravený na stiahnutie",
        "pripraveny na stiahnutie",
        "vygenerujem vo formáte pdf",
        "vygenerujem vo formate pdf",
    )
    payment_sentence = (
        ("týmto potvrdzujem" in normalized or "tymto potvrdzujem" in normalized)
        and ("zaplatil" in normalized or "uhradil" in normalized)
    )
    return (
        any(marker in normalized for marker in document_markers)
        and any(marker in normalized for marker in ready_markers)
    ) or payment_sentence


def _extract_generated_case_document_body(content: str) -> str:
    sections: list[list[str]] = []
    current: list[str] = []
    saw_separator = False
    for line in content.splitlines():
        if line.strip() in {"---", "—", "___"}:
            saw_separator = True
            if current:
                sections.append(current)
                current = []
            continue
        if line.strip().strip("-—_ ") == "":
            current.append(line)
            continue
        current.append(line)
    if current:
        sections.append(current)
    if not saw_separator:
        return ""
    candidates: list[str] = []
    for section in sections:
        cleaned = _clean_generated_case_document_section(section)
        if _looks_like_generated_case_document_body(cleaned):
            candidates.append(cleaned)
    if not candidates:
        return ""
    return candidates[0].strip()


def _clean_generated_case_document_section(lines: list[str]) -> str:
    cleaned_lines: list[str] = []
    for line in lines:
        cleaned = line.strip()
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s+", "", cleaned)
        cleaned = cleaned.strip("*_ ")
        cleaned_lines.append(cleaned)
    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
    return "\n".join(cleaned_lines).strip()


def _looks_like_generated_case_document_body(content: str) -> bool:
    normalized = " ".join(content.lower().split())
    title_markers = (
        "splnomocnenie",
        "potvrdenie",
        "zmluva",
        "výzva",
        "vyzva",
        "žaloba",
        "zaloba",
        "návrh",
        "navrh",
    )
    body_markers = (
        "ja,",
        "týmto",
        "tymto",
        "dátum",
        "datum",
        "splnomocnujem",
        "podpis",
        "zmluvné strany",
        "zmluvne strany",
        "predmet",
    )
    return any(marker in normalized for marker in title_markers) and any(
        marker in normalized for marker in body_markers
    )


def _document_context(*, case_id: str, store: ApiDatabaseStore) -> CaseDocumentContextResponse:
    processed: list[str] = []
    unprocessed: list[str] = []
    for document in store.list_case_documents(case_id=case_id):
        if document.kind not in {'uploaded', 'chat_attachment', 'session_history', 'generated_document'}:
            continue
        if document.processing_status == 'processed':
            processed.append(document.original_filename)
        else:
            unprocessed.append(document.original_filename)
    return CaseDocumentContextResponse(
        processed_documents=processed,
        unprocessed_documents=unprocessed,
    )


def _case_deep_link_base_url() -> str:
    configured = os.getenv("JURISDIGTA_AGENT_BASE_URL", "").strip().rstrip("/")
    if configured and configured != "unknown-variable":
        return configured
    return "https://agent.jurisdigta.eu"


def _build_case_deep_link(*, case_id: str) -> str:
    return f"{_case_deep_link_base_url()}/case/{quote(case_id.strip(), safe='')}"


def _document_share_lifetime_days() -> int:
    raw = os.getenv("DOCUMENT_SHARE_LIFETIME_DAYS", "7").strip()
    try:
        return max(1, min(int(raw), 30))
    except ValueError:
        return 7


def _document_share_locale(value: str) -> str:
    normalized = value.strip().lower().split("-", 1)[0]
    return normalized if normalized in {"en", "sk", "de"} else "en"


def _document_share_email_content(
    *, locale: str, share_url: str, expires_at: datetime
) -> dict[str, str]:
    copy = {
        "en": {
            "subject": "A legal document was shared with you | JurisDigta",
            "greeting": "Hello,",
            "body": "A JurisDigta user shared one legal document with you.",
            "action": "Open the protected document",
            "expiry": "The link expires on {date}. Registration is not required; email verification is required.",
            "warning": "Review AI-assisted legal documents with a qualified person before filing, signing, or relying on them.",
            "unexpected": "If you did not expect this message, do not open the link and contact JurisDigta support.",
        },
        "sk": {
            "subject": "Bol vám zdieľaný právny dokument | JurisDigta",
            "greeting": "Dobrý deň,",
            "body": "Používateľ JurisDigta s vami zdieľal jeden právny dokument.",
            "action": "Otvoriť chránený dokument",
            "expiry": "Odkaz je platný do {date}. Registrácia nie je potrebná; vyžaduje sa overenie e-mailom.",
            "warning": "Právne dokumenty vytvorené s podporou AI pred podaním, podpisom alebo použitím skontrolujte s kvalifikovanou osobou.",
            "unexpected": "Ak ste túto správu neočakávali, odkaz neotvárajte a kontaktujte podporu JurisDigta.",
        },
        "de": {
            "subject": "Ein Rechtsdokument wurde mit Ihnen geteilt | JurisDigta",
            "greeting": "Guten Tag,",
            "body": "Ein JurisDigta-Benutzer hat ein Rechtsdokument mit Ihnen geteilt.",
            "action": "Geschütztes Dokument öffnen",
            "expiry": "Der Link ist bis {date} gültig. Eine Registrierung ist nicht erforderlich; eine E-Mail-Verifizierung ist erforderlich.",
            "warning": "Lassen Sie KI-unterstützte Rechtsdokumente vor Einreichung, Unterzeichnung oder Verwendung qualifiziert prüfen.",
            "unexpected": "Wenn Sie diese Nachricht nicht erwartet haben, öffnen Sie den Link nicht und kontaktieren Sie den JurisDigta-Support.",
        },
    }[locale]
    expiry = copy["expiry"].format(date=expires_at.strftime("%Y-%m-%d %H:%M UTC"))
    plain = "\n\n".join((copy["greeting"], copy["body"], f"{copy['action']}: {share_url}", expiry, copy["warning"], copy["unexpected"]))
    escaped_url = html.escape(share_url, quote=True)
    html_body = (
        "<html><body style='font-family:Arial,sans-serif;color:#1f2937'>"
        f"<p>{html.escape(copy['greeting'])}</p><p>{html.escape(copy['body'])}</p>"
        f"<p><a href='{escaped_url}'>{html.escape(copy['action'])}</a></p>"
        f"<p>{html.escape(expiry)}</p><p>{html.escape(copy['warning'])}</p>"
        f"<p>{html.escape(copy['unexpected'])}</p></body></html>"
    )
    return {"subject": copy["subject"], "plain": plain, "html": html_body}


def _case_document_email_attachment(
    *,
    case: Case,
    user_id: str,
    document: CaseDocument,
    store: ApiDatabaseStore,
) -> dict[str, str]:
    if document.kind == "generated_document":
        pdf_content = _render_generated_case_document_pdf_bytes(
            case=case,
            user_id=user_id,
            document=document,
            store=store,
        )
        visible_content = _generated_case_document_storage_content(document=document, store=store) or (
            _generated_case_document_visible_content(
                case_id=case.case_id,
                doc_id=document.doc_id,
                store=store,
            )
        )
        return {
            "filename": _generated_case_document_filename(
                case_title=case.title,
                doc_id=document.doc_id,
                document_type=_generated_case_document_type(visible_content),
            ),
            "mime_type": "application/pdf",
            "content_base64": base64.b64encode(pdf_content).decode("utf-8"),
        }
    try:
        raw = store.read_storage_bytes(storage_uri=document.storage_uri)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stored payload is unavailable for document {document.doc_id}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Case storage backend is not reachable for this document",
        ) from exc
    return {
        "filename": document.original_filename,
        "mime_type": guess_type(document.original_filename)[0] or "application/octet-stream",
        "content_base64": base64.b64encode(raw).decode("utf-8"),
    }


def _build_lawyer_email_html(
    *,
    case_subject: str,
    version: str,
    correlation_id: str,
    case_url: str,
) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    escaped_subject = html.escape(case_subject)
    escaped_version = html.escape(version)
    escaped_correlation_id = html.escape(correlation_id)
    escaped_case_url = html.escape(case_url, quote=True)
    return (
        "<html><body style='font-family:Georgia,serif;color:#1f2937'>"
        "<p>Dear Client,</p>"
        "<p>Please find attached your generated legal documents prepared for the referenced case subject.</p>"
        f"<p>Open the case in JurisDigta: <a href='{escaped_case_url}'>{escaped_case_url}</a></p>"
        "<p>Review the generated legal documents before filing, signing, or relying on them.</p>"
        "<p>Kind regards,<br/>JurisDigta Legal Desk</p>"
        "<hr/>"
        f"<p style='font-size:12px;color:#6b7280'>Case Subject: {escaped_subject}<br/>"
        f"Version: {escaped_version}<br/>Correlation ID: {escaped_correlation_id}<br/>Generated: {timestamp}</p>"
        "</body></html>"
    )
