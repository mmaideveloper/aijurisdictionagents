from __future__ import annotations

import logging
import os
import base64
import re
import threading
import unicodedata
from mimetypes import guess_type
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.chat.api import (
    _build_professional_document_pdf,
    _load_case_documents_for_llm,
    _user_visible_text,
)
from app.security import require_api_key

from aijurisdictionagents.api_db import (
    ApiDatabaseStore,
    Case,
    CaseCommunication,
    CaseDocument,
)
from services.document_processor.service import DocumentProcessor
from services.document_processor.runtime import render_documents_for_prompt
from app.services.email_scheduler import EmailScheduler

router = APIRouter(prefix='/v1/cases', tags=['cases'], dependencies=[Depends(require_api_key)])
_MAX_ACTIVE_CASES = 5
_LOGGER = logging.getLogger(__name__)
_STORE_LOCK = threading.Lock()
_STORE_CACHE: dict[tuple[str, str, str, str, str], ApiDatabaseStore] = {}


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


class SendCaseDocumentsEmailRequest(BaseModel):
    user_id: str = Field(min_length=1)
    recipient: str = Field(min_length=3)
    case_subject: str = Field(default="")
    version: str = Field(default="v1")
    doc_ids: list[str] | None = None
    correlation_id: str | None = None


class SendCaseDocumentsEmailResponse(BaseModel):
    email_id: str
    recipient: str
    case_subject: str
    attachment_count: int
    correlation_id: str


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
    visible_content = _generated_case_document_storage_content(document=document, store=store)
    if not visible_content:
        visible_content = _generated_case_document_visible_content(
            case_id=case_id,
            doc_id=document.doc_id,
            store=store,
        )
    if not visible_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rendered PDF content is unavailable for document {doc_id}",
        )
    title = _generated_case_document_title(visible_content)
    document_type = _generated_case_document_type(visible_content)
    filename = _generated_case_document_filename(
        case_title=case.title,
        doc_id=document.doc_id,
        document_type=document_type,
    )
    pdf_content = _build_professional_document_pdf(
        title=title,
        lines=visible_content.splitlines(),
        country="SK",
        language="SK",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        case_id=case_id,
        session_id=getattr(document, "session_id", None),
        user_id=user_id,
        footer_line="AIJ generated case document",
        verification_score=None,
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
        if item.kind in {"uploaded", "chat_attachment", "session_history", "generated_document"}
        and (not requested_doc_ids or item.doc_id in requested_doc_ids)
    ]
    if not documents:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No case documents available to send.")
    correlation_id = (payload.correlation_id or str(uuid4())).strip()
    subject = (payload.case_subject or case.title).strip() or f"Case {case.case_id}"
    plain = f"Dear client,\n\nPlease find attached generated documents for case '{subject}'.\n\nRegards,\nJurisDigta Legal Team"
    html = _build_lawyer_email_html(case_subject=subject, version=payload.version.strip() or "v1", correlation_id=correlation_id)
    attachments: list[dict[str, str]] = []
    for document in documents:
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
        attachments.append(
            {
                "filename": document.original_filename,
                "mime_type": guess_type(document.original_filename)[0] or "application/octet-stream",
                "content_base64": base64.b64encode(raw).decode("utf-8"),
            }
        )
    scheduler = EmailScheduler.from_env()
    email_id = scheduler.enqueue(
        recipient=payload.recipient.strip().lower(),
        subject=f"Legal document package | {subject}",
        body=plain,
        metadata={"event": "case_documents_email", "case_id": case_id, "html_body": html, "attachments": attachments},
    )
    return SendCaseDocumentsEmailResponse(
        email_id=email_id,
        recipient=payload.recipient.strip().lower(),
        case_subject=subject,
        attachment_count=len(attachments),
        correlation_id=correlation_id,
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
    *, store: ApiDatabaseStore, communication: CaseCommunication
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
        cleaned = "\n".join(line.strip().strip("*") for line in section).strip()
        if _looks_like_generated_case_document_body(cleaned):
            candidates.append(cleaned)
    if not candidates:
        return ""
    return max(candidates, key=len).strip()


def _looks_like_generated_case_document_body(content: str) -> bool:
    normalized = " ".join(content.lower().split())
    title_markers = (
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


def _build_lawyer_email_html(*, case_subject: str, version: str, correlation_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "<html><body style='font-family:Georgia,serif;color:#1f2937'>"
        "<p>Dear Client,</p>"
        "<p>Please find attached your generated legal documents prepared for the referenced case subject.</p>"
        "<p>Kind regards,<br/>JurisDigta Legal Desk</p>"
        "<hr/>"
        f"<p style='font-size:12px;color:#6b7280'>Case Subject: {case_subject}<br/>"
        f"Version: {version}<br/>Correlation ID: {correlation_id}<br/>Generated: {timestamp}</p>"
        "</body></html>"
    )
