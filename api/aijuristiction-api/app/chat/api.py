from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import logging
from mimetypes import guess_type
import os
import re
import time
import textwrap
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile
from collections import deque
from collections.abc import Callable, Generator
from datetime import date, datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any, List, Literal, Optional, cast
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from reportlab.graphics import renderPDF  # type: ignore[import-untyped]
from reportlab.graphics.barcode import qr  # type: ignore[import-untyped]
from reportlab.graphics.shapes import Drawing  # type: ignore[import-untyped]
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]
from pypdf import PdfReader, PdfWriter

from app.chat.core_runtime import core_message_role, run_orchestration
from app.chat.case_type_detection import resolve_case_catalog_context
from app.chat.country_services import prepare_country_direct_reply
from app.flow_packs.api import get_flow_pack_store
from app.chat.intent_policy_service import (
    build_document_task_plan_note,
    is_document_modernization_request,
)
from app.chat.mcp_law_context import build_mcp_law_context
from app.chat.mcp_status_context import build_mcp_status_context
from app.chat.models import Message, MessageRole, Session, SessionResult, SessionState
from app.chat.output_validation import AILawyerOutputMessageValidationAgent, LawyerOutputUserProfile
from app.chat.repository import InMemoryChatRepository
from app.chat.result_metadata import build_session_result_metadata
from app.document_templates.disclaimers import resolve_disclaimer_from_templates
from app.document_templates.store import get_document_template_store
from app.security import require_api_key
from app.services.email_scheduler import EmailScheduler
from app.versioning import get_api_version, get_core_version

from aijurisdictionagents.api_db import ApiDatabaseStore, CaseDocument, User
from aijurisdictionagents.llm import get_embedding_client
from aijurisdictionagents.llm.base import ModelProcessingTimeout, read_positive_finite_env_seconds
from aijurisdictionagents.llm.routing import (
    ModelRouteUnavailable,
    RoutedLLMClient,
    get_routed_llm_client,
)
from aijurisdictionagents.schemas import Document as CoreDocument
from aijurisdictionagents.schemas import Message as CoreMessage
from services.document_processor.runtime import (
    cosine_similarity,
    lexical_overlap_score,
    parse_embedding_vector,
)
from services.document_processor.service import DocumentProcessor

router = APIRouter(prefix="/v1/chat", tags=["chat"], dependencies=[Depends(require_api_key)])
_repository = InMemoryChatRepository()
_FINISH_RESPONSES = {"finish", "no", "nope", "done", "exit", "quit", "stop"}
_API_VERSION = get_api_version()
_CORE_VERSION = get_core_version()
_LOGGER = logging.getLogger(__name__)
_LAWYER_OUTPUT_VALIDATOR = AILawyerOutputMessageValidationAgent()
_STREAM_KEEPALIVE_SECONDS = 15.0
_STREAM_STATUS_SECONDS = 15.0
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOGO_SVG_PRIMARY = _REPO_ROOT / "corporate-web" / "assets" / "ai-log.svg"
_LOGO_SVG_FALLBACK = _REPO_ROOT / "corporate-web" / "assets" / "aj-logo.svg"
_WINDOWS_FONT_DIR = Path("C:/Windows/Fonts")
_REPORTLAB_FONT_DIR = Path(str(canvas.__file__)).resolve().parents[1] / "fonts"
_LINUX_DEJAVU_FONT_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
)
_LINUX_LIBERATION_FONT_DIRS = (
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/liberation2"),
)
_REGISTERED_PDF_FONT_FAMILIES: set[str] = set()
DOCUMENT_SHOW_DISCLAIMER = 50.0


@dataclass(frozen=True)
class _DocumentExportAsset:
    filename: str
    title: str
    lines: list[str]
    disclaimer: tuple[str, str, str] | None = None
    use_corporate_template: bool = False


@dataclass(frozen=True)
class _GeneratedCaseDocumentDraft:
    filename: str
    body: str


@dataclass(frozen=True)
class _TechnicalPayloadAsset:
    content: str
    extension: str
    start_index: int
    end_index: int


class DocumentExportOption(BaseModel):
    index: int
    filename: str
    title: str


class DocumentExportOptionsResponse(BaseModel):
    documents: list[DocumentExportOption]


class SendSessionDocumentsEmailRequest(BaseModel):
    user_id: str | None = None
    recipient: str | None = None
    confirmed: bool = False


class SendSessionDocumentsEmailResponse(BaseModel):
    needs_confirmation: bool
    recipient: str
    message: str
    email_id: str | None = None
    attachment_count: int = 0


class CreateSessionRequest(BaseModel):
    user_id: Optional[UUID] = None
    case_id: str | None = None
    country: str = "SK"
    language: str | None = None
    discussion_type: Literal["advice", "court"] = "advice"
    model_profile_id: str | None = None


class CreateMessageRequest(BaseModel):
    session_id: UUID
    role: MessageRole
    content: str


class ReplyRequest(BaseModel):
    content: str
    user_id: UUID | None = None
    user_email: str | None = None
    model_profile_id: str | None = None


class InputDocument(BaseModel):
    doc_id: str = Field(default="doc")
    path: str
    content: str


def _get_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


def _case_write_block_detail(store: Any, *, case_id: str, user_id: str) -> dict[str, object] | None:
    detail_getter = getattr(store, "get_case_write_block_detail", None)
    if callable(detail_getter):
        block = detail_getter(case_id=case_id, user_id=user_id)
        if block is not None:
            to_api_detail = getattr(block, "to_api_detail", None)
            return to_api_detail() if callable(to_api_detail) else {"message": str(block)}
        return None

    reason = store.get_case_write_block_reason(case_id=case_id, user_id=user_id)
    return {"message": reason} if reason is not None else None


def _ensure_case_write_access_for_session(session: Session) -> None:
    case_id = (session.case_id or "").strip()
    if not case_id:
        return
    store = _get_store()
    try:
        case = store.get_case(case_id=case_id)
        user_id = str(session.user_id) if session.user_id else case.user_id
        detail = _case_write_block_detail(store, case_id=case_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if detail is not None:
        raise HTTPException(status_code=403, detail=detail)


def _persist_case_message_if_needed(*, session: Session, role: str, content: str, agent_name: str | None = None) -> None:
    case_id = session.case_id
    if case_id is None or not case_id.strip():
        return
    store = _get_store()
    if role.strip().lower() == "assistant":
        content = _user_visible_text(content)
    store.add_case_message(case_id=case_id, role=role, content=content, agent_name=agent_name)


def _record_case_ai_model_audit(
    *,
    session: Session,
    question: Message,
    answer: Message,
    task_type: str,
    source: str,
    model_used: bool,
    route: RoutedLLMClient | None = None,
) -> None:
    case_id = (session.case_id or "").strip()
    if not case_id:
        return
    question_text = _user_visible_text(question.content)
    answer_text = _user_visible_text(answer.content)
    provider, model, route_type, subscription_id, plan_code, fallback_reason = _resolve_audit_model_identity(
        model_used=model_used,
        route=route,
    )
    try:
        store = _get_store()
        user_id = str(session.user_id) if session.user_id else ""
        if not user_id:
            try:
                user_id = store.get_case(case_id=case_id).user_id
            except KeyError:
                user_id = ""
        store.record_ai_model_usage(
            provider=provider,
            model=model,
            route_type=route_type,
            input_tokens=_estimate_audit_tokens(question_text),
            output_tokens=_estimate_audit_tokens(answer_text),
            case_id=case_id,
            user_id=user_id,
            subscription_id=subscription_id,
            plan_code=plan_code,
            task_type=task_type,
            session_id=str(session.id),
            question_id=str(question.id),
            question_text=question_text,
            question_sha256=hashlib.sha256(question_text.strip().encode("utf-8")).hexdigest()
            if question_text.strip()
            else "",
            answer_id=str(answer.id),
            audit_metadata={
                "source": source,
                "agent_name": answer.agent_name or "",
                "model_used": model_used,
                "model_profile_id": route.route.model_profile.model_profile_id
                if route and route.route.model_profile
                else "",
                "provider_code": route.route.provider.provider_code
                if route and route.route.provider
                else "",
                "route_reason": route.route.reason if route else "",
                "token_counting": "estimated_characters_div_4",
                "full_question_source": "case_history",
            },
            fallback_reason=fallback_reason,
        )
    except Exception:
        _LOGGER.warning(
            "Could not record case AI model audit entry",
            extra={"case_id": case_id, "session_id": str(session.id), "task_type": task_type},
            exc_info=True,
        )


def _resolve_audit_model_identity(
    *,
    model_used: bool,
    route: RoutedLLMClient | None = None,
) -> tuple[str, str, str, str, str, str]:
    if not model_used:
        return "jurisdigta_rules", "deterministic_case_logic", "deterministic", "", "", ""
    if route is None:
        return "unresolved_model_route", "unresolved_model_route", "unresolved", "", "", "missing_route_context"
    return (
        route.provider,
        route.model,
        route.route_type,
        route.subscription_id,
        route.plan_code,
        route.fallback_reason,
    )


def _resolve_session_llm_route(
    *,
    session: Session,
    task_type: str,
    request_user_id: str | None = None,
    request_user_email: str | None = None,
    selected_model_profile_id: str | None = None,
) -> RoutedLLMClient:
    store = _get_store()
    user_id = (request_user_id or "").strip()
    if not user_id:
        user_id = str(session.user_id) if session.user_id else ""
    if not user_id and session.case_id:
        try:
            user_id = store.get_case(case_id=session.case_id).user_id
        except KeyError:
            user_id = ""
    user_email = (request_user_email or "").strip().lower()
    try:
        normalized_selected_profile_id = (
            selected_model_profile_id or session.selected_model_profile_id or ""
        ).strip()
        if normalized_selected_profile_id:
            return get_routed_llm_client(
                store=store,
                user_id=user_id,
                user_email=user_email,
                task_type=task_type,
                selected_model_profile_id=normalized_selected_profile_id,
            )
        return get_routed_llm_client(
            store=store,
            user_id=user_id,
            task_type=task_type,
        )
    except ModelRouteUnavailable as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _estimate_audit_tokens(text: str) -> int:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return 0
    return max(1, (len(normalized) + 3) // 4)


def _persist_session_history_document_if_needed(*, session: Session, session_id: UUID) -> None:
    case_id = (session.case_id or "").strip()
    if not case_id:
        return
    messages = _repository.list_messages(session_id)
    if not messages:
        return
    lines: list[str] = []
    for message in messages:
        role = message.role.value.upper()
        visible_message = _message_for_user(message) if message.role == MessageRole.ASSISTANT else message
        content = visible_message.content.strip()
        if not content:
            continue
        line = f"{role}: {content}"
        if message.agent_name:
            line = f"{line} (agent={message.agent_name})"
        lines.append(line)
    if not lines:
        return
    transcript = "\n".join(lines)
    store = _get_store()
    add_session_history_document = getattr(store, "add_case_session_history_document", None)
    if callable(add_session_history_document):
        doc_id = add_session_history_document(
            case_id=case_id,
            session_id=str(session_id),
            content=transcript,
            uploaded_by_user_id=str(session.user_id) if session.user_id else None,
        )
        get_case_document = getattr(store, "get_case_document", None)
        if callable(get_case_document):
            _process_case_documents_if_needed(
                store=store,
                documents=[get_case_document(case_id=case_id, doc_id=doc_id)],
            )


def _document_processor_mode() -> str:
    value = os.getenv(
        "DOCUMENT_PROCESSOR_OPTION",
        os.getenv("DOCUMENT_PROCESSOR", "api"),
    ).strip().lower()
    if value == "azure":
        return "azure"
    return "api"


def _process_case_documents_if_needed(
    *,
    store: ApiDatabaseStore,
    documents: list[CaseDocument],
) -> None:
    if not documents or _document_processor_mode() == "azure":
        return
    DocumentProcessor(store).process_documents(documents)


def _persist_inline_case_documents_if_needed(
    *,
    session: Session,
    documents: list[InputDocument],
) -> None:
    case_id = (session.case_id or "").strip()
    if not case_id or not documents:
        return
    store = _get_store()
    persisted_documents: list[CaseDocument] = []
    for index, document in enumerate(documents, start=1):
        filename = Path(document.path).name.strip() or f"attachment-{index}.txt"
        doc_id = store.add_case_text_document(
            case_id=case_id,
            original_filename=filename,
            content=document.content,
            uploaded_by_user_id=str(session.user_id) if session.user_id else None,
        )
        persisted_documents.append(store.get_case_document(case_id=case_id, doc_id=doc_id))
    _process_case_documents_if_needed(store=store, documents=persisted_documents)


def _read_case_communication_content(*, store: ApiDatabaseStore, communication: Any) -> str:
    content = str(getattr(communication, "summary", ""))
    transcript_uri = getattr(communication, "transcript_uri", None)
    if not isinstance(transcript_uri, str) or not transcript_uri.strip():
        return content
    try:
        return str(store.read_storage_text(storage_uri=transcript_uri))
    except FileNotFoundError:
        _LOGGER.info(
            "Case communication transcript not found; using summary fallback",
            extra={
                "case_id": getattr(communication, "case_id", None),
                "communication_id": getattr(communication, "communication_id", None),
                "transcript_uri": transcript_uri,
            },
        )
        return content
    except Exception:
        _LOGGER.warning(
            "Falling back to case communication summary because transcript could not be read",
            extra={
                "case_id": getattr(communication, "case_id", None),
                "communication_id": getattr(communication, "communication_id", None),
                "transcript_uri": transcript_uri,
            },
            exc_info=True,
        )
        return content


def _parse_case_history_entry(*, store: ApiDatabaseStore, communication: Any) -> tuple[MessageRole, str, str | None]:
    content = _read_case_communication_content(store=store, communication=communication)
    role = MessageRole.ASSISTANT
    agent_name: str | None = None
    normalized = content.strip()
    upper = normalized.upper()
    if upper.startswith("USER:"):
        role = MessageRole.USER
        normalized = normalized[5:].strip()
    elif upper.startswith("ASSISTANT:"):
        role = MessageRole.ASSISTANT
        normalized = normalized[10:].strip()
    elif upper.startswith("SYSTEM:"):
        role = MessageRole.SYSTEM
        normalized = normalized[7:].strip()
    if normalized.endswith(")") and "(agent=" in normalized:
        prefix, _, suffix = normalized.rpartition("(agent=")
        agent_name = suffix[:-1].strip() or None
        normalized = prefix.strip()
    return role, normalized, agent_name


def _load_case_documents_for_llm(
    *,
    case_id: str,
    query: str,
) -> tuple[list[CoreDocument], list[str], list[str]]:
    store = _get_store()
    processed_documents: list[CoreDocument] = []
    processed_names: list[str] = []
    unprocessed_names: list[str] = []

    list_case_documents = getattr(store, "list_case_documents", None)
    list_case_document_contents = getattr(store, "list_case_document_contents", None)
    list_case_document_chunks = getattr(store, "list_case_document_chunks", None)
    if not callable(list_case_documents) or not callable(list_case_document_contents):
        return processed_documents, processed_names, unprocessed_names

    contents_by_doc_id = {
        doc_id: (name, text, vector)
        for doc_id, name, text, _vector in list_case_document_contents(case_id=case_id)
        for vector in [_vector]
    }
    processed_entries: list[tuple[str, str, str, str]] = []
    processed_names_by_doc_id: dict[str, str] = {}
    for document in list_case_documents(case_id=case_id):
        if document.kind not in {'uploaded', 'chat_attachment', 'session_history', 'generated_document'}:
            continue
        if document.processing_status == 'processed' and document.doc_id in contents_by_doc_id:
            name, text, vector = contents_by_doc_id[document.doc_id]
            processed_names.append(name)
            processed_names_by_doc_id[document.doc_id] = name
            processed_entries.append((document.doc_id, name, text, vector))
        else:
            unprocessed_names.append(document.original_filename)
    selected_entries = []
    if callable(list_case_document_chunks):
        chunk_entries = [
            chunk
            for chunk in list_case_document_chunks(case_id=case_id)
            if chunk.doc_id in processed_names_by_doc_id
        ]
        selected_chunks = _select_relevant_case_document_chunks(
            query=query,
            chunk_entries=chunk_entries,
        )
        if selected_chunks:
            processed_documents = [
                CoreDocument(
                    doc_id=chunk.doc_id,
                    path=f"{processed_names_by_doc_id[chunk.doc_id]}#chunk-{chunk.chunk_index + 1}",
                    content=chunk.chunk_text,
                )
                for chunk in selected_chunks
            ]
            return processed_documents, processed_names, unprocessed_names
    selected_entries = _select_relevant_case_documents(
        query=query,
        processed_entries=processed_entries,
    )
    processed_documents = [
        CoreDocument(doc_id=doc_id, path=name, content=text)
        for doc_id, name, text, _vector in selected_entries
    ]
    return processed_documents, processed_names, unprocessed_names


def _select_relevant_case_documents(
    *,
    query: str,
    processed_entries: list[tuple[str, str, str, str]],
    limit: int = 4,
) -> list[tuple[str, str, str, str]]:
    if len(processed_entries) <= limit or _requests_all_processed_documents(query):
        return processed_entries
    normalized_query = query.strip()
    if not normalized_query:
        return processed_entries[:limit]

    scored: list[tuple[float, int, tuple[str, str, str, str]]] = []
    for index, entry in enumerate(processed_entries):
        _doc_id, _name, text, _raw_vector = entry
        lexical_score = lexical_overlap_score(normalized_query, text)
        score = lexical_score * 10.0
        scored.append((score, index, entry))
    ranked = sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)
    selected = [entry for score, _index, entry in ranked if score > 0][:limit]
    if selected:
        return selected
    return processed_entries[:limit]


def _select_relevant_case_document_chunks(
    *,
    query: str,
    chunk_entries: list[Any],
    limit: int = 6,
    per_document_limit: int = 2,
) -> list[Any]:
    if not chunk_entries:
        return []
    if _requests_all_processed_documents(query):
        return _select_all_case_document_chunks(
            chunk_entries,
            limit=max(limit, 8),
            per_document_limit=per_document_limit,
        )

    normalized_query = query.strip()
    if not normalized_query:
        return _limit_chunks_per_document(
            chunk_entries,
            limit=limit,
            per_document_limit=per_document_limit,
        )

    query_vector: list[float] = []
    query_model_name = ""
    try:
        embedding_client = get_embedding_client()
        query_batch = embedding_client.embed_texts([normalized_query])
        query_vector = query_batch.vectors[0]
        query_model_name = query_batch.model_name
    except Exception:
        _LOGGER.warning("Falling back to lexical-only case document chunk retrieval", exc_info=True)

    scored: list[tuple[float, int, Any]] = []
    for index, chunk in enumerate(chunk_entries):
        lexical_score = lexical_overlap_score(normalized_query, chunk.chunk_text)
        vector_score = 0.0
        if (
            query_vector
            and chunk.embedding_model == query_model_name
            and chunk.embedding_dimensions == len(query_vector)
        ):
            vector_score = cosine_similarity(
                query_vector,
                parse_embedding_vector(chunk.embedding_vector),
            )
        score = (lexical_score * 10.0) + vector_score
        scored.append((score, index, chunk))
    ranked = [entry for score, _index, entry in sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True) if score > 0]
    if ranked:
        return _limit_chunks_per_document(
            ranked,
            limit=limit,
            per_document_limit=per_document_limit,
        )
    return _limit_chunks_per_document(
        chunk_entries,
        limit=limit,
        per_document_limit=per_document_limit,
    )


def _limit_chunks_per_document(
    chunk_entries: list[Any],
    *,
    limit: int,
    per_document_limit: int,
) -> list[Any]:
    selected: list[Any] = []
    counts_by_doc_id: dict[str, int] = {}
    for chunk in chunk_entries:
        count = counts_by_doc_id.get(chunk.doc_id, 0)
        if count >= per_document_limit:
            continue
        selected.append(chunk)
        counts_by_doc_id[chunk.doc_id] = count + 1
        if len(selected) >= limit:
            break
    return selected


def _select_all_case_document_chunks(
    chunk_entries: list[Any],
    *,
    limit: int,
    per_document_limit: int,
) -> list[Any]:
    if not chunk_entries:
        return []
    selected: list[Any] = []
    counts_by_doc_id: dict[str, int] = {}
    for chunk in chunk_entries:
        if chunk.doc_id in counts_by_doc_id:
            continue
        selected.append(chunk)
        counts_by_doc_id[chunk.doc_id] = 1
        if len(selected) >= limit:
            return selected
    if len(selected) == len(chunk_entries):
        return selected
    for chunk in chunk_entries:
        count = counts_by_doc_id.get(chunk.doc_id, 0)
        if count >= per_document_limit:
            continue
        if count == 0:
            continue
        selected.append(chunk)
        counts_by_doc_id[chunk.doc_id] = count + 1
        if len(selected) >= limit:
            break
    return selected


def _requests_all_processed_documents(query: str) -> bool:
    normalized = " ".join(query.lower().split())
    phrases = (
        "all uploaded documents",
        "all documents in this case",
        "summarize all uploaded documents",
        "analyze all uploaded documents",
        "vsetky nahrane dokumenty",
        "vsetky dokumenty v tomto pripade",
        "alle hochgeladenen dokumente",
        "alle dokumente in diesem fall",
    )
    return any(phrase in normalized for phrase in phrases)


def _prepend_document_status_note(*, reply: str, processed_names: list[str], unprocessed_names: list[str]) -> str:
    if not processed_names and not unprocessed_names:
        return reply
    lines: list[str] = []
    if processed_names:
        _LOGGER.info("Processed documents available for search: %s", ", ".join(processed_names))
    if unprocessed_names:
        _LOGGER.info("Document processing still running: %s", ", ".join(unprocessed_names))
        lines.append("Spracovanie stále prebieha....")
    note = '\n'.join(lines).strip()
    if not note:
        return reply
    if not reply.strip():
        return note
    return f"{note}\n\n{reply}"


def _bootstrap_case_history_if_needed(*, session: Session) -> None:
    case_id = (session.case_id or "").strip()
    if not case_id:
        return
    store = _get_store()
    history = store.list_case_communications(case_id=case_id)
    for item in reversed(history):
        role, content, agent_name = _parse_case_history_entry(
            store=store,
            communication=item,
        )
        _repository.add_message(
            Message(
                session_id=session.id,
                role=role,
                content=content,
                agent_name=agent_name,
            )
        )


def _message_payload(message: Message) -> dict[str, object]:
    visible_message = _message_for_user(message)
    payload: dict[str, object] = {
        "id": str(visible_message.id),
        "session_id": str(visible_message.session_id),
        "role": visible_message.role.value,
        "agent_name": visible_message.agent_name,
        "content": visible_message.content,
        "created_at": visible_message.created_at.isoformat(),
    }
    generated_document_urls = list(
        dict.fromkeys(
            match.group(0).rstrip(".,;)")
            for match in re.finditer(
                r"/v1/cases/[^/\s?]+/documents/[^/\s?]+(?:\?[^\s]+)?",
                message.content,
            )
        )
    )
    if generated_document_urls:
        payload["generated_document_urls"] = generated_document_urls
    return payload


def _build_case_memory_refresh_note(prior_messages: list[Message]) -> str:
    answered_questions = _case_memory_answered_questions(prior_messages)
    rental_address = _known_rental_property_address(prior_messages)
    party_memory = _known_rental_parties(prior_messages)
    document_ready = _case_memory_has_prepared_document(prior_messages)
    if not answered_questions and not rental_address and not party_memory and not document_ready:
        return ""
    lines = [
        "CASE MEMORY REFRESH:\n"
        "- Review the full case conversation above before asking a clarification question."
    ]
    if document_ready:
        lines.append("- A document draft was already prepared earlier in this case; do not restart intake.")
    if answered_questions:
        lines.append("- Previously answered case questions:")
        for question, answer in answered_questions[-8:]:
            lines.append(f"  - Q: {question} | A: {answer}")
    if rental_address:
        lines.append(f"- Known rental property address from prior question/answer: {rental_address}")
    if party_memory.get("prenajimatel"):
        lines.append(f"- Known landlord/prenajimatel: {party_memory['prenajimatel']}")
    if party_memory.get("najomca"):
        lines.append(f"- Known tenant/najomca: {party_memory['najomca']}")
    lines.extend(
        [
            "- Do not ask again for facts that are already present in the case memory.",
            "- If a remembered fact is ambiguous, ask only about the ambiguity.",
        ]
    )
    return "\n".join(lines)


def _apply_case_memory_to_lawyer_content(*, content: str, prior_messages: list[Message]) -> str:
    answered_questions = _case_memory_answered_questions(prior_messages)
    repeated_answers = _matching_answered_questions(
        content=content,
        answered_questions=answered_questions,
    )
    rental_address = _known_rental_property_address(prior_messages)
    party_memory = _known_rental_parties(prior_messages)
    document_ready = _case_memory_has_prepared_document(prior_messages)
    has_general_repeat = bool(repeated_answers)
    has_address_repeat = bool(rental_address and _asks_rental_property_address(content))
    has_party_repeat = bool((party_memory or document_ready) and _asks_rental_parties(content))
    if not has_general_repeat and not has_address_repeat and not has_party_repeat:
        return content
    visible_text = _user_visible_text(content)
    kept_lines = [
        line
        for line in visible_text.splitlines()
        if not _line_repeats_answered_question(line, answered_questions)
        and not _asks_rental_property_address(line)
        and not _asks_rental_parties(line)
    ]
    reminders: list[str] = []
    if has_general_repeat:
        for _question, answer in repeated_answers[:3]:
            reminders.append(f"Jednu z opakovanych otazok uz mam zodpovedanu: {answer}.")
    if has_address_repeat:
        reminders.append(
            "Adresu prenajimanej nehnutelnosti mam z predchadzajucej diskusie: "
            f"{rental_address}."
        )
    if has_party_repeat:
        party_parts = []
        if party_memory.get("prenajimatel"):
            party_parts.append(f"prenajimatel: {party_memory['prenajimatel']}")
        if party_memory.get("najomca"):
            party_parts.append(f"najomca: {party_memory['najomca']}")
        party_text = ", ".join(party_parts)
        if party_text:
            reminders.append(f"Zmluvne strany mam z predchadzajucej diskusie: {party_text}.")
        else:
            reminders.append("Dokument bol v tejto veci uz pripraveny, preto nepokracujem opakovanim intake otazok.")
    reminder = " ".join([*reminders, "Pokracujem bez opatovneho pytania tej istej otazky."])
    if any(line.strip() for line in kept_lines):
        visible = "\n".join([reminder, *kept_lines]).strip()
    else:
        visible = reminder
    case_update = _extract_case_update(content)
    if case_update is not None:
        case_update = _remove_known_case_memory_open_questions(
            case_update,
            answered_questions=answered_questions,
            remove_address=has_address_repeat,
            remove_parties=has_party_repeat,
        )
    return _compose_assistant_content(visible_text=visible, case_update=case_update)


def _case_memory_answered_questions(messages: list[Message]) -> list[tuple[str, str]]:
    answered: list[tuple[str, str]] = []
    pending_question = ""
    for message in messages:
        visible_content = _user_visible_text(message.content)
        if message.role == MessageRole.ASSISTANT:
            questions = _extract_case_memory_questions(visible_content)
            pending_question = questions[-1] if questions else ""
            continue
        if message.role != MessageRole.USER or not pending_question:
            continue
        answer = _clean_case_memory_answer(visible_content)
        if answer:
            answered.append((pending_question, answer))
        pending_question = ""
    return answered


def _extract_case_memory_questions(content: str) -> list[str]:
    questions: list[str] = []
    for raw_line in _user_visible_text(content).splitlines():
        line = _clean_case_memory_question(raw_line)
        if not line or "?" not in line:
            continue
        if _is_technical_or_confirmation_question(line):
            continue
        questions.append(line)
    return questions


def _clean_case_memory_question(content: str) -> str:
    line = re.sub(r"^[\-\*\d\.\)\s]+", "", " ".join(content.split()))
    line = re.sub(r"\*\*", "", line).strip()
    if not line:
        return ""
    question_index = line.find("?")
    if question_index >= 0:
        line = line[: question_index + 1]
    return line[:240]


def _is_technical_or_confirmation_question(question: str) -> bool:
    normalized = _canonicalize_document_text(question)
    ignored_markers = (
        "chcete poslat",
        "potvrdte odoslanie",
        "confirm sending",
        "chcete aby som pripravil",
        "mam pripravit",
        "pdf",
        "download",
        "stiahnutie",
    )
    return any(marker in normalized for marker in ignored_markers)


def _matching_answered_questions(
    *, content: str, answered_questions: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    current_questions = _extract_case_memory_questions(content)
    matches: list[tuple[str, str]] = []
    for current_question in current_questions:
        for answered_question, answer in answered_questions:
            if _questions_match(current_question, answered_question):
                matches.append((answered_question, answer))
                break
    return matches


def _line_repeats_answered_question(line: str, answered_questions: list[tuple[str, str]]) -> bool:
    question = _clean_case_memory_question(line)
    if not question or "?" not in question:
        return False
    return any(_questions_match(question, answered_question) for answered_question, _answer in answered_questions)


def _questions_match(left: str, right: str) -> bool:
    left_normalized = _canonicalize_document_text(left).rstrip("?")
    right_normalized = _canonicalize_document_text(right).rstrip("?")
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True
    left_tokens = _case_memory_question_tokens(left_normalized)
    right_tokens = _case_memory_question_tokens(right_normalized)
    if not left_tokens or not right_tokens:
        return False
    intersection = left_tokens & right_tokens
    overlap = len(intersection) / min(len(left_tokens), len(right_tokens))
    jaccard = len(intersection) / len(left_tokens | right_tokens)
    return overlap >= 0.8 or jaccard >= 0.72


def _case_memory_question_tokens(normalized_question: str) -> set[str]:
    stopwords = {
        "a",
        "aby",
        "ake",
        "aka",
        "aky",
        "ale",
        "bude",
        "budu",
        "este",
        "je",
        "kto",
        "mi",
        "mohol",
        "mohla",
        "na",
        "niekolko",
        "potrebujem",
        "pre",
        "prosim",
        "spravne",
        "som",
        "zmluvu",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized_question)
        if len(token) > 2 and token not in stopwords
    }


def _known_rental_property_address(messages: list[Message]) -> str:
    known_address = ""
    awaiting_address_answer = False
    for message in messages:
        visible_content = _user_visible_text(message.content)
        if message.role == MessageRole.ASSISTANT:
            awaiting_address_answer = _asks_rental_property_address(visible_content)
            continue
        if message.role != MessageRole.USER:
            continue
        labeled_address = _extract_rental_property_address_from_text(visible_content)
        if labeled_address:
            known_address = labeled_address
            awaiting_address_answer = False
            continue
        if awaiting_address_answer:
            answer = _clean_case_memory_answer(visible_content)
            if answer:
                known_address = answer
            awaiting_address_answer = False
    return known_address


def _known_rental_parties(messages: list[Message]) -> dict[str, str]:
    known: dict[str, str] = {}
    awaiting_party_answer = False
    for message in messages:
        visible_content = _user_visible_text(message.content)
        extracted = _extract_rental_parties_from_text(visible_content)
        if extracted:
            known.update(extracted)
        if message.role == MessageRole.ASSISTANT:
            awaiting_party_answer = _asks_rental_parties(visible_content)
            continue
        if message.role != MessageRole.USER:
            continue
        if awaiting_party_answer:
            known.update(extracted)
            awaiting_party_answer = False
    return {key: value for key, value in known.items() if value}


def _extract_rental_parties_from_text(content: str) -> dict[str, str]:
    parties: dict[str, str] = {}
    for line in content.splitlines():
        cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", _repair_common_mojibake(line).strip())
        cleaned = re.sub(r"\*\*", "", cleaned).strip()
        if not cleaned:
            continue
        landlord = re.search(
            r"\b(?:prenaj[ií]matel|prenaj[ií]mateľ|landlord|lessor)\s*(?:je|:|-)?\s*(.+?)(?=\s*(?:[,;]|\ba\b)\s*(?:n[aá]jomca|podn[aá]jomnik|podn[aá]jomník|tenant|subtenant)\b|$)",
            cleaned,
            flags=re.IGNORECASE,
        )
        tenant = re.search(
            r"\b(?:n[aá]jomca|podn[aá]jomnik|podn[aá]jomník|tenant|subtenant)\s*(?:je|:|-)?\s*(.+)$",
            cleaned,
            flags=re.IGNORECASE,
        )
        if landlord is not None:
            value = _clean_case_memory_answer(landlord.group(1))
            if value and not _is_missing_document_fact(value):
                parties["prenajimatel"] = value
        if tenant is not None:
            value = _clean_case_memory_answer(tenant.group(1))
            if value and not _is_missing_document_fact(value):
                parties["najomca"] = value
    return parties


def _case_memory_has_prepared_document(messages: list[Message]) -> bool:
    if _document_export_ready(messages):
        return True
    ready_markers = (
        "dokument je pripraveny",
        "dokument je pripraven",
        "dokumenty su pripravene",
        "draft is ready",
        "ready for download",
        "navrh zmluvy",
        "najomna zmluva",
        "zmluva o najme",
    )
    for message in messages:
        if message.role != MessageRole.ASSISTANT:
            continue
        normalized = _canonicalize_document_text(_user_visible_text(message.content))
        if any(marker in normalized for marker in ready_markers):
            return True
    return False


def _extract_rental_property_address_from_text(content: str) -> str:
    for line in content.splitlines():
        match = re.search(
            r"\b(?:adresa\s+)?(?:prenajimanej\s+)?(?:nehnutelnosti|bytu|predmetu\s+najmu|predmetu\s+prenajmu)\s*[:\-]\s*(.+)$",
            _canonicalize_document_text(line),
        )
        if match is None:
            continue
        value = _clean_case_memory_answer(match.group(1))
        if value:
            return value
    return ""


def _clean_case_memory_answer(content: str) -> str:
    single_line = " ".join(content.split())
    single_line = re.sub(r"^(?:odpoved|answer)\s*[:\-]\s*", "", single_line, flags=re.IGNORECASE).strip()
    if not single_line or "?" in single_line:
        return ""
    if _canonicalize_document_text(single_line) in {"ano", "nie", "yes", "no", "ok", "okay"}:
        return ""
    return single_line[:240]


def _asks_rental_property_address(content: str) -> bool:
    normalized = _canonicalize_document_text(_user_visible_text(content))
    if "adresa" not in normalized:
        return False
    if "prenajimanej nehnutelnosti" in normalized:
        return True
    return "nehnutelnosti" in normalized and any(
        marker in normalized for marker in ("aka je", "presna", "doplnte", "chyba")
    )


def _asks_rental_parties(content: str) -> bool:
    normalized = _canonicalize_document_text(_user_visible_text(content))
    has_landlord = "prenajimatel" in normalized or "landlord" in normalized or "lessor" in normalized
    has_tenant = "najomca" in normalized or "podnajomnik" in normalized or "tenant" in normalized
    if not has_landlord or not has_tenant:
        return False
    return any(marker in normalized for marker in ("kto", "bude", "doplnte", "chyba", "potrebujem"))


def _remove_known_case_memory_open_questions(
    case_update: dict[str, Any],
    *,
    answered_questions: list[tuple[str, str]],
    remove_address: bool,
    remove_parties: bool,
) -> dict[str, Any]:
    case_payload = case_update.get("case")
    if not isinstance(case_payload, dict):
        return case_update
    open_questions = case_payload.get("open_questions")
    if not isinstance(open_questions, list):
        return case_update
    case_payload["open_questions"] = [
        question
        for question in open_questions
        if not (
            _line_repeats_answered_question(str(question), answered_questions)
            or (remove_address and _asks_rental_property_address(str(question)))
            or (remove_parties and _asks_rental_parties(str(question)))
        )
    ]
    return case_update


def _assistant_requests_user_reply(content: str) -> bool:
    return "?" in _user_visible_text(content)


def _persist_direct_assistant_message(
    *,
    session_id: UUID,
    session: Session,
    content: str,
    agent_name: str,
    allow_document_generation: bool = True,
) -> Message:
    content = _validate_lawyer_output_message(session=session, content=content)
    content = _attach_technical_payload_to_case_if_needed(session=session, content=content)
    generated_doc_ids = (
        _persist_generated_case_document_if_needed(session=session, content=content)
        if allow_document_generation
        else []
    )
    content = _attach_generated_case_document_references(
        session=session,
        content=content,
        doc_ids=generated_doc_ids,
    )
    persisted_lawyer = _repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=content,
            agent_name=agent_name,
        )
    )
    _persist_case_message_if_needed(
        session=session,
        role="assistant",
        content=content,
        agent_name=agent_name,
    )
    return persisted_lawyer


def _validate_lawyer_output_message(*, session: Session, content: str) -> str:
    return _LAWYER_OUTPUT_VALIDATOR.validate(
        content=content,
        user_profile=_lawyer_output_user_profile_for_session(session),
    )


def _lawyer_output_user_profile_for_session(session: Session) -> LawyerOutputUserProfile | None:
    user = _document_user_profile_for_session(session)
    if user is None:
        return None
    return LawyerOutputUserProfile(
        has_full_name=bool(_user_profile_document_display_name(user)),
        has_address=bool(_user_profile_document_address(user)),
    )


def _build_signed_in_user_profile_prompt_note(session: Session) -> str:
    user = _document_user_profile_for_session(session)
    if user is None:
        return ""
    display_name = _user_profile_document_display_name(user)
    address_parts = _user_profile_document_address(user)
    if not display_name and not address_parts:
        return ""

    lines = [
        "SIGNED-IN USER PROFILE DEFAULTS:",
        "- Use these profile values as the client/default party details when the user asks "
        "for a legal document or when the response needs the user's name/address.",
        "- Do not ask again for a field listed here. Ask only for missing profile fields or "
        "opponent/recipient details.",
        "- Do not output placeholders such as [nebolo poskytnute] or [Vase meno a adresa] "
        "for fields listed here.",
    ]
    if display_name:
        lines.append(f"- Client full name: {display_name}")
    if address_parts:
        lines.append(f"- Client address: {', '.join(address_parts)}")
    return "\n".join(lines)


_SLOVAK_MONTHS_GENITIVE = {
    1: "januara",
    2: "februara",
    3: "marca",
    4: "aprila",
    5: "maja",
    6: "juna",
    7: "jula",
    8: "augusta",
    9: "septembra",
    10: "oktobra",
    11: "novembra",
    12: "decembra",
}


def _build_current_date_prompt_note(*, today: date | None = None) -> str:
    current_date = today or date.today()
    numeric_display_date = f"{current_date.day}.{current_date.month}.{current_date.year}"
    slovak_display_date = (
        f"{current_date.day}. {_SLOVAK_MONTHS_GENITIVE[current_date.month]} {current_date.year}"
    )
    return "\n".join(
        [
            "CURRENT DATE CONTEXT:",
            (
                f"- Today's date is {current_date.isoformat()} "
                f"({numeric_display_date}; {slovak_display_date})."
            ),
            (
                "- If the user asks for today's/current/date-of-signature date in a document, "
                "use this date."
            ),
            "- Do not invent, infer from model training data, or reuse old example dates.",
        ]
    )


def _build_uploaded_document_contract_confirmation_note(
    *,
    content: str,
    documents: list[CoreDocument],
) -> str:
    if not documents or not _is_contract_preparation_request(content):
        return ""
    return (
        "UPLOADED DOCUMENT CONTRACT INTAKE MODE:\n"
        "- The user is asking to prepare a new contract/agreement and uploaded documents are available.\n"
        "- Before asking generic intake questions or drafting the final contract, review every available uploaded "
        "document provided in this turn or stored in the case.\n"
        "- Extract all available contract data from the uploaded documents and the conversation first, including "
        "parties, identification numbers, addresses, subject matter, property or asset details, dates, price/rent, "
        "payment terms, obligations, attachments, governing law, and any missing or uncertain fields.\n"
        "- Do not ask for a fact that is already available in the uploaded documents.\n"
        "- In the user-facing reply, present a concise grouped list headed 'Udaje, ktore som nasiel v dokumentoch' "
        "or the same meaning in the user's language. Mark uncertain facts as uncertain and mention the source "
        "document when useful.\n"
        "- After the extracted-data list, ask exactly one confirmation question asking whether the user agrees "
        "with these data for the new contract or wants to change/add anything.\n"
        "- For Slovak replies, use this confirmation wording unless the conversation clearly uses another language: "
        "'Suhlasite, aby som zmluvu pripravil z tychto udajov, alebo chcete niektory udaj zmenit/doplnit?'\n"
        "- Do not generate or export the final contract until the user confirms or corrects the extracted data."
    )


def _build_legal_document_preparation_policy_note(*, content: str, country: str) -> str:
    if not _is_legal_document_preparation_request(content):
        return ""

    lines = [
        "LEGAL DOCUMENT PREPARATION MODE:",
        "- Prepare legally structured documents according to the applicable law and the requested jurisdiction.",
        "- If the user asks for the same document in multiple languages, multiple versions, or variants, prepare each "
        "language/version/variant as a separate final document, not as sections combined into one document.",
        "- If the user provides a table/CSV/list with multiple people, companies, addresses, recipients, attorneys-in-fact, "
        "principals, or other parties, prepare one separate final document per row/person/entity. Example: a power of "
        "attorney request with 100 attorneys-in-fact in a CSV requires 100 separate PDF documents.",
        "- Do not mix Slovak and English final legal texts in one PDF unless the user explicitly requests one bilingual "
        "comparison document instead of separate documents.",
        "- For each final document, keep the party data scoped to that document only.",
        "- When using CASE_UPDATE_JSON, represent each separate final document as its own case.documents entry with a "
        "clear filename/path so export can create separate PDFs or a ZIP package.",
        "- Before drafting a legal document, check the managed document-template catalog for the detected document type.",
    ]

    template_note = _legal_document_template_source_note(content=content, country=country)
    if template_note:
        lines.extend(template_note)
    else:
        lines.extend(
            [
                "- No matching managed template was found for this request.",
                "- Use AIWebSearchAgent (AIInternetSearchAgent alias, if configured) to locate a reliable current legal "
                "document body or official/professional template before drafting.",
                "- In the user-facing response, include the URL/title/location from which the internet template/body was "
                "downloaded or derived.",
                "- If no reliable source can be found, state that clearly and ask for confirmation before drafting from "
                "general legal knowledge.",
            ]
        )
    return "\n".join(lines)


def _legal_document_template_source_note(*, content: str, country: str) -> list[str]:
    try:
        score, template = get_document_template_store().find_best_match(
            request_text=content,
            country=(country or "SK").strip() or "SK",
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Document-template lookup failed for legal document request | reason=%s", exc)
        return [
            "- Managed document-template lookup failed for this request.",
            "- Use AIWebSearchAgent (AIInternetSearchAgent alias, if configured) to locate a reliable current legal "
            "document body or official/professional template before drafting.",
            "- In the user-facing response, include the URL/title/location from which the internet template/body was "
            "downloaded or derived.",
        ]
    if score <= 0 or template is None:
        return []

    lines = [
        f"- Managed template match: {template.title} ({template.template_key}), score {score}.",
        f"- Managed template source location: {template.source_url}.",
        "- Mention this managed template source location in the user-facing response when it influenced the draft.",
    ]
    if template.body.strip():
        lines.append(
            "- Use the managed template body as the primary drafting structure and replace all placeholders with "
            "confirmed data."
        )
    else:
        lines.extend(
            [
                "- The managed template record has metadata/source only and no stored body.",
                "- Use AIWebSearchAgent (AIInternetSearchAgent alias, if configured) to fetch or verify the document body "
                "from that source or another reliable current source before drafting.",
                "- In the user-facing response, include the URL/title/location from which the internet template/body was "
                "downloaded or derived.",
            ]
        )
    return lines


def _is_legal_document_preparation_request(content: str) -> bool:
    normalized = _canonicalize_document_text(content)
    document_markers = (
        "splnomocnen",
        "plna moc",
        "power of attorney",
        "zmluv",
        "contract",
        "agreement",
        "dohod",
        "potvrden",
        "vyhlasen",
        "navrh",
        "ziadost",
        "legal document",
        "pravny dokument",
        "dokument",
        "pdf",
    )
    preparation_markers = (
        "priprav",
        "vytvor",
        "vygeneruj",
        "napis",
        "spis",
        "vypracuj",
        "draft",
        "prepare",
        "create",
        "generate",
        "write",
        "new",
        "novu",
        "nova",
        "novy",
    )
    review_only_markers = (
        "skontrol",
        "posud",
        "zhrn",
        "summar",
        "review",
        "analyz",
    )
    if any(marker in normalized for marker in review_only_markers) and not any(
        marker in normalized for marker in preparation_markers
    ):
        return False
    return any(marker in normalized for marker in document_markers) and any(
        marker in normalized for marker in preparation_markers
    )


def _is_contract_preparation_request(content: str) -> bool:
    normalized = _canonicalize_document_text(content)
    contract_markers = (
        "zmluv",
        "contract",
        "agreement",
        "dohod",
    )
    preparation_markers = (
        "priprav",
        "vytvor",
        "vygeneruj",
        "napis",
        "spis",
        "draft",
        "prepare",
        "create",
        "generate",
        "write",
        "new",
        "novu",
        "nova",
        "novy",
    )
    return any(marker in normalized for marker in contract_markers) and any(
        marker in normalized for marker in preparation_markers
    )


def _run_direct_lawyer_turn(
    *,
    session_id: UUID,
    session: Session,
    content: str,
    request_user_id: str | None = None,
    request_user_email: str | None = None,
    supplemental_documents: list[CoreDocument] | None = None,
    processing_event_callback: Callable[[dict[str, object]], None] | None = None,
    user_message_callback: Callable[[Message], None] | None = None,
) -> tuple[Message, Message, str, list[dict[str, object]], RoutedLLMClient | None]:
    persisted_user = _repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content=content,
            agent_name="User",
        )
    )
    _persist_case_message_if_needed(session=session, role="user", content=content, agent_name="User")
    if user_message_callback is not None:
        user_message_callback(persisted_user)
    _emit_thinking_processing_event(
        session=session,
        processing_event_callback=processing_event_callback,
    )
    _warn_if_flow_pack_missing(session_id=session_id, session=session, request_text=content)

    history = _repository.list_messages(session_id)
    prior_messages = history[:-1]
    processing_events: list[dict[str, object]] = []
    conversation = [
        CoreMessage(
            role=msg.role.value,
            content=msg.content,
            agent_name=msg.agent_name or ("User" if msg.role == MessageRole.USER else "Assistant"),
        )
        for msg in history
    ]

    if _should_reply_with_ready_document_status(content=content, previous_messages=prior_messages):
        status_reply = _document_package_ready_message(
            country=session.country,
            language=session.language,
            document_names=_document_progress_names(
                messages=prior_messages,
                lawyer_message="",
                country=session.country,
                language=session.language,
            ),
        )
        persisted_lawyer = _persist_direct_assistant_message(
            session_id=session_id,
            session=session,
            content=status_reply,
            agent_name="LawyerStatus",
            allow_document_generation=False,
        )
        _record_case_ai_model_audit(
            session=session,
            question=persisted_user,
            answer=persisted_lawyer,
            task_type="chat_status",
            source="chat.direct_reply",
            model_used=False,
        )
        return (
            persisted_user,
            persisted_lawyer,
            _user_visible_text(persisted_lawyer.content),
            [],
            None,
        )

    document_generation_requested = _user_requested_document_generation(
        content=content,
        previous_messages=prior_messages,
    )
    preparation = prepare_country_direct_reply(
        session=session,
        messages=history,
        current_content=content,
        prior_messages=prior_messages,
        normalize_document_lines=_normalize_document_lines,
        extract_document_facts=_extract_document_facts,
        current_turn_confirms_document_generation=_current_turn_confirms_document_generation,
        build_share_transfer_lines=_build_slovak_share_transfer_lines,
        processing_event_callback=processing_event_callback,
    )
    processing_events = list(preparation.processing_events)
    if preparation.direct_reply is not None:
        _LOGGER.info(
            "Chat route selected",
            extra={
                "chat_route": "country_direct_reply",
                "current_turn_document_request": _user_requested_document_generation(
                    content=content,
                    previous_messages=prior_messages,
                ),
                "generated_artifact_payload": _extract_case_update(preparation.direct_reply) is not None,
            },
        )
        normalized_direct_reply = _finalize_document_ready_reply_if_needed(
            session=session,
            messages=history,
            lawyer_content=_enforce_single_question_turn(preparation.direct_reply),
        )
        persisted_lawyer = _persist_direct_assistant_message(
            session_id=session_id,
            session=session,
            content=normalized_direct_reply,
            agent_name="Assistant",
            allow_document_generation=_user_requested_document_generation(
                content=content,
                previous_messages=prior_messages,
            ),
        )
        _record_case_ai_model_audit(
            session=session,
            question=persisted_user,
            answer=persisted_lawyer,
            task_type="chat_direct_reply",
            source="chat.direct_reply",
            model_used=False,
        )
        return (
            persisted_user,
            persisted_lawyer,
            _user_visible_text(persisted_lawyer.content),
            processing_events,
            None,
        )

    routed_llm = _resolve_session_llm_route(
        session=session,
        task_type="chat_reply",
        request_user_id=request_user_id,
        request_user_email=request_user_email,
    )

    from aijurisdictionagents.agents import create_lawyer_agent

    runtime_reply = _runtime_question_reply(
        content=content,
        route=routed_llm,
        prior_messages=prior_messages,
    )
    if runtime_reply is not None:
        persisted_lawyer = _persist_direct_assistant_message(
            session_id=session_id,
            session=session,
            content=runtime_reply,
            agent_name="Assistant",
            allow_document_generation=False,
        )
        _record_case_ai_model_audit(
            session=session,
            question=persisted_user,
            answer=persisted_lawyer,
            task_type="chat_status",
            source="chat.direct_reply",
            model_used=False,
            route=routed_llm,
        )
        return (
            persisted_user,
            persisted_lawyer,
            _user_visible_text(persisted_lawyer.content),
            processing_events,
            routed_llm,
        )

    case_catalog_context = resolve_case_catalog_context(
        session_id=session_id,
        session=session,
        current_content=content,
        prior_messages=prior_messages,
        route=routed_llm,
        store=_get_store(),
        template_store=get_document_template_store(),
        document_generation_requested=document_generation_requested,
    )
    if case_catalog_context.direct_reply is not None:
        persisted_lawyer = _persist_direct_assistant_message(
            session_id=session_id,
            session=session,
            content=case_catalog_context.direct_reply,
            agent_name="CaseTypeDetectionAgent",
            allow_document_generation=False,
        )
        _record_case_ai_model_audit(
            session=session,
            question=persisted_user,
            answer=persisted_lawyer,
            task_type="case_type_detection",
            source="chat.case_type_detection",
            model_used=False,
            route=routed_llm,
        )
        return (
            persisted_user,
            persisted_lawyer,
            _user_visible_text(persisted_lawyer.content),
            processing_events,
            routed_llm,
        )
    lawyer = create_lawyer_agent(routed_llm.client, session.country)
    case_memory_note = _build_case_memory_refresh_note(prior_messages)
    user_profile_note = _build_signed_in_user_profile_prompt_note(session)
    _LOGGER.info(
        "Chat route selected",
        extra={
            "chat_route": "model_answer",
            "current_turn_document_request": document_generation_requested,
            "generated_artifact_payload": False,
        },
    )
    use_compact_local_prompt = _is_free_local_reply_route(routed_llm)
    if use_compact_local_prompt:
        prompt_override = _build_compact_free_local_lawyer_prompt(
            session=session,
            case_memory_note=case_memory_note,
            user_profile_note=user_profile_note,
            preparation_prompt_note=preparation.prompt_note,
            document_generation_requested=document_generation_requested,
        )
    else:
        prompt_override = lawyer.system_prompt
        if session.language and session.language.strip():
            prompt_override = f"{lawyer.system_prompt}\nRespond in {session.language.strip()}."
        prompt_override = (
            f"{prompt_override}\n\n"
            "SINGLE-QUESTION CLARIFICATION POLICY:\n"
            "- If clarification is needed, ask exactly one highest-priority question in this turn.\n"
            "- Do not ask multiple numbered questions in one reply.\n"
            "- Do not include summary/risk/next-step sections while waiting for that single answer.\n"
            "- Keep CASE_UPDATE_JSON.case.open_questions at maximum one item when awaiting user input."
        )
        prompt_override = f"{prompt_override}\n\n{_build_current_date_prompt_note()}"
        if case_memory_note:
            prompt_override = f"{prompt_override}\n\n{case_memory_note}"
        if user_profile_note:
            prompt_override = f"{prompt_override}\n\n{user_profile_note}"
        if document_generation_requested:
            prompt_override = (
                f"{prompt_override}\n\n"
                "DOCUMENT GENERATION MODE:\n"
                "- The user confirmed that they want the downloadable document prepared now.\n"
                "- Do not ask for PDF confirmation again.\n"
                "- Produce the finalized draft-oriented response for PDF export in this turn.\n"
                "- Do not claim that PDF or ZIP files are already created, saved, attached, or uploaded.\n"
                "- Say that the draft package is ready for download/export instead.\n"
                "- Do not mention JSON, CASE_UPDATE_JSON, machine payload, or technical persistence details in the user-facing content.\n"
                "- Do not include direct file paths, markdown download links, or relative links such as documents/... in the user-facing content.\n"
                "- Include CASE_UPDATE_JSON after the user-facing content.\n"
                "- Never output unresolved placeholders in square brackets (for example [Vase meno], [address], [ico]).\n"
                "- If any required field is missing, ask for it explicitly instead of using placeholders."
            )
        if preparation.prompt_note:
            prompt_override = f"{prompt_override}\n\n{preparation.prompt_note}"
    if case_catalog_context.prompt_note:
        prompt_override = f"{prompt_override}\n\n{case_catalog_context.prompt_note}"
    case_documents: list[CoreDocument] = []
    processed_names: list[str] = []
    unprocessed_names: list[str] = []
    if session.case_id:
        case_documents, processed_names, unprocessed_names = _load_case_documents_for_llm(
            case_id=session.case_id,
            query=content,
        )
        if processed_names or unprocessed_names:
            context_note = (
                '\n\nCASE DOCUMENT STATUS:\n'
                f"Processed documents: {', '.join(processed_names) if processed_names else 'none'}.\n"
                f"Unprocessed documents: {', '.join(unprocessed_names) if unprocessed_names else 'none'}.\n"
                'Use processed documents as case evidence and explicitly mention any unprocessed documents.'
            )
            prompt_override = f"{prompt_override}{context_note}"
    if not use_compact_local_prompt:
        task_plan_note = build_document_task_plan_note(
            query=content,
            has_processed_documents=bool(
                case_documents or supplemental_documents or preparation.supplemental_documents
            ),
        )
        if task_plan_note:
            prompt_override = f"{prompt_override}{task_plan_note}"

    all_documents = list(preparation.supplemental_documents)
    all_documents.extend(supplemental_documents or [])
    all_documents.extend(case_catalog_context.template_documents)
    all_documents.extend(case_documents)
    uploaded_contract_note = _build_uploaded_document_contract_confirmation_note(
        content=content,
        documents=all_documents,
    )
    if uploaded_contract_note:
        prompt_override = f"{prompt_override}\n\n{uploaded_contract_note}"
    mcp_status_context = build_mcp_status_context(
        query=content,
        country=session.country,
        language=session.language,
    )
    if use_compact_local_prompt and mcp_status_context is not None and mcp_status_context.direct_reply:
        persisted_lawyer = _persist_direct_assistant_message(
            session_id=session_id,
            session=session,
            content=mcp_status_context.direct_reply,
            agent_name="Assistant",
            allow_document_generation=False,
        )
        processing_events.append(mcp_status_context.processing_event)
        if processing_event_callback is not None:
            processing_event_callback(mcp_status_context.processing_event)
        _record_case_ai_model_audit(
            session=session,
            question=persisted_user,
            answer=persisted_lawyer,
            task_type="chat_status",
            source="chat.direct_reply",
            model_used=False,
        )
        return (
            persisted_user,
            persisted_lawyer,
            _user_visible_text(persisted_lawyer.content),
            processing_events,
            routed_llm,
        )
    if mcp_status_context is not None:
        prompt_override = f"{prompt_override}\n\n{mcp_status_context.prompt_note}"
        if mcp_status_context.document is not None:
            all_documents.append(mcp_status_context.document)
        processing_events.append(mcp_status_context.processing_event)
        if processing_event_callback is not None:
            processing_event_callback(mcp_status_context.processing_event)
    mcp_law_context = build_mcp_law_context(
        query=content,
        country=session.country,
        language=session.language,
    )
    if mcp_law_context is not None:
        prompt_override = f"{prompt_override}\n\n{mcp_law_context.prompt_note}"
        if mcp_law_context.document is not None:
            all_documents.append(mcp_law_context.document)
        processing_events.append(mcp_law_context.processing_event)
        if processing_event_callback is not None:
            processing_event_callback(mcp_law_context.processing_event)
    if not use_compact_local_prompt:
        legal_document_policy_note = _build_legal_document_preparation_policy_note(
            content=content,
            country=session.country,
        )
        if legal_document_policy_note:
            prompt_override = f"{prompt_override}\n\n{legal_document_policy_note}"
    lawyer_message = lawyer.respond(
        conversation=conversation,
        documents=all_documents,
        sources=[],
        system_prompt_override=prompt_override,
    )
    normalized_lawyer_content = _enforce_single_question_turn(
        _apply_case_memory_to_lawyer_content(
            content=_prepend_document_status_note(
                reply=lawyer_message.content,
                processed_names=processed_names,
                unprocessed_names=unprocessed_names,
            ),
            prior_messages=prior_messages,
        )
    )
    normalized_lawyer_content = _finalize_document_ready_reply_if_needed(
        session=session,
        messages=history,
        lawyer_content=normalized_lawyer_content,
    )
    persisted_lawyer = _persist_direct_assistant_message(
        session_id=session_id,
        session=session,
        content=normalized_lawyer_content,
        agent_name=lawyer_message.agent_name,
        allow_document_generation=document_generation_requested,
    )
    _record_case_ai_model_audit(
        session=session,
        question=persisted_user,
        answer=persisted_lawyer,
        task_type="chat_reply",
        source="chat.direct_reply",
        model_used=True,
        route=routed_llm,
    )
    return (
        persisted_user,
        persisted_lawyer,
        _user_visible_text(persisted_lawyer.content),
        processing_events,
        routed_llm,
    )


def _warn_if_flow_pack_missing(*, session_id: UUID, session: Session, request_text: str) -> None:
    try:
        flow_pack = get_flow_pack_store().find_best_match(
            request_text=request_text,
            country=session.country,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning(
            "Flow-pack lookup failed for request | session_id=%s country=%s reason=%s",
            session_id,
            session.country,
            exc,
        )
        return
    if flow_pack is None:
        _LOGGER.warning(
            "No flow-pack matched user request | session_id=%s country=%s request=%s",
            session_id,
            session.country,
            " ".join(request_text.split())[:180],
        )


def _is_free_local_reply_route(route: RoutedLLMClient) -> bool:
    return bool(route.route_type == "free_local" and route.provider == "local_ollama")


def _runtime_question_reply(
    *,
    content: str,
    route: RoutedLLMClient,
    prior_messages: list[Message] | None = None,
) -> str | None:
    normalized = _canonicalize_document_text(content)
    asks_missing_data = "chybajuc" in normalized and any(
        marker in normalized for marker in ("udaj", "data", "inform")
    )
    if asks_missing_data:
        prior_text = "\n".join(
            _canonicalize_document_text(_user_visible_text(message.content))
            for message in (prior_messages or [])
            if message.role == MessageRole.ASSISTANT
        )
        missing_fields: list[str] = []
        candidates = (
            ("poskytovatel pozicky bude doplneny", "poskytovateľ/platiteľ"),
            ("prijemca bude doplneny", "príjemca"),
            ("datum bude doplneny", "dátum platby alebo splatnosti"),
            ("[mesto]", "miesto vystavenia"),
            ("[datum vystavenia]", "dátum vystavenia"),
        )
        for marker, label in candidates:
            if marker in prior_text and label not in missing_fields:
                missing_fields.append(label)
        if missing_fields:
            return "V pripravenom dokumente chýbajú tieto údaje: " + ", ".join(missing_fields) + "."
        return "V predchádzajúcej odpovedi nie sú označené žiadne konkrétne chýbajúce údaje."

    asks_model = "model" in normalized and any(
        marker in normalized for marker in ("aky", "ktory", "nazov", "pouziv")
    )
    if asks_model:
        return f"V tomto chate používam model {route.model} cez poskytovateľa {route.provider}."

    asks_mcp_runtime = "mcp" in normalized and any(
        marker in normalized for marker in ("lokal", "local", "pouziv")
    )
    if not asks_mcp_runtime:
        return None
    remote_mcp = os.getenv("INTERNAL_MCP_BASE_URL", os.getenv("MCP_PUBLIC_BASE_URL", "")).strip()
    if remote_mcp and remote_mcp != "unknown-variable":
        return "JurisDigta MCP používam cez interné sieťové pripojenie, nie lokálne v procese API."
    return "Áno. JurisDigta MCP je v tomto nasadení volané lokálne v procese API."


def _build_compact_free_local_lawyer_prompt(
    *,
    session: Session,
    case_memory_note: str,
    user_profile_note: str,
    preparation_prompt_note: str,
    document_generation_requested: bool,
) -> str:
    language = session.language.strip() if session.language and session.language.strip() else "sk"
    language_guard = _build_free_local_language_guard(language=language, country=session.country)
    document_mode_note = (
        "- The user confirmed document generation. Prepare draft-oriented text for export, but do not claim files "
        "already exist and do not output unresolved placeholders."
        if document_generation_requested
        else "- If a downloadable legal document is requested, ask whether the user wants it prepared now before drafting."
    )
    optional_notes = "\n".join(
        note
        for note in (
            _clamp_prompt_note("Case memory", case_memory_note, max_chars=700),
            _clamp_prompt_note("Signed-in user profile", user_profile_note, max_chars=500),
            _clamp_prompt_note("Country-specific note", preparation_prompt_note, max_chars=900),
        )
        if note
    )
    return textwrap.dedent(
        f"""
        You are JurisDigta Assistant, a Slovak legal intake assistant for free-plan local model routing.
        Reply in {language}. Be concise and practical.
        {language_guard}

        Compliance and safety:
        - Apply GDPR data minimization: do not ask for IDs, birth numbers, addresses, or sensitive data unless needed.
        - Treat the output as preliminary legal-risk support that requires human legal oversight before use.
        - Do not invent facts, laws, registry results, signatures, authority, or uploaded document contents.
        - Do not help with fraud, evasion, or illegal conduct.

        Turn policy:
        - If facts are missing, ask exactly one highest-priority question.
        - Do not ask multiple numbered questions in one reply.
        - If enough facts are present, give a short next-step answer and identify any remaining missing fact.
        {document_mode_note}

        Output contract:
        - First write only the user-facing answer.
        - Do not show hidden reasoning, analysis, planning text, or self-dialogue.
        - Then include CASE_UPDATE_JSON with compact valid JSON:
          {{"case":{{"status":"intake_open|waiting_user|ready_for_next_step","jurisdiction":{{"country":"{session.country}","language":"{language}"}},"facts_summary":"...","client_goal":"...","open_questions":["..."]}}}}
        - Keep open_questions to at most one item.

        {_build_current_date_prompt_note()}
        {optional_notes}
        """
    ).strip()


def _build_free_local_language_guard(*, language: str, country: str) -> str:
    normalized_language = language.strip().lower()
    normalized_country = country.strip().upper()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return (
            "Use only Slovak (sk-SK) in every visible answer, including notes, summaries, "
            "questions, labels, and any explanation. Do not mix English and Slovak. Do not write "
            "English meta-analysis such as 'We need to', 'The user has', or 'However, the problem "
            "is'. Do not expose hidden chain-of-thought; provide only the concise user-facing "
            "Slovak answer."
        )
    return (
        "Use only the selected user language in every visible answer, including notes, summaries, "
        "questions, labels, and any explanation. Do not mix languages. Do not expose hidden "
        "chain-of-thought; provide only the concise user-facing answer."
    )


def _clamp_prompt_note(label: str, note: str, *, max_chars: int) -> str:
    normalized = " ".join(note.split())
    if not normalized:
        return ""
    if len(normalized) > max_chars:
        normalized = f"{normalized[: max_chars - 3].rstrip()}..."
    return f"{label}: {normalized}"


class StartSessionStreamRequest(BaseModel):
    instruction: str
    documents: List[InputDocument] = Field(default_factory=list)
    question_timeout_seconds: float = 300
    max_discussion_minutes: float = 15
    communication_minutes: float | None = None
    user_simulation_mode: Literal["ReadUser", "AIUserSimulatorAgent"] = "ReadUser"
    user_replies: List[str] = Field(default_factory=list)
    user_id: UUID | None = None
    user_email: str | None = None
    model_profile_id: str | None = None


@router.post("/sessions", response_model=Session)
def create_session(payload: CreateSessionRequest) -> Session:
    session = Session(
        user_id=payload.user_id,
        case_id=payload.case_id,
        country=payload.country,
        language=payload.language,
        discussion_type=payload.discussion_type,
        selected_model_profile_id=(payload.model_profile_id or "").strip() or None,
    )
    created = _repository.create_session(session)
    _bootstrap_case_history_if_needed(session=created)
    return created


@router.post("/messages", response_model=Message)
def create_message(payload: CreateMessageRequest) -> Message:
    try:
        return _repository.add_message(
            Message(session_id=payload.session_id, role=payload.role, content=payload.content)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/reply", response_model=Message)
def reply_to_session(session_id: UUID, payload: ReplyRequest) -> Message:
    session = _repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.user_id is None and payload.user_id is not None:
        session.user_id = payload.user_id
    _ensure_case_write_access_for_session(session)

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Reply content is required")
    if payload.model_profile_id is not None:
        session.selected_model_profile_id = payload.model_profile_id.strip() or None

    _persisted_user, persisted_lawyer, visible_lawyer_content, processing_events, routed_llm = (
        _run_direct_lawyer_turn(
            session_id=session_id,
            session=session,
            content=content,
            request_user_id=str(payload.user_id) if payload.user_id else None,
            request_user_email=payload.user_email,
        )
    )
    _persist_session_history_document_if_needed(session=session, session_id=session_id)
    session_result = _build_direct_reply_result(
        session_id=session_id,
        session=session,
        messages=_repository.list_messages(session_id),
        lawyer_message=visible_lawyer_content,
        route=routed_llm,
        legal_source_citations=_legal_source_citations_from_processing_events(processing_events),
    )
    _repository.set_result(session_id, session_result)
    persisted_citations = _persist_case_citations_for_answer(
        session=session,
        question=_persisted_user,
        answer=persisted_lawyer,
        result=session_result,
    )

    return _message_for_user(persisted_lawyer).model_copy(update={"citations": persisted_citations})


@router.get("/sessions/{session_id}/messages", response_model=List[Message])
def list_session_messages(session_id: UUID) -> List[Message]:
    if _repository.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return [_message_for_user(message) for message in _repository.list_messages(session_id)]


@router.post("/sessions/{session_id}/stream")
def stream_session(session_id: UUID, payload: StartSessionStreamRequest) -> StreamingResponse:
    session = _repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.state == SessionState.COMPLETED and payload.user_simulation_mode != "ReadUser":
        raise HTTPException(status_code=409, detail="Session already completed")
    if session.user_id is None and payload.user_id is not None:
        session.user_id = payload.user_id
    if payload.model_profile_id is not None:
        session.selected_model_profile_id = payload.model_profile_id.strip() or None
    _ensure_case_write_access_for_session(session)
    _persist_inline_case_documents_if_needed(session=session, documents=payload.documents)
    if payload.user_simulation_mode == "ReadUser":
        return _stream_read_user_session(session_id=session_id, session=session, payload=payload)

    event_queue: Queue[tuple[str, dict[str, object]] | None] = Queue()
    replies = deque(payload.user_replies)
    communication_minutes = payload.communication_minutes or payload.max_discussion_minutes
    simulation_deadline = time.monotonic() + max(communication_minutes, 0) * 60
    seeded_messages = _repository.list_messages(session_id)
    core_conversation: list[CoreMessage] = [
        CoreMessage(
            role=message.role.value,
            content=message.content,
            agent_name=message.agent_name or (
                "User" if message.role == MessageRole.USER else "Assistant"
            ),
        )
        for message in seeded_messages
    ]
    question_attempts: dict[str, int] = {}
    simulation_turn = 0
    last_simulator_reply = ""
    assistant_messages_seen = len(
        [item for item in seeded_messages if item.role == MessageRole.ASSISTANT]
    )
    last_audit_user_message: Message | None = None
    answered_agent_questions = 0
    followup_prompts_seen = 0
    pdf_request_sent = False
    thank_you_sent = False
    stream_route: RoutedLLMClient | None = None

    simulator = None
    simulator_documents = [CoreDocument(doc_id=d.doc_id, path=d.path, content=d.content) for d in payload.documents]
    if payload.user_simulation_mode == "AIUserSimulatorAgent":
        from aijurisdictionagents.agents import AIUserSimulatorAgent

        simulator_route = _resolve_session_llm_route(session=session, task_type="user_simulator")
        simulator = AIUserSimulatorAgent(simulator_route.client, language=session.language)

    def user_response_provider(_question: str, _timeout: float) -> str | None:
        nonlocal simulation_turn, last_simulator_reply
        nonlocal answered_agent_questions, followup_prompts_seen
        nonlocal pdf_request_sent, thank_you_sent
        if time.monotonic() > simulation_deadline:
            return None
        if simulator is not None and communication_minutes > 0:
            simulation_turn += 1
            normalized_question = _normalize_question_key(_question)
            question_attempts[normalized_question] = question_attempts.get(normalized_question, 0) + 1
            question_count = question_attempts[normalized_question]

            if _is_pdf_format_question(_question):
                if answered_agent_questions < 1:
                    answered_agent_questions += 1
                    reply = _defer_pdf_reply(session.language)
                    last_simulator_reply = reply
                    return reply
                if not pdf_request_sent:
                    pdf_request_sent = True
                    reply = _request_pdf_reply(session.language)
                    last_simulator_reply = reply
                    return reply
                if not thank_you_sent:
                    thank_you_sent = True
                    reply = _thank_you_reply(session.language)
                    last_simulator_reply = reply
                    return reply
                reply = _finish_discussion_reply(session.language)
                last_simulator_reply = reply
                return reply

            if _is_followup_termination_prompt(_question):
                followup_prompts_seen += 1
                if answered_agent_questions < 1:
                    answered_agent_questions += 1
                    reply = _continue_discussion_reply(session.language, simulation_turn)
                    last_simulator_reply = reply
                    return reply
                if not pdf_request_sent:
                    pdf_request_sent = True
                    reply = _request_pdf_reply(session.language)
                    last_simulator_reply = reply
                    return reply
                if not thank_you_sent:
                    thank_you_sent = True
                    reply = _thank_you_reply(session.language)
                    last_simulator_reply = reply
                    return reply
                if _should_finish_followup(
                    assistant_messages_seen=assistant_messages_seen,
                    answered_agent_questions=answered_agent_questions,
                    followup_prompts_seen=followup_prompts_seen,
                ):
                    reply = _finish_discussion_reply(session.language)
                    last_simulator_reply = reply
                    return reply
                reply = _continue_discussion_reply(session.language, simulation_turn)
                last_simulator_reply = reply
                return reply
            conversation = list(core_conversation)
            simulator_question = _question
            if question_count > 1:
                simulator_question = (
                    f"{_question}\n"
                    "You already answered a very similar question. "
                    "Give a different, more specific answer with new facts."
                )
            raw_reply = simulator.prepare_random_answer(
                simulator_question,
                conversation=conversation,
                documents=simulator_documents,
            )
            answered_agent_questions += 1
            reply = _normalize_simulator_reply(
                raw_reply,
                session.language,
                turn_index=simulation_turn,
                previous_reply=last_simulator_reply,
            )
            last_simulator_reply = reply
            return reply
        if replies:
            return replies.popleft()
        return None

    def message_callback(core_message: CoreMessage) -> None:
        nonlocal last_audit_user_message
        nonlocal assistant_messages_seen
        normalized_role = core_message_role(core_message.role)
        if normalized_role == "assistant":
            assistant_messages_seen += 1
            content = _attach_technical_payload_to_case_if_needed(
                session=session,
                content=_validate_lawyer_output_message(session=session, content=core_message.content),
            )
            generated_doc_ids = _persist_generated_case_document_if_needed(
                session=session,
                content=content,
            )
            content = _attach_generated_case_document_references(
                session=session,
                content=content,
                doc_ids=generated_doc_ids,
            )
        else:
            content = core_message.content
        core_conversation.append(core_message)
        persisted = _repository.add_message(
            Message(
                session_id=session_id,
                role=MessageRole(normalized_role),
                content=content,
                agent_name=core_message.agent_name,
            )
        )
        _persist_case_message_if_needed(
            session=session,
            role=normalized_role,
            content=content,
            agent_name=core_message.agent_name,
        )
        if normalized_role == "user":
            last_audit_user_message = persisted
        elif normalized_role == "assistant" and last_audit_user_message is not None:
            _record_case_ai_model_audit(
                session=session,
                question=last_audit_user_message,
                answer=persisted,
                task_type="discussion_stream",
                source="chat.stream",
                model_used=True,
                route=stream_route,
            )
            last_audit_user_message = None
        event_queue.put(("message", _message_payload(persisted)))
        if normalized_role == "user":
            event_queue.put(
                (
                    "processing",
                    {
                        "stage": "processing",
                        "message": _processing_status_message(
                            country=session.country,
                            language=session.language,
                        ),
                    },
                )
            )
            event_queue.put(
                (
                    "processing",
                    {
                        "stage": "thinking",
                        "message": _thinking_status_message(
                            country=session.country,
                            language=session.language,
                        ),
                    },
                )
            )

    def worker() -> None:
        nonlocal stream_route
        try:
            docs = [
                CoreDocument(doc_id=d.doc_id, path=d.path, content=d.content)
                for d in payload.documents
            ]
            if session.case_id:
                case_documents, _processed_names, _unprocessed_names = _load_case_documents_for_llm(
                    case_id=session.case_id,
                    query=payload.instruction,
                )
                docs.extend(case_documents)
            stream_route = _resolve_session_llm_route(session=session, task_type="discussion_stream")
            result = run_orchestration(
                session=session,
                instruction=payload.instruction,
                documents=docs,
                question_timeout_seconds=payload.question_timeout_seconds,
                max_discussion_minutes=payload.max_discussion_minutes,
                user_response_provider=user_response_provider,
                message_callback=message_callback,
                llm_client=stream_route.client,
            )
            persisted_messages = _repository.list_messages(session_id)
            metadata = build_session_result_metadata(
                session=session,
                messages=persisted_messages,
                final_recommendation=result.final_recommendation,
                base_metadata={"message_count": len(result.messages), "mode": "discussion_stream"},
                routed_model_name=stream_route.model if stream_route is not None else None,
            )
            session_result = SessionResult(
                final_recommendation=result.final_recommendation,
                judge_rationale=result.judge_rationale,
                citations=_merge_session_citations(
                    generic_citations=[{"filename": c.filename, "snippet": c.snippet} for c in result.citations],
                    metadata=metadata,
                ),
                metadata=metadata,
            )
            _persist_session_history_document_if_needed(session=session, session_id=session_id)
            _repository.set_result(session_id, session_result)
            event_queue.put(("result", session_result.model_dump(mode="json")))
            event_queue.put(("done", {"session_id": str(session_id)}))
        except Exception as exc:  # noqa: BLE001
            _repository.mark_failed(session_id)
            timeout_payload = _model_timeout_error_payload(
                exc,
                session=session,
                task_type="discussion_stream",
            )
            if timeout_payload is None:
                _LOGGER.exception(
                    "Discussion stream worker failed | session_id=%s error_type=%s",
                    session_id,
                    type(exc).__name__,
                )
            event_queue.put(("error", timeout_payload or {"message": str(exc)}))
        finally:
            event_queue.put(None)

    Thread(target=worker, daemon=True).start()

    return StreamingResponse(
        _stream_event_queue(event_queue=event_queue, session=session),
        media_type="text/event-stream",
    )


def _stream_read_user_session(
    *,
    session_id: UUID,
    session: Session,
    payload: StartSessionStreamRequest,
) -> StreamingResponse:
    inline_documents = [CoreDocument(doc_id=d.doc_id, path=d.path, content=d.content) for d in payload.documents]
    event_queue: Queue[tuple[str, dict[str, object]] | None] = Queue()

    def processing_event_callback(event: dict[str, object]) -> None:
        event_queue.put(("processing", event))

    def user_message_callback(message: Message) -> None:
        event_queue.put(("message", _message_payload(message)))

    def worker() -> None:
        try:
            existing_result = _get_or_build_session_result(session_id)
            previous_messages = _repository.list_messages(session_id)
            if _is_document_email_flow_message(
                content=payload.instruction,
                previous_messages=previous_messages,
            ):
                persisted_user = _repository.add_message(
                    Message(
                        session_id=session_id,
                        role=MessageRole.USER,
                        content=payload.instruction,
                        agent_name="User",
                    )
                )
                _persist_case_message_if_needed(
                    session=session,
                    role="user",
                    content=payload.instruction,
                    agent_name="User",
                )
                user_message_callback(persisted_user)
                email_reply = _handle_document_email_flow(
                    session_id=session_id,
                    session=session,
                    content=payload.instruction,
                    previous_messages=previous_messages,
                )
                persisted_lawyer = _persist_direct_assistant_message(
                    session_id=session_id,
                    session=session,
                    content=email_reply,
                    agent_name="LawyerEmail",
                )
                _record_case_ai_model_audit(
                    session=session,
                    question=persisted_user,
                    answer=persisted_lawyer,
                    task_type="chat_email_flow",
                    source="chat.read_user_stream",
                    model_used=False,
                )
                _persist_session_history_document_if_needed(session=session, session_id=session_id)
                event_queue.put(("message", _message_payload(persisted_lawyer)))
                event_queue.put(("done", {"session_id": str(session_id), "status": "completed"}))
                return
            if session.state == SessionState.COMPLETED and _is_document_status_request(payload.instruction):
                persisted_user = _repository.add_message(
                    Message(
                        session_id=session_id,
                        role=MessageRole.USER,
                        content=payload.instruction,
                        agent_name="User",
                    )
                )
                _persist_case_message_if_needed(
                    session=session,
                    role="user",
                    content=payload.instruction,
                    agent_name="User",
                )
                user_message_callback(persisted_user)
                existing_result = _get_or_build_session_result(session_id) or existing_result
                status_reply = _build_document_status_reply(
                    session=session,
                    messages=_repository.list_messages(session_id),
                    result=existing_result,
                )
                persisted_lawyer = _persist_direct_assistant_message(
                    session_id=session_id,
                    session=session,
                    content=status_reply,
                    agent_name="LawyerStatus",
                )
                _record_case_ai_model_audit(
                    session=session,
                    question=persisted_user,
                    answer=persisted_lawyer,
                    task_type="chat_status",
                    source="chat.read_user_stream",
                    model_used=False,
                )
                current_messages = _repository.list_messages(session_id)
                event_queue.put(
                    (
                        "processing",
                        {
                            "stage": "document_status",
                            "message": status_reply,
                            "details": {"status": "completed"},
                        },
                    )
                )
                event_queue.put(("message", _message_payload(persisted_lawyer)))
                _persist_session_history_document_if_needed(session=session, session_id=session_id)
                event_queue.put(("done", {"session_id": str(session_id), "status": "completed"}))
                return
            if session.state == SessionState.COMPLETED:
                _repository.reactivate_session(session_id)
            _persisted_user, persisted_lawyer, visible_lawyer_content, processing_events, routed_llm = (
                _run_direct_lawyer_turn(
                    session_id=session_id,
                    session=session,
                    content=payload.instruction,
                    request_user_id=str(payload.user_id) if payload.user_id else None,
                    request_user_email=payload.user_email,
                    supplemental_documents=inline_documents,
                    processing_event_callback=processing_event_callback,
                    user_message_callback=user_message_callback,
                )
            )
            current_messages = _repository.list_messages(session_id)
            if not current_messages:
                current_messages = [message for message in (_persisted_user, persisted_lawyer) if message is not None]
            session_result = _build_direct_reply_result(
                session_id=session_id,
                session=session,
                messages=current_messages,
                lawyer_message=visible_lawyer_content,
                route=routed_llm,
                legal_source_citations=_legal_source_citations_from_processing_events(processing_events),
            )
            _persist_case_citations_for_answer(
                session=session,
                question=_persisted_user,
                answer=persisted_lawyer,
                result=session_result,
            )
            for document_event in _document_generation_progress_events(
                session=session,
                messages=current_messages,
                lawyer_message=visible_lawyer_content,
            ):
                event_queue.put(("processing", document_event))
            event_queue.put(("message", _message_payload(persisted_lawyer)))

            waiting_for_user_reply = _assistant_requests_user_reply(
                visible_lawyer_content
            ) and not _document_export_ready(current_messages)
            if waiting_for_user_reply:
                event_queue.put(
                    (
                        "waiting_for_reply",
                        {
                            "session_id": str(session_id),
                            "mode": "ReadUser",
                            "message": "Stream paused. Waiting for manual /reply input.",
                        },
                    )
                )
                event_queue.put(("done", {"session_id": str(session_id), "status": "waiting_for_reply"}))
            else:
                _persist_session_history_document_if_needed(session=session, session_id=session_id)
                _repository.set_result(session_id, session_result)
                for document_event in _document_completion_processing_events(
                    session=session,
                    messages=current_messages,
                    result=session_result,
                ):
                    event_queue.put(("processing", document_event))
                event_queue.put(("result", session_result.model_dump(mode="json")))
                event_queue.put(("done", {"session_id": str(session_id), "status": "completed"}))
        except Exception as exc:  # noqa: BLE001
            _repository.mark_failed(session_id)
            timeout_payload = _model_timeout_error_payload(
                exc,
                session=session,
                task_type="chat_reply",
            )
            if timeout_payload is None:
                _LOGGER.exception(
                    "ReadUser stream worker failed | session_id=%s error_type=%s",
                    session_id,
                    type(exc).__name__,
                )
            event_queue.put(("error", timeout_payload or {"message": str(exc)}))
        finally:
            event_queue.put(None)

    Thread(target=worker, daemon=True).start()

    return StreamingResponse(
        _stream_event_queue(event_queue=event_queue, session=session),
        media_type="text/event-stream",
    )


def _is_followup_termination_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    return "finish" in lowered and ("type" in lowered or "nap" in lowered)


def _is_pdf_format_question(prompt: str) -> bool:
    lowered = prompt.lower()
    return "pdf" in lowered and "?" in prompt


def _user_requested_document_generation(*, content: str, previous_messages: list[Message]) -> bool:
    normalized = _canonicalize_document_text(content)
    if _is_explicit_document_request(normalized):
        return True
    if not _is_affirmative_reply(normalized):
        return False
    return _has_unanswered_document_confirmation(previous_messages)


def _is_explicit_document_request(normalized: str) -> bool:
    normalized = _canonicalize_document_text(normalized)
    document_markers = (
        "pdf",
        "document",
        "draft",
        "template",
        "zmluv",
        "zakon",
        "zakonov",
        "law",
        "laws",
        "predzalob",
        "predžalob",
        "vzor",
        "dokument",
    )
    request_markers = (
        "prepare",
        "generate",
        "create",
        "draft",
        "review",
        "revise",
        "update",
        "amend",
        "fix",
        "prosim",
        "please",
        "chcem",
        "priprav",
        "vytvor",
        "vygeneruj",
        "pozri",
        "skontroluj",
        "oprav",
        "uprav",
        "aktualizuj",
        "podla",
    )
    return any(marker in normalized for marker in document_markers) and any(
        marker in normalized for marker in request_markers
    )


def _is_affirmative_reply(normalized: str) -> bool:
    normalized = _canonicalize_document_text(normalized)
    replacement_repaired = normalized.replace("\ufffd", "a")
    affirmatives = (
        "ano",
        "yes",
        "sure",
        "ok",
        "okay",
        "prosim",
        "please",
        "chcem",
        "potvrdzujem",
    )
    return any(
        token in candidate
        for candidate in (normalized, replacement_repaired)
        for token in affirmatives
    )


def _is_standalone_affirmative_reply(content: str) -> bool:
    normalized = _canonicalize_document_text(content)
    replacement_repaired = normalized.replace("\ufffd", "a")
    standalone_affirmatives = {
        "ano",
        "yes",
        "sure",
        "ok",
        "okay",
        "prosim",
        "please",
        "potvrdzujem",
        "user: ano",
        "user ano",
    }
    return normalized in standalone_affirmatives or replacement_repaired in standalone_affirmatives


def _has_unanswered_document_confirmation(messages: list[Message]) -> bool:
    awaiting_confirmation = False
    for message in messages:
        if message.role == MessageRole.ASSISTANT and _assistant_requests_document_confirmation(message.content):
            awaiting_confirmation = True
            continue
        if message.role != MessageRole.USER or not awaiting_confirmation:
            continue
        normalized = _canonicalize_document_text(message.content)
        if _is_affirmative_reply(normalized) or _is_explicit_document_request(normalized):
            awaiting_confirmation = False
    return awaiting_confirmation


def _should_reply_with_ready_document_status(*, content: str, previous_messages: list[Message]) -> bool:
    if not _is_standalone_affirmative_reply(content):
        return False
    if _has_unanswered_document_confirmation(previous_messages):
        return False
    return _document_export_ready(previous_messages)


def _assistant_requests_document_confirmation(content: str) -> bool:
    lowered = content.lower()
    document_markers = ("pdf", "document", "draft", "template", "zmluv", "dokument")
    confirmation_markers = (
        "do you want",
        "would you like",
        "chcete",
        "mám pripraviť",
        "mam pripravit",
        "pripraviť",
        "pripravit",
    )
    return (
        any(marker in lowered for marker in document_markers)
        and "?" in content
        and any(marker in lowered for marker in confirmation_markers)
    )


def _is_document_email_flow_message(*, content: str, previous_messages: list[Message]) -> bool:
    normalized = _canonicalize_document_text(content)
    if _is_document_email_request(normalized):
        return True
    if _last_assistant_requested_document_email_confirmation(previous_messages) and _extract_email_address(content):
        return True
    if not _is_affirmative_reply(normalized):
        return False
    return _last_assistant_requested_document_email_confirmation(previous_messages)


def _is_document_email_request(normalized: str) -> bool:
    document_hit = any(token in normalized for token in ("dokument", "document", "pdf", "zmluv"))
    email_hit = any(token in normalized for token in ("email", "e-mail", "mail", "mailom"))
    send_hit = any(
        token in normalized
        for token in ("poslat", "posli", "odoslat", "odosli", "send", "forward", "preposlat")
    )
    return document_hit and email_hit and send_hit


def _last_assistant_requested_document_email_confirmation(messages: list[Message]) -> bool:
    for message in reversed(messages):
        if message.role == MessageRole.USER:
            continue
        if message.role != MessageRole.ASSISTANT:
            continue
        normalized = _canonicalize_document_text(message.content)
        return (
            "potvrdte odoslanie dokumentov" in normalized
            or "confirm sending all generated documents" in normalized
        )
    return False


def _last_document_email_confirmation_recipient(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == MessageRole.USER:
            continue
        if message.role != MessageRole.ASSISTANT:
            continue
        normalized = _canonicalize_document_text(message.content)
        if (
            "potvrdte odoslanie dokumentov" in normalized
            or "confirm sending all generated documents" in normalized
        ):
            return _extract_email_address(message.content)
        return ""
    return ""


def _extract_email_address(content: str) -> str:
    match = re.search(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", content)
    if match is None:
        return ""
    return match.group(0).strip(".,;:()[]{}<>").lower()


def _handle_document_email_flow(
    *,
    session_id: UUID,
    session: Session,
    content: str,
    previous_messages: list[Message],
) -> str:
    user = _document_user_profile_for_session(session)
    explicit_recipient = _extract_email_address(content)
    pending_recipient = _last_document_email_confirmation_recipient(previous_messages)
    profile_recipient = user.email.strip().lower() if user is not None else ""
    recipient = explicit_recipient or pending_recipient or profile_recipient
    if not recipient:
        return (
            "V profile nemate ulozeny e-mail. Najprv prosim doplnte e-mail v profile "
            "a potom poziadajte o odoslanie dokumentov znova."
        )
    normalized = _canonicalize_document_text(content)
    confirmation_requested = _last_assistant_requested_document_email_confirmation(previous_messages)
    confirmed = not explicit_recipient and _is_affirmative_reply(normalized) and confirmation_requested
    if explicit_recipient and confirmation_requested:
        return (
            f"Chcete poslat vsetky vygenerovane dokumenty na e-mail {recipient}? "
            "Potvrdte odoslanie dokumentov odpovedou ano."
        )
    if not confirmed:
        return (
            f"Chcete poslat vsetky vygenerovane dokumenty na e-mail {recipient}? "
            "Potvrdte odoslanie dokumentov odpovedou ano."
        )
    result = _get_or_build_session_result(session_id)
    if result is None:
        result = _build_direct_reply_result(
            session_id=session_id,
            session=session,
            messages=previous_messages,
            lawyer_message="",
        )
    assets = _build_document_export_assets(
        session_id=session_id,
        messages=previous_messages,
        result=result,
        country=session.country,
        language=session.language,
        user_profile=user,
    )
    email_id, attachment_count = _enqueue_session_documents_email(
        session=session,
        result=result,
        assets=assets,
        recipient=recipient,
    )
    return (
        f"Dokumenty boli zaradene na odoslanie na e-mail {recipient}. "
        f"Pocet priloh: {attachment_count}. ID e-mailu: {email_id}."
    )


def _document_generation_progress_events(
    *,
    session: Session,
    messages: list[Message],
    lawyer_message: str,
) -> list[dict[str, object]]:
    visible_text = _user_visible_text(lawyer_message)
    if _assistant_requests_user_reply(visible_text):
        return []
    document_names = _document_progress_names(
        messages=messages,
        lawyer_message=lawyer_message,
        country=session.country,
        language=session.language,
    )
    if len(document_names) < 2:
        return []
    lowered_visible = visible_text.lower()
    if not _document_export_ready(messages) and not any(
        marker in lowered_visible
        for marker in ("pripravil som", "pripravila som", "prepared", "ready", "hotove", "hotový")
    ):
        return []
    return [
        {
            "stage": "document_ready",
            "message": _document_progress_message(
                document_name=document_name,
                country=session.country,
                language=session.language,
            ),
            "details": {"document_name": document_name},
        }
        for document_name in document_names
    ]


def _document_progress_names(
    *,
    messages: list[Message],
    lawyer_message: str,
    country: str,
    language: str | None,
) -> list[str]:
    visible_text = _user_visible_text(lawyer_message)
    extracted = _extract_document_titles_from_text(visible_text)
    if len(extracted) >= 2:
        return extracted
    discussion_messages = [
        message.content for message in messages if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
    ]
    context_lines = _normalize_document_lines("\n".join([*discussion_messages, visible_text]))
    source = _pick_document_message([visible_text, *discussion_messages])
    case_update = _extract_case_update(source)
    if case_update is None:
        for content in reversed(discussion_messages):
            case_update = _extract_case_update(content)
            if case_update is not None:
                break
    document_kind = _detect_document_kind(context_lines, case_update)
    defaults = _default_document_titles_for_kind(
        document_kind=document_kind,
        country=country,
        language=language,
    )
    if len(defaults) >= 2:
        return defaults
    return extracted


def _extract_document_titles_from_text(content: str) -> list[str]:
    if not content.strip():
        return []
    names: list[str] = []
    seen: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        normalized = re.sub(r"^\d+\.\s*", "", line)
        normalized = normalized.strip("* ").strip()
        if ":" in normalized:
            normalized = normalized.split(":", 1)[0].strip()
        display_name = _repair_common_mojibake(normalized)
        if not _looks_like_document_title(display_name):
            continue
        key = _canonicalize_document_text(display_name)
        if key in seen:
            continue
        seen.add(key)
        names.append(display_name)
    return names


def _looks_like_document_title(value: str) -> bool:
    lowered = _canonicalize_document_text(value)
    non_document_titles = (
        "zhrnutie",
        "zhrnutie pripadu",
        "summary",
        "case summary",
        "chybajuce informacie",
        "chybajuce informacie dokumenty",
        "missing information",
        "missing information documents",
        "rizika",
        "rizika slabe miesta",
        "risks",
        "risk",
        "weak points",
        "navrhovany postup",
        "recommended next steps",
        "next steps",
        "dalsi postup",
        "navrh terminu dalsej konzultacie",
        "next consultation",
        "export",
        "download",
        "stiahnutie",
    )
    if lowered in non_document_titles or any(
        lowered.startswith(f"{title} ") for title in non_document_titles
    ):
        return False
    document_prefixes = (
        "zmluva",
        "inventarny zoznam",
        "inventar",
        "odovzdavaci protokol",
        "preberaci protokol",
        "potvrdenie",
        "zapisnica",
        "rozhodnutie",
        "aktualizacia",
        "aktualizovane",
        "podanie na orsr",
        "navrh rozhodnutia",
        "splnomocnenie",
        "plnomocenstvo",
        "power of attorney",
        "share transfer agreement",
        "sole shareholder decision",
        "updated articles",
        "registry filing",
        "founding deed",
    )
    document_phrases = (
        "inventarny zoznam",
        "zoznam vybavenia",
        "odovzdanie bytu",
        "prevzatie bytu",
        "potvrdenie o prevzati",
        "protokol o odovzdani",
        "protokol o prevzati",
        "spolocenska zmluva",
        "spolocenskej zmluvy",
        "zakladatelska listina",
        "zakladatelskej listiny",
        "podanie na orsr",
        "obchodneho registra",
        "splnomocnenie",
        "plnomocenstvo",
        "power of attorney",
        "share transfer agreement",
        "sole shareholder decision",
        "updated articles",
        "founding deed",
        "registry filing",
    )
    exclusion_tokens = (
        "text ",
        "textu ",
        "obsah ",
        "prakticky postup",
        "odhad trvania",
        "estimated timing",
        "poznamka",
        "podklady",
        "prilohy",
        "potvrdzuje",
        "prenajima",
        "prenajíma",
        "zmluvne strany",
        "predmet zmluvy",
        "doba najmu",
        "najomne",
        "skoncenie najmu",
        "vypovedna lehota",
        "podpis",
    )
    if any(token in lowered for token in exclusion_tokens):
        return False
    if lowered.startswith(document_prefixes) or any(token in lowered for token in document_phrases):
        return True
    signal_groups = (
        ("prevode", "podiel"),
        ("kupno", "predajn", "zmluv"),
        ("kupna", "zmluv"),
        ("predajna", "zmluv"),
        ("darovac", "zmluv"),
        ("potvrdenie", "zaplat"),
        ("potvrdenie", "uhrad"),
        ("power", "attorney"),
        ("splnomoc", "verzia"),
        ("pisnica", "rozhodnut"),
        ("aktualiz", "zmluv"),
        ("inventar", "zoznam"),
        ("zoznam", "vybaven"),
        ("potvrdenie", "prevzati"),
        ("odovzd", "byt"),
        ("prevzat", "byt"),
        ("protokol", "odovzd"),
        ("protokol", "prevzat"),
        ("spolocensk", "zmluv"),
        ("spoloensk", "zmluv"),
        ("zakladatelsk", "listin"),
        ("podanie", "orsr"),
        ("share", "transfer"),
        ("sole", "decision"),
        ("updated", "articles"),
        ("registry", "filing"),
        ("founding", "deed"),
    )
    return any(all(token in lowered for token in group) for group in signal_groups)


def _repair_common_mojibake(value: str) -> str:
    repaired = value
    for _ in range(3):
        if not any(marker in repaired for marker in ("Ã", "Â", "Ä", "Å", "â")):
            return repaired
        next_value = ""
        for source_encoding in ("latin-1", "cp1252"):
            try:
                candidate = repaired.encode(source_encoding, errors="ignore").decode("utf-8", errors="ignore").strip()
            except UnicodeError:
                continue
            if candidate:
                next_value = candidate
                break
        if not next_value or next_value == repaired:
            return repaired
        repaired = next_value
    return repaired


def _canonicalize_document_text(value: str) -> str:
    repaired = _repair_common_mojibake(value)
    normalized = unicodedata.normalize("NFKD", repaired.casefold())
    ascii_only = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_only).strip()

def _default_document_titles_for_kind(
    *, document_kind: str, country: str, language: str | None
) -> list[str]:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if document_kind != "share_transfer":
        return []
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return [
            "Zmluva o prevode obchodneho podielu",
            "Rozhodnutie jedineho spolocnika / zapisnica",
            "Spolocenska zmluva",
        ]
    return [
        "Share transfer agreement",
        "Sole shareholder decision / meeting minutes",
        "Articles of association",
    ]


def _document_progress_message(
    *, document_name: str, country: str, language: str | None
) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"Pripravil som dokument: {document_name}."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return f"Pripravil jsem dokument: {document_name}."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return f"Dokument vorbereitet: {document_name}."
    return f"Prepared document: {document_name}."


def _document_package_ready_message(
    *, country: str, language: str | None, document_names: list[str], status_prefix: bool = False
) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        intro = (
            "Stav dokumentov: balik dokumentov je pripraveny na export a stiahnutie."
            if status_prefix
            else "Balik dokumentov je pripraveny na export a stiahnutie."
        )
        label = "Pripravene dokumenty:"
    elif normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        intro = (
            "Stav dokumentu: balik dokumentu je pripraven k exportu a stazeni."
            if status_prefix
            else "Balik dokumentu je pripraven k exportu a stazeni."
        )
        label = "Pripravene dokumenty:"
    elif normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        intro = (
            "Dokumentenstatus: Das Dokumentenpaket ist fuer Export und Download bereit."
            if status_prefix
            else "Das Dokumentenpaket ist fuer Export und Download bereit."
        )
        label = "Vorbereitete Dokumente:"
    else:
        intro = (
            "Document status: the document package is ready for export and download."
            if status_prefix
            else "The document package is ready for export and download."
        )
        label = "Prepared documents:"
    if not document_names:
        return intro
    items = "\n".join(f"{index}. {name}" for index, name in enumerate(document_names, start=1))
    return f"{intro}\n\n{label}\n{items}"


def _document_status_message(*, country: str, language: str | None, status_text: str) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"Stav dokumentov: {status_text}"
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return f"Stav dokumentu: {status_text}"
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return f"Dokumentenstatus: {status_text}"
    return f"Document status: {status_text}"


def _looks_like_processing_placeholder_reply(content: str) -> bool:
    normalized = " ".join(_user_visible_text(content).lower().split())
    wait_markers = (
        "prosim, dajte mi chvilu",
        "prosim dajte mi chvilu",
        "dajte mi chvilu",
        "prosim, pockajte",
        "prosim pockajte",
        "please wait",
        "give me a moment",
        "one moment",
        "working on it",
        "dokoncim navrh",
        "dokoncim pripravu",
        "pripravim ich na export",
    )
    return any(marker in normalized for marker in wait_markers)


def _is_document_status_request(content: str) -> bool:
    normalized = " ".join(content.lower().split())
    explicit_phrases = (
        "status dokument",
        "status dokumentov",
        "stav dokument",
        "stav dokumentov",
        "je dokument hotovy",
        "su dokumenty hotove",
        "su dokumenty pripravene",
        "je balik pripraveny",
        "is the document ready",
        "status of the document",
        "status of documents",
        "document status",
    )
    if any(phrase in normalized for phrase in explicit_phrases):
        return True
    status_tokens = ("status", "stav", "ready", "hotov", "pripraven", "export", "download", "stiahn")
    document_tokens = ("dokument", "dokumenty", "balik", "package", "pdf", "zip", "draft", "navrh")
    return any(token in normalized for token in status_tokens) and any(
        token in normalized for token in document_tokens
    )


def _finalize_document_ready_reply_if_needed(
    *,
    session: Session,
    messages: list[Message],
    lawyer_content: str,
) -> str:
    visible_text = _user_visible_text(lawyer_content)
    if _assistant_requests_user_reply(visible_text):
        return lawyer_content.strip()
    if not _document_generation_requested(messages) or not _document_generation_confirmed(messages):
        return lawyer_content.strip()
    if not _looks_like_processing_placeholder_reply(visible_text):
        return lawyer_content.strip()
    document_names = _document_progress_names(
        messages=messages,
        lawyer_message=lawyer_content,
        country=session.country,
        language=session.language,
    )
    return _document_package_ready_message(
        country=session.country,
        language=session.language,
        document_names=document_names,
    ).strip()


def _current_turn_confirms_document_generation(
    content: str,
    previous_messages: list[Message],
) -> bool:
    normalized = _canonicalize_document_text(content)
    if not _has_unanswered_document_confirmation(previous_messages):
        return False
    return _is_affirmative_reply(normalized) or _is_explicit_document_request(normalized)


def _build_direct_reply_result(
    *,
    session_id: UUID,
    session: Session,
    messages: list[Message],
    lawyer_message: str,
    route: RoutedLLMClient | None = None,
    legal_source_citations: list[dict[str, object]] | None = None,
) -> SessionResult:
    visible_text = _user_visible_text(lawyer_message)
    document_requested = _document_generation_requested(messages)
    document_confirmed = _document_generation_confirmed(messages)
    document_ready = _document_export_ready(messages)
    rationale = (
        "Direct lawyer reply prepared for session export."
        if visible_text
        else "Direct lawyer reply stored for session export."
    )
    metadata = build_session_result_metadata(
        session=session,
        messages=messages,
        final_recommendation=visible_text or f"Direct lawyer reply for session {session_id}.",
        base_metadata={
            "message_count": len(messages),
            "mode": "direct_reply",
            "country": session.country,
            "language": session.language or "",
            "document_requested": document_requested,
            "document_confirmed": document_confirmed,
            "document_ready": document_ready,
            "legal_source_citations": legal_source_citations or [],
        },
        routed_model_name=route.model if route is not None else None,
    )
    return SessionResult(
        final_recommendation=visible_text or f"Direct lawyer reply for session {session_id}.",
        judge_rationale=rationale,
        citations=_merge_session_citations(generic_citations=[], metadata=metadata),
        metadata=metadata,
    )


def _build_document_status_reply(
    *,
    session: Session,
    messages: list[Message],
    result: SessionResult | None,
) -> str:
    metadata = result.metadata if result is not None else {}
    document_requested = bool(metadata.get("document_requested"))
    document_confirmed = bool(metadata.get("document_confirmed"))
    document_ready = bool(metadata.get("document_ready"))
    lawyer_message = result.final_recommendation if result is not None else ""
    document_names = _document_progress_names(
        messages=messages,
        lawyer_message=lawyer_message,
        country=session.country,
        language=session.language,
    )
    if document_ready:
        return _document_package_ready_message(
            country=session.country,
            language=session.language,
            document_names=document_names,
            status_prefix=True,
        )
    if document_confirmed:
        return _document_status_message(
            country=session.country,
            language=session.language,
            status_text="balik dokumentov sa este pripravuje, ale export zatial nie je hotovy."
            if (session.country or "").strip().upper() == "SK" or (session.language or "").strip().lower().startswith("sk")
            else "the document package is still being prepared and the export is not ready yet.",
        )
    if document_requested:
        return _document_status_message(
            country=session.country,
            language=session.language,
            status_text="dokument bol vyziadany, ale stale chyba potvrdenie alebo doplnujuce udaje."
            if (session.country or "").strip().upper() == "SK" or (session.language or "").strip().lower().startswith("sk")
            else "a document was requested, but confirmation or additional details are still missing.",
        )
    return _document_status_message(
        country=session.country,
        language=session.language,
        status_text="pre tuto session este nebol pripraveny ziaden dokument."
        if (session.country or "").strip().upper() == "SK" or (session.language or "").strip().lower().startswith("sk")
        else "no document has been prepared for this session yet.",
    )


def _document_completion_processing_events(
    *,
    session: Session,
    messages: list[Message],
    result: SessionResult,
) -> list[dict[str, object]]:
    if not bool(result.metadata.get("document_ready")):
        return []
    document_names = _document_progress_names(
        messages=messages,
        lawyer_message=result.final_recommendation,
        country=session.country,
        language=session.language,
    )
    return [
        {
            "stage": "document_package_ready",
            "message": _document_package_ready_message(
                country=session.country,
                language=session.language,
                document_names=document_names,
            ),
            "details": {
                "document_names": document_names,
                "status": "ready",
            },
        }
    ]


def _legal_source_citations_from_processing_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for event in events:
        details = event.get("details")
        if not isinstance(details, dict):
            continue
        raw_citations = details.get("citations")
        if not isinstance(raw_citations, list):
            continue
        for raw_item in raw_citations:
            if not isinstance(raw_item, dict):
                continue
            source_type = str(raw_item.get("source_type") or "other").strip() or "other"
            source_id = str(raw_item.get("source_id") or "").strip()
            source_url = str(raw_item.get("source_url") or "").strip()
            title = str(raw_item.get("title") or raw_item.get("citation_label") or source_id or source_url).strip()
            if not title:
                continue
            key = (source_type, source_id, source_url or title)
            if key in seen:
                continue
            seen.add(key)
            citations.append({**raw_item, "source_type": source_type, "title": title})
    return citations


def _document_generation_requested(messages: list[Message]) -> bool:
    for index, message in enumerate(messages):
        if message.role != MessageRole.USER:
            continue
        if _user_requested_document_generation(content=message.content, previous_messages=messages[:index]):
            return True
    return any(
        _assistant_requests_document_confirmation(message.content)
        for message in messages
        if message.role == MessageRole.ASSISTANT
    )


def _document_generation_confirmed(messages: list[Message]) -> bool:
    for index, message in enumerate(messages):
        if message.role != MessageRole.USER:
            continue
        previous_messages = messages[:index]
        normalized = _canonicalize_document_text(message.content)
        if _is_final_document_generation_command(normalized) and _document_generation_requested(messages[: index + 1]):
            return True
        if not any(
            prior.role == MessageRole.ASSISTANT and _assistant_requests_document_confirmation(prior.content)
            for prior in previous_messages
        ):
            continue
        if _is_affirmative_reply(normalized) or _is_explicit_document_request(normalized):
            return True
    return False


def _is_final_document_generation_command(normalized: str) -> bool:
    normalized = _canonicalize_document_text(normalized)
    final_markers = ("vygeneruj", "generuj", "priprav", "konecnu", "konecna", "finalny", "finalnu", "finalne")
    document_markers = ("pdf", "dokument", "document")
    return any(token in normalized for token in final_markers) and any(
        token in normalized for token in document_markers
    )


def _document_export_ready(messages: list[Message]) -> bool:
    if not _document_generation_confirmed(messages):
        return False
    assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]
    if not assistant_messages:
        return False
    last_assistant = assistant_messages[-1]
    if _assistant_requests_document_confirmation(last_assistant.content):
        return False
    if _looks_like_processing_placeholder_reply(last_assistant.content):
        return False
    if any(_extract_case_update(message.content) is not None for message in assistant_messages):
        return True
    visible_text = _user_visible_text(last_assistant.content).lower()
    ready_markers = (
        "pripravil som",
        "pripravila som",
        "pripraven",
        "pripraveny",
        "pripravene",
        "stiahnutie",
        "prepared the final",
        "prepared the draft",
        "draft is ready",
        "ready for download",
        "navrh zmluvy",
        "predzalobna vyzva",
        "predžalobná výzva",
        "legal summary",
        "pravne zhrnutie",
    )
    if any(marker in visible_text for marker in ready_markers):
        return True
    return "?" not in visible_text and bool(visible_text.strip())


def _contains_case_update_json(content: str) -> bool:
    return "case_update_json" in content.lower()


def _user_visible_text(content: str) -> str:
    bounds = _technical_payload_bounds(content)
    if bounds is None:
        return _strip_user_visible_technical_trailer(content)
    start_index, _end_index, _extension = bounds
    return _strip_user_visible_technical_trailer(content[:start_index])


def _attach_technical_payload_to_case_if_needed(*, session: Session, content: str) -> str:
    payload = _extract_hidden_technical_payload(content)
    if payload is None:
        return content.strip()
    case_id = (session.case_id or "").strip()
    if not case_id:
        return content.strip()
    visible_text = _user_visible_text(content)
    if _contains_case_technical_document_notice(visible_text):
        return content.strip()
    doc_id = _persist_case_technical_payload(
        session=session,
        payload=payload.content,
        extension=payload.extension,
    )
    if doc_id is None:
        return content.strip()
    document_url = _case_document_download_url(session=session, doc_id=doc_id)
    notice = _technical_payload_saved_notice(
        country=session.country,
        language=session.language,
        document_url=document_url,
    )
    technical_tail = content[payload.start_index : payload.end_index].strip()
    if visible_text:
        return f"{visible_text}\n\n{notice}\n\n{technical_tail}".strip()
    return f"{notice}\n\n{technical_tail}".strip()


def _contains_case_technical_document_notice(content: str) -> bool:
    normalized = " ".join(content.lower().split())
    return (
        "technicke udaje som ulozil do dokumentu pripadu" in normalized
        or "technické údaje som uložil do dokumentu prípadu" in normalized
        or "technical data was saved as a case document" in normalized
    )


def _persist_case_technical_payload(
    *,
    session: Session,
    payload: str,
    extension: str,
) -> str | None:
    case_id = (session.case_id or "").strip()
    if not case_id:
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"assistant-technical-{timestamp}-{uuid4().hex[:8]}.{extension}"
    try:
        store = _get_store()
        doc_id = store.add_case_document(
            case_id=case_id,
            kind="technical_payload",
            version=1,
            original_filename=filename,
            payload=payload.encode("utf-8"),
            uploaded_by_user_id=str(session.user_id) if session.user_id else None,
        )
        return doc_id if isinstance(doc_id, str) else None
    except Exception:
        _LOGGER.warning(
            "Failed to persist hidden assistant technical payload as a case document",
            extra={"case_id": case_id, "extension": extension},
            exc_info=True,
        )
        return None


def _persist_generated_case_document_if_needed(*, session: Session, content: str) -> list[str]:
    case_id = (session.case_id or "").strip()
    if not case_id:
        return []
    case_update = _extract_case_update(content)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    drafts = _generated_case_document_drafts_from_case_update(case_update, timestamp=timestamp)
    if drafts:
        return _persist_generated_case_document_drafts(session=session, case_id=case_id, drafts=drafts)
    visible_text = _user_visible_text(content).strip()
    drafts = _generated_case_document_drafts_for_storage(visible_text, timestamp=timestamp)
    if not drafts:
        if not _looks_like_fake_download_response(content):
            return []
        store = _get_store()
        if _has_generated_case_documents(store=store, case_id=case_id):
            return []
        drafts = _generated_case_document_drafts_from_previous_assistant_message(
            session=session,
            timestamp=timestamp,
        )
        if not drafts:
            return []
    return _persist_generated_case_document_drafts(session=session, case_id=case_id, drafts=drafts)


def _attach_generated_case_document_references(
    *,
    session: Session,
    content: str,
    doc_ids: list[str],
) -> str:
    references = [
        _case_document_download_url(session=session, doc_id=doc_id)
        for doc_id in doc_ids
        if doc_id.strip()
    ]
    if not references:
        return content
    reference_lines = "\n".join(
        f"Generated case document: {reference}" for reference in references
    )
    return f"{content.rstrip()}\n\n{reference_lines}"


def _persist_generated_case_document_drafts(
    *,
    session: Session,
    case_id: str,
    drafts: list[_GeneratedCaseDocumentDraft],
) -> list[str]:
    try:
        store = _get_store()
        version = _next_generated_case_document_version(store=store, case_id=case_id)
        doc_ids: list[str] = []
        for offset, draft in enumerate(drafts):
            doc_id = store.add_case_document(
                case_id=case_id,
                kind="generated_document",
                version=version + offset,
                original_filename=draft.filename,
                payload=draft.body.encode("utf-8"),
                uploaded_by_user_id=str(session.user_id) if session.user_id else None,
            )
            if isinstance(doc_id, str):
                doc_ids.append(doc_id)
        return doc_ids
    except Exception:
        _LOGGER.warning(
            "Failed to persist assistant final answer as a generated case document",
            extra={"case_id": case_id},
            exc_info=True,
        )
        return []


def _generated_case_document_drafts_from_case_update(
    case_update: dict[str, Any] | None,
    *,
    timestamp: str,
) -> list[_GeneratedCaseDocumentDraft]:
    drafts: list[_GeneratedCaseDocumentDraft] = []
    for index, entry in enumerate(_case_update_document_entries(case_update), start=1):
        body = _document_entry_content(entry)
        if not body:
            continue
        sanitized = _sanitize_generated_legal_document_body(body)
        if not sanitized:
            continue
        filename = _generated_case_document_filename_from_entry(
            entry=entry,
            body=sanitized,
            timestamp=timestamp,
            fallback_index=index,
        )
        drafts.append(_GeneratedCaseDocumentDraft(filename=filename, body=sanitized))
    return drafts


def _generated_case_document_drafts_for_storage(
    content: str,
    *,
    timestamp: str,
) -> list[_GeneratedCaseDocumentDraft]:
    power_of_attorney_drafts = _bilingual_power_of_attorney_drafts(content, timestamp=timestamp)
    if power_of_attorney_drafts:
        return power_of_attorney_drafts

    section_drafts = _generated_case_document_drafts_from_visible_sections(
        content,
        timestamp=timestamp,
    )
    if section_drafts:
        return section_drafts

    if _looks_like_generated_case_document_for_storage(content):
        document_body = _generated_case_document_body_for_storage(content)
    else:
        document_body = _synthesized_generated_case_document_body_for_storage(content)
    if not document_body:
        return []
    return [
        _GeneratedCaseDocumentDraft(
            filename=_generated_case_document_filename_for_storage(document_body, timestamp=timestamp),
            body=document_body,
        )
    ]


def _generated_case_document_drafts_from_visible_sections(
    content: str,
    *,
    timestamp: str,
) -> list[_GeneratedCaseDocumentDraft]:
    sections = _exportable_visible_document_sections_for_storage(content)
    if not sections:
        return []
    return [
        _GeneratedCaseDocumentDraft(
            filename=_generated_case_document_filename_for_storage(
                section["content"],
                timestamp=timestamp,
            ),
            body=section["content"],
        )
        for section in sections
        if section.get("content")
    ]


def _generated_case_document_drafts_from_previous_assistant_message(
    *,
    session: Session,
    timestamp: str,
) -> list[_GeneratedCaseDocumentDraft]:
    session_id = getattr(session, "id", None)
    if session_id is None:
        return []
    previous_assistant_messages = [
        message.content
        for message in _repository.list_messages(session_id)
        if message.role == MessageRole.ASSISTANT
    ]
    source = _pick_document_message(previous_assistant_messages)
    if not source:
        return []
    visible_source = _user_visible_text(source).strip()
    drafts = _generated_case_document_drafts_for_storage(visible_source, timestamp=timestamp)
    if drafts:
        return drafts
    sections = _exportable_visible_document_sections_for_storage(visible_source)
    return [
        _GeneratedCaseDocumentDraft(
            filename=_generated_case_document_filename_for_storage(section["content"], timestamp=timestamp),
            body=section["content"],
        )
        for section in sections
        if section.get("content")
    ]


def _exportable_visible_document_sections_for_storage(content: str) -> list[dict[str, str]]:
    return [
        section
        for section in _extract_visible_document_sections_for_export(content)
        if section.get("content") and _looks_like_exportable_legal_document_body(section["content"])
    ]


def _document_entry_content(entry: dict[str, Any]) -> str:
    for key in ("content", "body", "text", "markdown", "document_text"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _sanitize_generated_legal_document_body(content: str) -> str:
    visible = _user_visible_text(content)
    cleaned_lines: list[str] = []
    skip_markers = (
        "case_update_json",
        "ready for export",
        "ready for download",
        "pripraveny na export",
        "pripravene na export",
        "pripraveny na stiahnutie",
        "pripravene na stiahnutie",
        "vyborne pripravim",
        "výborne pripravím",
        "pripravim splnomocnenie",
        "pripravim dokument",
        "tu je finalny navrh",
        "tu je finalny dokument",
        "technicke udaje som ulozil",
        "technical data was saved",
        "teraz pripravim oba dokumenty",
        "teraz pripravim dokumenty",
    )
    for raw_line in visible.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned_lines.append("")
            continue
        normalized = _canonicalize_document_text(line)
        if line in {"---", "___", "***"}:
            continue
        if line.startswith("```") or line.endswith("```"):
            continue
        if normalized and any(marker in normalized for marker in skip_markers):
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = line.strip("* ")
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"__([^_]+)__", r"\1", line)
        cleaned_lines.append(line.strip())
    while cleaned_lines and not cleaned_lines[0].strip():
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
    collapsed: list[str] = []
    previous_blank = False
    for line in cleaned_lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = is_blank
    return "\n".join(collapsed).strip()


def _generated_case_document_filename_from_entry(
    *,
    entry: dict[str, Any],
    body: str,
    timestamp: str,
    fallback_index: int,
) -> str:
    raw_name = str(entry.get("filename") or entry.get("path") or "").strip()
    if raw_name:
        stem = Path(raw_name).stem.strip()
        if stem:
            return f"{_filename_slug_for_generated_case_document(stem)}_{timestamp}.pdf"
    title = _document_asset_title(entry=entry, language=str(entry.get("language") or ""), fallback_index=fallback_index)
    if title:
        slug = _filename_slug_for_generated_case_document(_generated_case_document_legal_title(title))
        if slug:
            return f"{slug}_{timestamp}.pdf"
    return _generated_case_document_filename_for_storage(body, timestamp=timestamp)


def _bilingual_power_of_attorney_drafts(
    content: str,
    *,
    timestamp: str,
) -> list[_GeneratedCaseDocumentDraft]:
    normalized = _canonicalize_document_text(content)
    if not (
        "splnomocnenie" in normalized
        and "power of attorney" in normalized
        and any(token in normalized for token in ("anglick", "english", "en verzi", "en version"))
    ):
        return []
    facts = _extract_power_of_attorney_facts(content)
    if not facts:
        return []
    return [
        _GeneratedCaseDocumentDraft(
            filename=f"splnomocnenie_sk_{timestamp}.pdf",
            body=_render_slovak_power_of_attorney(facts),
        ),
        _GeneratedCaseDocumentDraft(
            filename=f"power_of_attorney_en_{timestamp}.pdf",
            body=_render_english_power_of_attorney(facts),
        ),
    ]


def _extract_power_of_attorney_facts(content: str) -> dict[str, str]:
    facts = {
        "agent": _extract_labeled_value(content, "Splnomocnenec", "Attorney-in-fact", "Agent"),
        "company": _extract_labeled_value(content, "Spolocnost", "Spoločnosť", "Company"),
        "address": _extract_labeled_value(content, "Adresa", "Address"),
        "scope": _extract_labeled_value(content, "Prava", "Práva", "Rights", "Scope"),
    }
    facts = {key: value for key, value in facts.items() if value}
    if not any(facts.get(key) for key in ("agent", "company", "scope")):
        return {}
    return facts


def _extract_labeled_value(content: str, *labels: str) -> str:
    lines = content.splitlines()
    for index, raw_line in enumerate(lines):
        line = raw_line.strip().strip("-* ")
        for label in labels:
            match = re.match(rf"^{re.escape(label)}\s*:\s*(?P<value>.+)$", line, flags=re.IGNORECASE)
            if match:
                value = match.group("value").strip().strip(".")
                if value:
                    return value
            if re.match(rf"^{re.escape(label)}\s*:\s*$", line, flags=re.IGNORECASE):
                value = _next_non_empty_document_line(lines[index + 1 :])
                if value:
                    return value
    return ""


def _next_non_empty_document_line(lines: list[str]) -> str:
    for raw_line in lines:
        value = raw_line.strip().strip("-* ").strip(".")
        if value:
            return value
    return ""


def _power_of_attorney_principal(facts: dict[str, str]) -> str:
    company = facts.get("company", "").strip()
    address = facts.get("address", "").strip()
    if company and address:
        return f"{company}, {address}"
    return company or "Doplniť splnomocniteľa"


def _render_slovak_power_of_attorney(facts: dict[str, str]) -> str:
    principal = _power_of_attorney_principal(facts)
    agent = facts.get("agent", "Doplniť splnomocnenca")
    scope = facts.get("scope", "Doplniť rozsah splnomocnenia")
    return "\n".join(
        [
            "Splnomocnenie",
            "",
            f"Splnomocniteľ: {principal}",
            f"Splnomocnenec: {agent}",
            "",
            "1. Predmet splnomocnenia",
            (
                "Splnomocniteľ týmto podľa § 31 a nasl. zákona č. 40/1964 Zb. "
                "Občiansky zákonník udeľuje splnomocnencovi plnú moc konať v mene "
                "splnomocniteľa v rozsahu uvedenom v tomto splnomocnení."
            ),
            "",
            "2. Rozsah oprávnenia",
            scope,
            "",
            "3. Vyhlásenia",
            (
                "Splnomocnenec je oprávnený vykonať všetky úkony, podpisovať potrebné "
                "listiny a preberať alebo odovzdávať dokumenty, ak súvisia s uvedeným "
                "rozsahom splnomocnenia. Splnomocnenie sa udeľuje do jeho písomného "
                "odvolania, ak nie je v samostatnej dohode uvedené inak."
            ),
            "",
            "V ____________________, dňa ____________________",
            "",
            "Splnomocniteľ: ______________________________",
            "",
            "Splnomocnenec: ______________________________",
        ]
    )


def _render_english_power_of_attorney(facts: dict[str, str]) -> str:
    principal = _power_of_attorney_principal(facts)
    agent = facts.get("agent", "To be completed")
    scope = facts.get("scope", "To be completed")
    return "\n".join(
        [
            "Power of Attorney",
            "",
            f"Principal: {principal}",
            f"Attorney-in-fact: {agent}",
            "",
            "1. Grant of authority",
            (
                "The Principal hereby authorizes the Attorney-in-fact to act on behalf "
                "of the Principal within the scope stated in this power of attorney."
            ),
            "",
            "2. Scope of authority",
            scope,
            "",
            "3. Declarations",
            (
                "The Attorney-in-fact may perform all acts, sign necessary documents, "
                "and receive or deliver documents connected with the stated scope of "
                "authority. This power of attorney remains valid until revoked in "
                "writing unless a separate agreement provides otherwise."
            ),
            "",
            "Place ____________________, date ____________________",
            "",
            "Principal: ______________________________",
            "",
            "Attorney-in-fact: ______________________________",
        ]
    )


def _looks_like_generated_case_document_for_storage(content: str) -> bool:
    normalized = _canonicalize_document_text(content)
    if not normalized or "?" in normalized[-180:]:
        return False
    document_markers = (
        "splnomocnenie",
        "power of attorney",
        "potvrdenie",
        "zmluva",
        "vyzva",
        "zaloba",
        "navrh",
        "dohoda",
        "contract",
        "agreement",
    )
    ready_markers = (
        "dokument je pripraven",
        "dokumenty su pripravene",
        "finalne verzie",
        "finalna verzia",
        "konecna verzia",
        "na stiahnutie",
        "format pdf",
        "tu je",
        "tu su",
    )
    body_markers = (
        "tymto",
        "podpis",
        "attorney",
        "rights",
        "company",
        "splnomocnenec",
        "splnomocnitel",
        "zmluvne strany",
    )
    return (
        any(marker in normalized for marker in document_markers)
        and any(marker in normalized for marker in ready_markers)
        and any(marker in normalized for marker in body_markers)
    )


def _generated_case_document_body_for_storage(content: str) -> str:
    lines = content.strip().splitlines()
    cleaned: list[str] = []
    skip_markers = (
        "spracovanie stale prebieha",
        "dokument je pripraven",
        "dokumenty su pripravene",
        "dokumentu su pripravene",
        "pripraveny na stiahnutie",
        "pripravene na stiahnutie",
        "tu su finalne verzie",
        "teraz ich vygenerujem",
        "prosim chvilu pockajte",
        "tu su finálne verzie",
    )
    for line in lines:
        stripped = line.strip()
        normalized = _canonicalize_document_text(stripped)
        if normalized and any(marker in normalized for marker in skip_markers):
            continue
        stripped = re.sub(r"^(?:[A-Za-z]+Slovakia|LawyerSlovakia)\s*:\s*", "", stripped).strip()
        if not stripped:
            continue
        cleaned.append(stripped)
    body = "\n".join(cleaned).strip()
    return body


def _synthesized_generated_case_document_body_for_storage(content: str) -> str:
    normalized = _canonicalize_document_text(content)
    if (
        "potvrdenie" in normalized
        and any(token in normalized for token in ("pozic", "pozick", "pozical", "dlznik", "dlznika"))
        and any(marker in normalized for marker in ("na stiahnutie", "pripravil som navrh", "pripravim finalne"))
    ):
        if "?" in normalized[-180:]:
            return ""
        visible_lines = [line.strip() for line in _user_visible_text(content).splitlines()]
        start_index = next(
            (
                index
                for index, line in enumerate(visible_lines)
                if "potvrdenie o pozicke" in _canonicalize_document_text(line)
            ),
            -1,
        )
        if start_index >= 0:
            body = "\n".join(line for line in visible_lines[start_index:] if line).strip()
            if body:
                return body
    if not (
        "potvrdenie" in normalized
        and any(token in normalized for token in ("zaplat", "uhrad", "platb"))
        and any(marker in normalized for marker in ("format pdf", "na stiahnutie", "pripravim finalne"))
    ):
        return ""
    if "?" in normalized[-180:]:
        return ""

    facts = _extract_document_facts(content.splitlines())
    lines = _build_slovak_payment_confirmation_lines(facts)
    return "\n".join(lines).strip()


def _generated_case_document_filename_for_storage(content: str, *, timestamp: str) -> str:
    for title in _extract_document_titles_from_text(content):
        slug = _filename_slug_for_generated_case_document(_generated_case_document_legal_title(title))
        if slug:
            return f"{slug}_{timestamp}.pdf"
    for line in content.splitlines():
        title = _generated_case_document_legal_title(line.strip().strip("*#:- "))
        if title:
            slug = _filename_slug_for_generated_case_document(title)
            if slug:
                return f"{slug}_{timestamp}.pdf"
    return f"generated_document_{timestamp}.pdf"


def _generated_case_document_legal_title(value: str) -> str:
    title = re.sub(r"\([^)]*(?:verzia|version|jazyk|language)[^)]*\)", "", value, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title.strip().strip("*#:- "))
    normalized = _canonicalize_document_text(title)
    if "power of attorney" in normalized:
        return "Power of Attorney"
    if "splnomocnenie" in normalized or "plnomocenstvo" in normalized:
        return "Splnomocnenie"
    if "potvrdenie" in normalized and any(token in normalized for token in ("pozic", "pozick", "pozical")):
        return "Potvrdenie o pozicke"
    if "potvrdenie" in normalized and any(token in normalized for token in ("zaplat", "uhrad", "platb")):
        return "Potvrdenie o zaplatení"
    return title


def _filename_slug_for_generated_case_document(value: str) -> str:
    without_accents = unicodedata.normalize("NFKD", value)
    ascii_text = without_accents.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug[:80].strip("_")


def _next_generated_case_document_version(*, store: ApiDatabaseStore, case_id: str) -> int:
    list_case_documents = getattr(store, "list_case_documents", None)
    if not callable(list_case_documents):
        return 1
    versions = [
        int(getattr(document, "version", 0) or 0)
        for document in list_case_documents(case_id=case_id)
        if getattr(document, "kind", "") == "generated_document"
    ]
    return (max(versions) + 1) if versions else 1


def _has_generated_case_documents(*, store: ApiDatabaseStore, case_id: str) -> bool:
    list_case_documents = getattr(store, "list_case_documents", None)
    if not callable(list_case_documents):
        return False
    return any(
        getattr(document, "kind", "") == "generated_document"
        for document in list_case_documents(case_id=case_id)
    )


def _case_document_download_url(*, session: Session, doc_id: str) -> str:
    case_id = quote((session.case_id or "").strip(), safe="")
    encoded_doc_id = quote(doc_id, safe="")
    url = f"/v1/cases/{case_id}/documents/{encoded_doc_id}"
    if session.user_id is not None:
        url = f"{url}?user_id={quote(str(session.user_id), safe='')}"
    return url


def _technical_payload_saved_notice(*, country: str, language: str | None, document_url: str) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return f"Technické údaje som uložil do dokumentu prípadu: {document_url}"
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return f"Technické údaje jsem uložil do dokumentu případu: {document_url}"
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return f"Technische Daten wurden als Falldokument gespeichert: {document_url}"
    return f"Technical data was saved as a case document: {document_url}"


def _extract_hidden_technical_payload(content: str) -> _TechnicalPayloadAsset | None:
    bounds = _technical_payload_bounds(content)
    if bounds is None:
        return None
    start_index, end_index, extension = bounds
    raw_payload = content[start_index:end_index].strip()
    payload = _normalize_technical_payload_for_storage(raw_payload, extension=extension)
    if not payload:
        return None
    return _TechnicalPayloadAsset(
        content=payload,
        extension=extension,
        start_index=start_index,
        end_index=end_index,
    )


def _normalize_technical_payload_for_storage(raw_payload: str, *, extension: str) -> str:
    if extension == "json":
        for start_char in ("{", "["):
            json_start = raw_payload.find(start_char)
            if json_start < 0:
                continue
            json_payload = _extract_json_value(raw_payload, json_start)
            if json_payload is None:
                continue
            try:
                decoded = json.loads(json_payload)
            except json.JSONDecodeError:
                continue
            return json.dumps(decoded, ensure_ascii=False, indent=2)
    if extension == "xml":
        fenced = re.match(r"^```(?:xml)?\s*(.*?)\s*```$", raw_payload, flags=re.IGNORECASE | re.DOTALL)
        return (fenced.group(1) if fenced else raw_payload).strip()
    return raw_payload.strip()


def _strip_user_visible_technical_trailer(content: str) -> str:
    lines = _strip_user_visible_technical_lines(content.strip().splitlines())
    while lines:
        candidate = lines[-1].strip()
        normalized = re.sub(r"\s+", " ", candidate.lower())
        if _looks_like_technical_visible_line(normalized):
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def _strip_user_visible_technical_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    pending_download_intro = False
    for line in lines:
        stripped = line.strip()
        normalized = re.sub(r"\s+", " ", stripped.lower()) if stripped else ""
        if _looks_like_fake_download_intro(normalized):
            pending_download_intro = True
            continue
        if _looks_like_fake_download_link(stripped):
            continue
        if pending_download_intro and not stripped:
            continue
        if pending_download_intro:
            pending_download_intro = False
        cleaned.append(line)
    return cleaned


def _looks_like_technical_visible_line(normalized_line: str) -> bool:
    if not normalized_line:
        return False
    technical_prefixes = (
        "tu je json",
        "tu je machine",
        "tu je technicky",
        "here is the json",
        "below is the json",
        "here is the machine",
        "machine payload",
        "technical payload",
        "case_update_json",
        "technicke udaje som ulozil do dokumentu pripadu",
        "technical data was saved as a case document",
        "technische daten wurden als falldokument gespeichert",
    )
    technical_fragments = (
        "json pre uchovanie prípadu",
        "json pre uchovanie pripadu",
        "json for case persistence",
        "json for storing the case",
        "machine payload",
        "technical payload",
        "/v1/cases/",
    )
    return normalized_line.startswith(technical_prefixes) or any(
        fragment in normalized_line for fragment in technical_fragments
    )


def _looks_like_fake_download_intro(normalized_line: str) -> bool:
    if not normalized_line:
        return False
    markers = (
        "môžete si ich stiahnuť pomocou nasledujúcich odkazov",
        "mozete si ich stiahnut pomocou nasledujucich odkazov",
        "môžete si ich stiahnuť na nasledujúcich odkazoch",
        "mozete si ich stiahnut na nasledujucich odkazoch",
        "nasledujúce odkazy na stiahnutie",
        "nasledujuce odkazy na stiahnutie",
        "download using the following links",
        "download them using the following links",
    )
    return any(marker in normalized_line for marker in markers)


def _looks_like_fake_download_link(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(
        re.match(
            r"^(?:[-*]\s*|\d+\.\s*)?\[[^\]]+\]\(\s*documents/[^)]+\)$",
            stripped,
            flags=re.IGNORECASE,
        )
    )


def _looks_like_fake_download_response(content: str) -> bool:
    normalized = _canonicalize_document_text(content)
    return "documents/" in content.lower() or (
        any(marker in normalized for marker in ("na stiahnutie", "download", "stiahnut"))
        and any(marker in normalized for marker in ("dokument", "document"))
    )


def _message_for_user(message: Message) -> Message:
    if message.role != MessageRole.ASSISTANT:
        return message
    visible_content = _user_visible_text(message.content)
    if visible_content == message.content:
        return message
    return message.model_copy(update={"content": visible_content})


def _persist_case_citations_for_answer(
    *,
    session: Session,
    question: Message,
    answer: Message,
    result: SessionResult,
) -> list[dict[str, object]]:
    case_id = (session.case_id or "").strip()
    if not case_id:
        return []
    citation_inputs = _case_citation_inputs_from_result(case_id=case_id, result=result)
    if not citation_inputs:
        return []
    store = _get_store()
    question_message_id = _latest_case_communication_id_for_role(
        store=store,
        case_id=case_id,
        role="USER",
    ) or str(question.id)
    answer_message_id = _latest_case_communication_id_for_role(
        store=store,
        case_id=case_id,
        role="ASSISTANT",
    ) or str(answer.id)
    persisted: list[dict[str, object]] = []
    for citation in citation_inputs:
        citation_id = store.add_case_citation(
            case_id=case_id,
            question_message_id=question_message_id,
            answer_message_id=answer_message_id,
            source_type=str(citation["source_type"]),
            source_id=_optional_str(citation.get("source_id")),
            source_url=_optional_str(citation.get("source_url")),
            title=str(citation["title"]),
            citation_label=_optional_str(citation.get("citation_label")),
            law_number=_optional_str(citation.get("law_number")),
            section=_optional_str(citation.get("section")),
            effective_from=_optional_str(citation.get("effective_from")),
            court=_optional_str(citation.get("court")),
            ecli=_optional_str(citation.get("ecli")),
            file_number=_optional_str(citation.get("file_number")),
            decision_date=_optional_str(citation.get("decision_date")),
            snippet=_bounded_optional_text(citation.get("snippet"), max_chars=500),
            retrieval_tool=_optional_str(citation.get("retrieval_tool")),
            relevance_score=_optional_float(citation.get("relevance_score")),
        )
        persisted.append(
            {
                "id": citation_id,
                "case_id": case_id,
                "question_message_id": question_message_id,
                "answer_message_id": answer_message_id,
                **citation,
            }
        )
    _LOGGER.info(
        "Persisted case answer citations",
        extra={
            "case_id": case_id,
            "answer_message_id": answer_message_id,
            "citation_count": len(persisted),
        },
    )
    return persisted


def _case_citation_inputs_from_result(*, case_id: str, result: SessionResult) -> list[dict[str, object]]:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    citations: list[dict[str, object]] = _legal_source_citation_inputs(metadata=metadata)
    raw_law_citations = metadata.get("law_citations")
    if not isinstance(raw_law_citations, list):
        return citations
    seen: set[tuple[str, str]] = set()
    for raw_item in raw_law_citations:
        if not isinstance(raw_item, dict):
            continue
        law_identifier = str(raw_item.get("law_identifier") or raw_item.get("label") or "").strip()
        title = str(raw_item.get("title") or law_identifier or "Legal source").strip()
        if not law_identifier and not title:
            continue
        version_token = str(raw_item.get("version_token") or "").strip()
        source_id = ":".join(
            part
            for part in (
                str(raw_item.get("country_code") or "").strip(),
                str(raw_item.get("collection_code") or "").strip(),
                str(raw_item.get("law_year") or "").strip(),
                str(raw_item.get("law_number") or "").strip(),
                version_token,
            )
            if part
        )
        source_url = str(raw_item.get("open_url") or raw_item.get("official_source_url") or "").strip()
        key = (source_id or law_identifier, source_url)
        if key in seen:
            continue
        seen.add(key)
        snippet = str(raw_item.get("summary") or "").strip()
        if not snippet:
            summary_bits = [
                title,
                f"version {version_token}" if version_token else "",
                f"effective from {raw_item.get('effective_from')}" if raw_item.get("effective_from") else "",
            ]
            snippet = ", ".join(part for part in summary_bits if part)
        citations.append(
            {
                "source_type": "law",
                "source_id": source_id or None,
                "source_url": source_url or None,
                "title": title,
                "citation_label": str(raw_item.get("label") or law_identifier or title).strip(),
                "law_number": law_identifier or None,
                "section": None,
                "effective_from": _optional_str(raw_item.get("effective_from")),
                "court": None,
                "ecli": None,
                "file_number": None,
                "decision_date": None,
                "snippet": _bounded_optional_text(snippet, max_chars=500),
                "retrieval_tool": "JurisDigta laws collector",
                "relevance_score": None,
            }
        )
    return citations


def _legal_source_citation_inputs(*, metadata: dict[str, object]) -> list[dict[str, object]]:
    raw_citations = metadata.get("legal_source_citations")
    if not isinstance(raw_citations, list):
        return []
    citations: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_item in raw_citations:
        if not isinstance(raw_item, dict):
            continue
        source_type = str(raw_item.get("source_type") or "other").strip()
        if source_type not in {"law", "court_decision", "case_document", "web", "other"}:
            source_type = "other"
        source_id = _optional_str(raw_item.get("source_id"))
        source_url = _optional_str(raw_item.get("source_url"))
        title = str(raw_item.get("title") or raw_item.get("citation_label") or source_id or source_url or "").strip()
        if not title:
            continue
        key = (source_type, source_id or "", source_url or title)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "source_url": source_url,
                "title": title,
                "citation_label": _optional_str(raw_item.get("citation_label")) or title,
                "law_number": _optional_str(raw_item.get("law_number")),
                "section": _optional_str(raw_item.get("section")),
                "effective_from": _optional_str(raw_item.get("effective_from")),
                "court": _optional_str(raw_item.get("court")),
                "ecli": _optional_str(raw_item.get("ecli")),
                "file_number": _optional_str(raw_item.get("file_number")),
                "decision_date": _optional_str(raw_item.get("decision_date")),
                "snippet": _bounded_optional_text(raw_item.get("snippet"), max_chars=500),
                "retrieval_tool": _optional_str(raw_item.get("retrieval_tool")),
                "relevance_score": _optional_float(raw_item.get("relevance_score")),
            }
        )
    return citations


def _latest_case_communication_id_for_role(
    *,
    store: Any,
    case_id: str,
    role: str,
) -> str | None:
    prefix = f"{role.strip().upper()}:"
    try:
        communications = store.list_case_communications(case_id=case_id, limit=20, offset=0)
    except Exception:
        return None
    for communication in communications:
        summary = str(getattr(communication, "summary", "") or "").lstrip()
        if summary.upper().startswith(prefix):
            return str(getattr(communication, "communication_id", "") or "") or None
    return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _bounded_optional_text(value: object, *, max_chars: int) -> str | None:
    normalized = _optional_str(value)
    if normalized is None:
        return None
    normalized = " ".join(normalized.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _compose_assistant_content(
    *,
    visible_text: str,
    case_update: dict[str, Any] | None,
) -> str:
    stripped_visible = visible_text.strip()
    if case_update is None:
        return stripped_visible
    payload = json.dumps(case_update, ensure_ascii=False, indent=2)
    if not stripped_visible:
        return f"CASE_UPDATE_JSON:\n{payload}"
    return f"{stripped_visible}\n\nCASE_UPDATE_JSON:\n{payload}"


def _first_followup_question(content: str) -> str:
    normalized = content.strip()
    first_question_index = normalized.find("?")
    if first_question_index < 0:
        return normalized
    return normalized[: first_question_index + 1].strip()


def _truncate_case_update_open_questions(case_update: dict[str, Any]) -> dict[str, Any]:
    case_payload = case_update.get("case")
    if not isinstance(case_payload, dict):
        return case_update
    open_questions = case_payload.get("open_questions")
    if isinstance(open_questions, list) and len(open_questions) > 1:
        case_payload["open_questions"] = open_questions[:1]
    return case_update


def _ensure_missing_info_prompt_has_question(content: str) -> str:
    visible_text = _user_visible_text(content).strip()
    if not visible_text or "?" in visible_text or not _looks_like_missing_info_intro(visible_text):
        return content.strip()
    case_update = _extract_case_update(content)
    question = _first_case_update_open_question(case_update)
    if not question:
        question = _fallback_missing_info_question(visible_text)
    if not question.endswith("?"):
        question = f"{question}?"
    return _compose_assistant_content(
        visible_text=f"{visible_text}\n\n{question}",
        case_update=case_update,
    )


def _looks_like_missing_info_intro(visible_text: str) -> bool:
    normalized = _canonicalize_document_text(visible_text)
    need_markers = (
        "potrebujem este",
        "potrebujem potvrdit",
        "potrebujem doplnit",
        "chyba",
        "chybaju",
        "need to confirm",
        "need more information",
        "missing information",
    )
    document_markers = ("zmluv", "dokument", "document", "contract", "udaj", "detail", "informac")
    return any(marker in normalized for marker in need_markers) and any(
        marker in normalized for marker in document_markers
    )


def _first_case_update_open_question(case_update: dict[str, Any] | None) -> str:
    if not isinstance(case_update, dict):
        return ""
    case_payload = case_update.get("case")
    if not isinstance(case_payload, dict):
        return ""
    open_questions = case_payload.get("open_questions")
    if not isinstance(open_questions, list):
        return ""
    for item in open_questions:
        question = str(item).strip()
        if question:
            return question
    return ""


def _fallback_missing_info_question(visible_text: str) -> str:
    normalized = _canonicalize_document_text(visible_text)
    if any(marker in normalized for marker in ("need to", "missing information", "document", "contract")):
        return "Which specific missing detail should I confirm first?"
    return "Ktorý konkrétny chýbajúci údaj mám potvrdiť ako prvý?"


def _enforce_single_question_turn(content: str) -> str:
    content = _ensure_missing_info_prompt_has_question(content)
    visible_text = _user_visible_text(content)
    if not _assistant_requests_user_reply(visible_text):
        return content.strip()
    first_question = _first_followup_question(visible_text)
    case_update = _extract_case_update(content)
    if case_update is not None:
        case_update = _truncate_case_update_open_questions(case_update)
    return _compose_assistant_content(visible_text=first_question, case_update=case_update)


def _emit_thinking_processing_event(
    *,
    session: Session,
    processing_event_callback: Callable[[dict[str, object]], None] | None,
) -> None:
    if processing_event_callback is None:
        return
    processing_event_callback(
        {
            "stage": "processing",
            "message": _processing_status_message(
                country=session.country,
                language=session.language,
            ),
        }
    )
    processing_event_callback(
        {
            "stage": "thinking",
            "message": _thinking_status_message(
                country=session.country,
                language=session.language,
            ),
        }
    )


def _processing_status_message(*, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return "Spracovavam..."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return "Zpracovavam..."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return "Verarbeite Anfrage..."
    return "Processing..."


def _thinking_status_message(*, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return "Premyslam..."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return "Premyslim..."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return "Ich denke nach..."
    return "Thinking..."


def _request_pdf_reply(language: str | None) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("sk"):
        return "Prosim pripravte vysledok aj vo formate PDF."
    if lang.startswith("de"):
        return "Bitte bereiten Sie das Ergebnis auch im PDF-Format vor."
    return "Please prepare the result in PDF format as well."


def _defer_pdf_reply(language: str | None) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("sk"):
        return "Najprv prosim dokoncime vsetky otazky, potom potvrdim PDF format."
    if lang.startswith("de"):
        return "Bitte lassen Sie uns zuerst alle Rueckfragen klaeren; danach bestaetige ich das PDF-Format."
    return "Please finish all clarifying questions first; then I will confirm PDF format."


def _thank_you_reply(language: str | None) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("sk"):
        return "Dakujem."
    if lang.startswith("de"):
        return "Danke."
    return "Thank you."


def _stream_still_working_message(*, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return "Stale pracujem na odpovedi. Overenie alebo priprava dokumentu trva dlhsie, vysledok poslem hned po dokonceni."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return "Stale pracuji na odpovedi. Overeni nebo priprava dokumentu trva dele, vysledek poslu hned po dokonceni."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return "Ich arbeite noch an der Antwort. Pruefung oder Dokumentvorbereitung dauert laenger, ich sende das Ergebnis sofort nach Abschluss."
    return "Still working on the answer. Verification or document preparation is taking longer; I will send the result as soon as it is ready."


def _model_timeout_message(*, provider_class: str, country: str, language: str | None) -> str:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    local_model = provider_class == "local"
    if normalized_country == "SK" or normalized_language.startswith("sk"):
        return "Časový limit lokálneho modelu vypršal." if local_model else "Časový limit externého modelu vypršal."
    if normalized_country == "CZ" or normalized_language.startswith(("cs", "cz")):
        return "Časový limit lokálního modelu vypršel." if local_model else "Časový limit externího modelu vypršel."
    if normalized_country in {"AT", "DE", "CH"} or normalized_language.startswith("de"):
        return "Zeitüberschreitung beim lokalen Modell." if local_model else "Zeitüberschreitung beim externen Modell."
    return "Timeout on local model." if local_model else "Timeout on external model."


def _model_timeout_error_payload(
    exc: Exception,
    *,
    session: Session,
    task_type: str,
) -> dict[str, object] | None:
    if not isinstance(exc, ModelProcessingTimeout):
        return None
    timeout_seconds = exc.timeout_seconds or 0.0
    _LOGGER.warning(
        "ai_model_processing_timeout provider_class=%s provider=%s model=%s "
        "task_type=%s timeout_seconds=%.3f elapsed_seconds=%.3f error_code=%s",
        exc.provider_class,
        exc.provider,
        exc.model,
        task_type,
        timeout_seconds,
        exc.elapsed_seconds,
        exc.code,
    )
    return {
        "code": exc.code,
        "message": _model_timeout_message(
            provider_class=exc.provider_class,
            country=session.country,
            language=session.language,
        ),
        "params": {
            "provider_class": exc.provider_class,
            "timeout_seconds": timeout_seconds,
        },
    }


def _stream_visible_progress_seconds() -> float:
    configured = float(
        read_positive_finite_env_seconds(
            "LOCAL_LLM_REQUEST_VISIBLE_PROGRESS",
            _STREAM_STATUS_SECONDS,
        )
    )
    return min(configured, _STREAM_STATUS_SECONDS)


def _stream_event_queue(
    *,
    event_queue: Queue[tuple[str, dict[str, object]] | None],
    session: Session,
) -> Generator[str, None, None]:
    last_visible_status_at = time.monotonic()
    visible_progress_seconds = _stream_visible_progress_seconds()
    poll_seconds = min(_STREAM_KEEPALIVE_SECONDS, visible_progress_seconds)
    while True:
        try:
            item = event_queue.get(timeout=poll_seconds)
        except Empty:
            now = time.monotonic()
            if now - last_visible_status_at >= visible_progress_seconds:
                last_visible_status_at = now
                status_body: dict[str, object] = {
                    "stage": "still_working",
                    "message": _stream_still_working_message(
                        country=session.country,
                        language=session.language,
                    ),
                }
                yield f"event: processing\ndata: {json.dumps(status_body)}\n\n"
                continue
            yield ": keepalive\n\n"
            continue
        if item is None:
            break
        event_name, body = item
        if event_name in {"message", "processing", "waiting_for_reply", "result", "done", "error"}:
            last_visible_status_at = time.monotonic()
        yield f"event: {event_name}\ndata: {json.dumps(body)}\n\n"


def _finish_discussion_reply(language: str | None) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("sk"):
        return "To je vsetko"
    if lang.startswith("de"):
        return "Das ist alles."
    return "That's all."


def _should_finish_followup(
    *,
    assistant_messages_seen: int,
    answered_agent_questions: int,
    followup_prompts_seen: int,
) -> bool:
    if answered_agent_questions >= 1 and followup_prompts_seen >= 1:
        return True
    if assistant_messages_seen >= 2 and followup_prompts_seen >= 1:
        return True
    return followup_prompts_seen >= 3


def _continue_discussion_reply(language: str | None, turn_index: int = 0) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("sk"):
        replies = [
            "Prosim pokracujte, chcem este doplnit dolezite skutocnosti.",
            "Doplnam, ze zmluva bola podpisana pisomne a mam jej kopiu.",
            "Doplnam, ze platba najmu prebiehala bankovym prevodom kazdy mesiac.",
            "Doplnam, ze viem poskytnut aj datumy a komunikaciu medzi stranami.",
        ]
        return replies[turn_index % len(replies)]
    if lang.startswith("de"):
        replies = [
            "Bitte machen Sie weiter; ich moechte weitere wichtige Details ergaenzen.",
            "Ich ergaenze: Der Vertrag wurde schriftlich unterschrieben und ich habe eine Kopie.",
            "Ich ergaenze: Die Miete wurde monatlich per Bankueberweisung gezahlt.",
            "Ich kann auch konkrete Daten und die Kommunikation zwischen den Parteien liefern.",
        ]
        return replies[turn_index % len(replies)]
    replies = [
        "Please continue; I want to add more important details.",
        "Additional detail: the agreement was signed in writing and I have a copy.",
        "Additional detail: rent payments were made monthly via bank transfer.",
        "I can also provide specific dates and message history between the parties.",
    ]
    return replies[turn_index % len(replies)]


def _normalize_simulator_reply(
    reply: str,
    language: str | None,
    turn_index: int = 0,
    previous_reply: str = "",
) -> str:
    cleaned = reply.strip()
    if not cleaned:
        return _continue_discussion_reply(language, turn_index)
    if _looks_like_non_answer(cleaned):
        return _continue_discussion_reply(language, turn_index)
    if cleaned.lower() in _FINISH_RESPONSES:
        return _continue_discussion_reply(language, turn_index)
    if previous_reply and cleaned.lower() == previous_reply.strip().lower():
        return _continue_discussion_reply(language, turn_index + 1)
    return cleaned


def _looks_like_non_answer(reply: str) -> bool:
    lowered = reply.lower()
    if "?" in reply:
        return True
    non_answer_markers = (
        "need more context",
        "need more details",
        "please provide",
        "can you clarify",
        "could you clarify",
        "potrebujem viac",
        "prosim doplnte",
        "mohli by ste doplnit",
        "bitte teilen sie",
        "koennen sie",
    )
    return any(marker in lowered for marker in non_answer_markers)


def _normalize_question_key(question: str) -> str:
    return " ".join(question.lower().split())


def _repeated_question_reply(language: str | None, question: str, question_count: int) -> str:
    question_excerpt = question.strip().replace("\n", " ")
    if len(question_excerpt) > 120:
        question_excerpt = question_excerpt[:117] + "..."

    lang = (language or "").strip().lower()
    if lang.startswith("sk"):
        return (
            "Na tuto otazku som uz odpovedal. "
            f"Opakovana otazka ({question_count}x): \"{question_excerpt}\". "
            "Prosim pokracujte navrhom riesenia alebo pripravte konkretne znenie."
        )
    if lang.startswith("de"):
        return (
            "Diese Frage habe ich bereits beantwortet. "
            f"Wiederholte Frage ({question_count}x): \"{question_excerpt}\". "
            "Bitte fahren Sie mit dem Loesungsvorschlag fort oder erstellen Sie einen konkreten Entwurf."
        )
    return (
        "I already answered this question. "
        f"Repeated question ({question_count}x): \"{question_excerpt}\". "
        "Please continue with a concrete solution or draft."
    )


@router.get("/sessions/{session_id}/result", response_model=SessionResult)
def get_session_result(session_id: UUID) -> SessionResult:
    result = _get_or_build_session_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for session {session_id} not found")
    return result


@router.get("/sessions/{session_id}/export/documents", response_model=DocumentExportOptionsResponse)
def list_session_document_exports(session_id: UUID) -> DocumentExportOptionsResponse:
    session, _result, _messages, assets = _session_document_export_context(session_id)
    return DocumentExportOptionsResponse(
        documents=[
            DocumentExportOption(
                index=index,
                filename=asset.filename,
                title=asset.title or f"Document {index + 1}",
            )
            for index, asset in enumerate(assets)
        ]
    )


@router.get("/sessions/{session_id}/export/documents/{document_index}")
def export_session_document_pdf(session_id: UUID, document_index: int) -> Response:
    session, result, _messages, assets = _session_document_export_context(session_id)
    if document_index < 0 or document_index >= len(assets):
        raise HTTPException(
            status_code=404,
            detail=f"Document export {document_index} for session {session_id} not found",
        )
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    footer_line = f"AIJ | API {_API_VERSION} | Core {_CORE_VERSION}"
    return _document_export_asset_response(
        asset=assets[document_index],
        session=session,
        generated_at=generated_at,
        footer_line=footer_line,
        verification_score=_document_verification_score(result),
    )


@router.post("/sessions/{session_id}/documents/send-email", response_model=SendSessionDocumentsEmailResponse)
def send_session_documents_email(
    session_id: UUID,
    payload: SendSessionDocumentsEmailRequest,
) -> SendSessionDocumentsEmailResponse:
    session, result, _messages, assets = _session_document_export_context(session_id)
    recipient = _resolve_document_email_recipient(session=session, payload=payload)
    if not recipient:
        raise HTTPException(status_code=409, detail="User profile email is not available.")
    if not payload.confirmed:
        return SendSessionDocumentsEmailResponse(
            needs_confirmation=True,
            recipient=recipient,
            message=f"Confirm sending all generated documents to {recipient}.",
            attachment_count=len(assets),
        )
    email_id, attachment_count = _enqueue_session_documents_email(
        session=session,
        result=result,
        assets=assets,
        recipient=recipient,
    )
    return SendSessionDocumentsEmailResponse(
        needs_confirmation=False,
        recipient=recipient,
        message=f"Generated documents were queued for email delivery to {recipient}.",
        email_id=email_id,
        attachment_count=attachment_count,
    )


@router.get("/sessions/{session_id}/export")
def export_session_result(
    session_id: UUID,
    format: Literal["json", "pdf"] = Query("json"),
    kind: Literal["summary", "document"] = Query("summary"),
    bundle: Literal["auto", "zip", "single_pdf"] = Query("auto"),
) -> Response:
    result = _get_or_build_session_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for session {session_id} not found")
    session = _repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    messages = _repository.list_messages(session_id)

    if format == "json":
        body = result.model_dump_json(indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="session-{session_id}.json"'},
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    footer_line = f"AIJ | API {_API_VERSION} | Core {_CORE_VERSION}"
    user_profile = _document_user_profile_for_session(session)

    if kind == "document":
        document_assets = _build_document_export_assets(
            session_id=session_id,
            messages=messages,
            result=result,
            country=session.country,
            language=session.language,
            user_profile=user_profile,
        )
        if len(document_assets) > 1 and bundle == "single_pdf":
            filename = _build_pdf_filename(session_id=session_id, kind="document")
            pdf_content = _build_combined_document_export_pdf(
                assets=document_assets,
                country=session.country,
                language=session.language,
                generated_at=generated_at,
                footer_line=footer_line,
                case_id=session.case_id or str(session.id),
                session_id=str(session.id),
                user_id=str(session.user_id) if session.user_id else None,
                verification_score=_document_verification_score(result),
            )
            return Response(
                content=pdf_content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        if len(document_assets) > 1:
            archive_name = _build_document_archive_filename(session_id=session_id)
            archive_content = _build_document_export_archive(
                assets=document_assets,
                country=session.country,
                language=session.language,
                generated_at=generated_at,
                footer_line=footer_line,
                case_id=session.case_id or str(session.id),
                session_id=str(session.id),
                user_id=str(session.user_id) if session.user_id else None,
                verification_score=_document_verification_score(result),
            )
            return Response(
                content=archive_content,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
            )
        return _document_export_asset_response(
            asset=document_assets[0],
            session=session,
            generated_at=generated_at,
            footer_line=footer_line,
            verification_score=_document_verification_score(result),
        )
    else:
        title, lines = _build_summary_export_content(
            session_id=session_id,
            result=result,
            messages=messages,
            country=session.country,
            language=session.language,
        )
        filename = _build_pdf_filename(session_id=session_id, kind="summary")
        disclaimer = None

    pdf_content = _build_simple_pdf(
        title=title,
        lines=lines,
        country=session.country,
        language=session.language,
        header_line=None,
        footer_line=None,
        disclaimer=disclaimer,
        draw_logo_mark=False,
        include_title_block=True,
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _get_or_build_session_result(session_id: UUID) -> SessionResult | None:
    session = _repository.get_session(session_id)
    if session is None:
        return None
    messages = _repository.list_messages(session_id)
    result = _repository.get_result(session_id)
    if result is not None and not _session_result_is_stale(result=result, messages=messages):
        return result
    assistant_messages = [message for message in messages if message.role == MessageRole.ASSISTANT]
    if not assistant_messages:
        return result
    latest_assistant = assistant_messages[-1]
    visible_text = _user_visible_text(latest_assistant.content)
    if _assistant_requests_user_reply(visible_text) and not _document_export_ready(messages):
        return result
    result = _build_direct_reply_result(
        session_id=session_id,
        session=session,
        messages=messages,
        lawyer_message=visible_text,
    )
    _repository.set_result(session_id, result)
    return result


def _session_result_is_stale(*, result: SessionResult, messages: list[Message]) -> bool:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    message_count = metadata.get("message_count")
    if isinstance(message_count, int) and message_count < len(messages):
        return True
    if _document_export_ready(messages) and metadata.get("document_ready") is not True:
        return True
    return False


def _session_document_export_context(
    session_id: UUID,
) -> tuple[Session, SessionResult, list[Message], list[_DocumentExportAsset]]:
    result = _get_or_build_session_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for session {session_id} not found")
    session = _repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    messages = _repository.list_messages(session_id)
    assets = _build_document_export_assets(
        session_id=session_id,
        messages=messages,
        result=result,
        country=session.country,
        language=session.language,
        user_profile=_document_user_profile_for_session(session),
    )
    return session, result, messages, assets


def _document_export_asset_response(
    *,
    asset: _DocumentExportAsset,
    session: Session,
    generated_at: str,
    footer_line: str,
    verification_score: str | None,
) -> Response:
    pdf_content = _build_professional_document_pdf(
        title=asset.title,
        lines=asset.lines,
        country=session.country,
        language=session.language,
        generated_at=generated_at,
        case_id=session.case_id or str(session.id),
        session_id=str(session.id),
        user_id=str(session.user_id) if session.user_id else None,
        footer_line=footer_line,
        verification_score=verification_score,
        disclaimer=asset.disclaimer,
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{asset.filename}"'},
    )


def _document_export_asset_pdf_bytes(
    *,
    asset: _DocumentExportAsset,
    session: Session,
    generated_at: str,
    footer_line: str,
    verification_score: str | None,
) -> bytes:
    return _build_professional_document_pdf(
        title=asset.title,
        lines=asset.lines,
        country=session.country,
        language=session.language,
        generated_at=generated_at,
        case_id=session.case_id or str(session.id),
        session_id=str(session.id),
        user_id=str(session.user_id) if session.user_id else None,
        footer_line=footer_line,
        verification_score=verification_score,
        disclaimer=asset.disclaimer,
    )


def _resolve_document_email_recipient(
    *, session: Session, payload: SendSessionDocumentsEmailRequest
) -> str:
    explicit_recipient = (payload.recipient or "").strip().lower()
    if explicit_recipient:
        return explicit_recipient
    if payload.user_id:
        user = _document_user_profile_for_user_id(payload.user_id)
    else:
        user = _document_user_profile_for_session(session)
    if user is None:
        return ""
    return str(user.email).strip().lower()


def _enqueue_session_documents_email(
    *,
    session: Session,
    result: SessionResult,
    assets: list[_DocumentExportAsset],
    recipient: str,
) -> tuple[str, int]:
    if not assets:
        raise HTTPException(status_code=409, detail="No generated documents available to send.")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    footer_line = f"AIJ | API {_API_VERSION} | Core {_CORE_VERSION}"
    verification_score = _document_verification_score(result)
    attachments: list[dict[str, str]] = []
    for asset in assets:
        pdf_content = _document_export_asset_pdf_bytes(
            asset=asset,
            session=session,
            generated_at=generated_at,
            footer_line=footer_line,
            verification_score=verification_score,
        )
        attachments.append(
            {
                "filename": asset.filename,
                "mime_type": guess_type(asset.filename)[0] or "application/pdf",
                "content_base64": base64.b64encode(pdf_content).decode("utf-8"),
            }
        )
    subject = _session_document_email_subject(session=session, assets=assets)
    plain = (
        "Dobry den,\n\n"
        "v prilohe posielame vygenerovane dokumenty k vasmu pripadu.\n\n"
        "S pozdravom,\nJurisDigta"
    )
    html = _build_session_document_email_html(
        subject=subject,
        session=session,
        attachment_count=len(attachments),
        generated_at=generated_at,
    )
    email_id = EmailScheduler.from_env().enqueue(
        recipient=recipient,
        subject=subject,
        body=plain,
        metadata={
            "event": "session_documents_email",
            "session_id": str(session.id),
            "case_id": session.case_id or "",
            "html_body": html,
            "attachments": attachments,
        },
    )
    return email_id, len(attachments)


def _session_document_email_subject(*, session: Session, assets: list[_DocumentExportAsset]) -> str:
    first_title = assets[0].title.strip() if assets else ""
    suffix = first_title or "Dokumenty"
    if len(assets) > 1:
        suffix = f"Balik dokumentov ({len(assets)})"
    if session.case_id:
        return f"JurisDigta dokumenty | {suffix} | pripad {session.case_id}"
    return f"JurisDigta dokumenty | {suffix}"


def _build_session_document_email_html(
    *, subject: str, session: Session, attachment_count: int, generated_at: str
) -> str:
    case_line = f"<br/>Case ID: {session.case_id}" if session.case_id else ""
    return (
        "<html><body style='font-family:Georgia,serif;color:#1f2937'>"
        "<p>Dobry den,</p>"
        "<p>v prilohe posielame vygenerovane dokumenty k vasmu pripadu.</p>"
        "<p>S pozdravom,<br/>JurisDigta</p>"
        "<hr/>"
        f"<p style='font-size:12px;color:#6b7280'>Subject: {subject}<br/>"
        f"Session ID: {session.id}{case_line}<br/>"
        f"Attachments: {attachment_count}<br/>Generated: {generated_at}</p>"
        "</body></html>"
    )


def _document_user_profile_for_session(session: Session) -> User | None:
    if session.user_id is not None:
        return _document_user_profile_for_user_id(str(session.user_id))
    case_id = (session.case_id or "").strip()
    if not case_id:
        return None
    try:
        store = ApiDatabaseStore.from_env()
        store.initialize()
        case = store.get_case(case_id=case_id)
        return store.find_user_by_id(user_id=case.user_id)
    except Exception:
        return None


def _document_user_profile_for_user_id(user_id: str) -> User | None:
    try:
        store = ApiDatabaseStore.from_env()
        store.initialize()
        return store.find_user_by_id(user_id=user_id)
    except Exception:
        return None


def _build_professional_document_pdf(
    *,
    title: str,
    lines: List[str],
    country: str,
    language: str | None,
    generated_at: str,
    case_id: str,
    footer_line: str,
    session_id: str | None = None,
    user_id: str | None = None,
    verification_score: str | None = None,
    disclaimer: tuple[str, str, str] | None = None,
) -> bytes:
    return _build_simple_pdf(
        title=title,
        lines=lines,
        country=country,
        language=language,
        footer_line=footer_line,
        footer_qr_payload=_build_professional_document_qr_payload(
            generated_at=generated_at,
            case_id=case_id,
            session_id=session_id,
            user_id=user_id,
            document_score=verification_score,
        ),
        document_verification_score=verification_score,
        disclaimer=disclaimer,
        draw_logo_mark=True,
        include_title_block=False,
    )


def _build_simple_pdf(
    title: str,
    lines: List[str],
    *,
    country: str,
    language: str | None,
    header_line: str | None = None,
    footer_line: str | None = None,
    footer_qr_payload: dict[str, str] | None = None,
    document_verification_score: str | None = None,
    disclaimer: tuple[str, str, str] | None = None,
    draw_logo_mark: bool = False,
    include_title_block: bool = True,
) -> bytes:
    regular_font, bold_font = _resolve_pdf_fonts(country=country, language=language)
    use_corporate_template = draw_logo_mark and not include_title_block
    page_width, page_height = cast(tuple[float, float], A4)
    margin_left = 50.0
    margin_top = 52.0
    margin_bottom = 42.0
    body_font_size = 11.0
    body_line_height = 14.0
    title_font_size = 14.0
    footer_font_size = 9.0

    if use_corporate_template:
        margin_left = 64.0
        margin_top = 214.0
        margin_bottom = 84.0
        title_font_size = 20.0
        body_font_size = 11.0
        body_line_height = 24.0

    show_disclaimer = _should_show_document_disclaimer(document_verification_score)
    effective_footer_qr_payload = _with_document_score_qr_payload(
        payload=footer_qr_payload,
        document_score=document_verification_score,
    )
    prefers_slovak_profile = _prefers_slovak_legal_pdf_profile(country=country, language=language)
    header_lines: list[str] = []
    if header_line and not use_corporate_template:
        header_lines.append(header_line)
        header_lines.append("")
    if prefers_slovak_profile and not use_corporate_template:
        header_lines.extend(
            [
                "Jurisdikcia: Slovenská republika",
                "Typ dokumentu: právny návrh",
                "",
            ]
        )

    if disclaimer is not None and not use_corporate_template:
        disclaimer_title, disclaimer_text, _disclaimer_footer = disclaimer
        if disclaimer_title.strip():
            header_lines.append(disclaimer_title.strip())
        if disclaimer_text.strip():
            header_lines.extend(
                _wrap_pdf_lines(
                    [disclaimer_text.strip()],
                    width=(54 if use_corporate_template else 82),
                )
            )
        header_lines.append("")

    title_block: list[str] = [title, "----------------"] if include_title_block else []
    prepared_lines = header_lines + title_block + _wrap_pdf_lines(lines)
    corporate_title_lines: list[str] = []
    if use_corporate_template:
        corporate_title_lines = _wrap_pdf_lines([title], width=42)
        prepared_lines = [*corporate_title_lines, ""]
        prepared_lines.extend(_wrap_pdf_lines(lines, width=54))
    if not prepared_lines:
        prepared_lines = [title]

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height), pageCompression=0)
    pdf.setTitle(title.strip() or "Dokument")
    pdf.setAuthor("JurisDigta")
    pdf.setSubject(title.strip() or "Generated legal document")

    def start_page() -> float:
        if use_corporate_template:
            _draw_jurisdicta_corporate_header(
                pdf=pdf,
                page_width=page_width,
                page_height=page_height,
                margin_left=margin_left,
                regular_font=regular_font,
                bold_font=bold_font,
            )
        elif draw_logo_mark:
            pdf.setFont(bold_font, 10)
            pdf.drawRightString(page_width - margin_left, page_height - 28, "AI Jurisdicta")
        return page_height - margin_top

    def draw_footer() -> None:
        effective_footer = footer_line
        if disclaimer is not None and disclaimer[2].strip():
            effective_footer = (
                f"{footer_line} | {disclaimer[2].strip()}"
                if footer_line
                else disclaimer[2].strip()
            )
        if effective_footer:
            pdf.setFont(regular_font, footer_font_size)
            if use_corporate_template:
                _draw_jurisdicta_professional_footer(
                    pdf=pdf,
                    page_width=page_width,
                    margin_left=margin_left,
                    margin_bottom=margin_bottom,
                    regular_font=regular_font,
                    bold_font=bold_font,
                    footer_line=effective_footer,
                    qr_payload=effective_footer_qr_payload,
                    verification_score=document_verification_score,
                    show_disclaimer=show_disclaimer,
                )
            else:
                pdf.drawString(margin_left, margin_bottom - 8, effective_footer)

    y = start_page()
    for index, line in enumerate(prepared_lines):
        if use_corporate_template and index < len(corporate_title_lines):
            pdf.setFont(bold_font, title_font_size)
            pdf.drawCentredString(page_width / 2.0, y, line)
            y -= body_line_height * (1.35 if index < len(corporate_title_lines) - 1 else 1.6)
            continue
        if index == 0 and include_title_block:
            pdf.setFont(bold_font, title_font_size)
            pdf.drawString(margin_left, y, line)
            y -= body_line_height
            continue
        if include_title_block and index == 1 and line == "----------------":
            pdf.setFont(regular_font, body_font_size)
            pdf.drawString(margin_left, y, line)
            y -= body_line_height
            continue
        if y <= margin_bottom + 20:
            draw_footer()
            pdf.showPage()
            y = start_page()
        if _is_pdf_article_heading(line):
            pdf.setFont(bold_font, body_font_size + 2.0)
            pdf.drawString(margin_left, y, line)
            y -= body_line_height * 1.15
            continue
        _draw_pdf_body_line(
            pdf=pdf,
            line=line,
            x=margin_left,
            y=y,
            regular_font=regular_font,
            bold_font=bold_font,
            font_size=body_font_size,
        )
        y -= body_line_height

    draw_footer()
    if show_disclaimer and disclaimer is not None:
        pdf.showPage()
        _draw_document_disclaimer_page(
            pdf=pdf,
            title=disclaimer[0] or "Dôležité upozornenie",
            text=disclaimer[1],
            page_width=page_width,
            page_height=page_height,
            margin_left=margin_left,
            regular_font=regular_font,
            bold_font=bold_font,
            draw_header=use_corporate_template,
        )
        draw_footer()
    pdf.save()
    return buffer.getvalue()


def _draw_jurisdicta_corporate_header(
    *,
    pdf: canvas.Canvas,
    page_width: float,
    page_height: float,
    margin_left: float,
    regular_font: str,
    bold_font: str,
) -> None:
    sidebar_color = colors.HexColor("#EAF5FF")
    grid_color = colors.HexColor("#D8E7F3")
    logo_box_color = colors.HexColor("#EEF7FF")
    brand_blue = colors.HexColor("#174A8B")
    shield_blue = colors.HexColor("#0F4B86")
    body_text = colors.HexColor("#222222")
    sidebar_width = 126.0
    sidebar_x = page_width - sidebar_width

    pdf.setFillColor(sidebar_color)
    pdf.rect(sidebar_x, 0, sidebar_width, page_height, stroke=0, fill=1)

    pdf.setStrokeColor(grid_color)
    pdf.setLineWidth(0.45)
    grid_step = 56.0
    grid_x = sidebar_x
    while grid_x <= page_width:
        pdf.line(grid_x, 0, grid_x, page_height)
        grid_x += grid_step
    grid_y = 0.0
    while grid_y <= page_height:
        pdf.line(sidebar_x, grid_y, page_width, grid_y)
        grid_y += grid_step

    logo_x = margin_left + 6.0
    logo_y = page_height - 116.0
    logo_w = 168.0
    logo_h = 46.0
    pdf.setFillColor(logo_box_color)
    pdf.rect(logo_x, logo_y, logo_w, logo_h, stroke=0, fill=1)

    shield_x = logo_x + 20.0
    shield_y = logo_y + 10.0
    shield_path = pdf.beginPath()
    shield_path.moveTo(shield_x + 4.0, shield_y + 25.0)
    shield_path.lineTo(shield_x + 31.0, shield_y + 25.0)
    shield_path.lineTo(shield_x + 28.0, shield_y + 8.0)
    shield_path.lineTo(shield_x + 17.5, shield_y)
    shield_path.lineTo(shield_x + 7.0, shield_y + 8.0)
    shield_path.close()
    pdf.setFillColor(shield_blue)
    pdf.drawPath(shield_path, stroke=0, fill=1)
    pdf.setStrokeColor(colors.white)
    pdf.setLineWidth(0.75)
    pdf.line(shield_x + 17.5, shield_y + 3.0, shield_x + 17.5, shield_y + 22.0)
    pdf.line(shield_x + 8.5, shield_y + 14.0, shield_x + 26.5, shield_y + 14.0)

    pdf.setFillColor(brand_blue)
    pdf.setFont(bold_font, 12)
    pdf.drawString(logo_x + 66.0, logo_y + 18.0, "JurisDigta")

    card_w = 150.0
    card_h = 84.0
    card_x = page_width - card_w - 10.0
    card_y = page_height - 144.0
    pdf.setFillColor(colors.white)
    pdf.rect(card_x, card_y, card_w, card_h, stroke=0, fill=1)

    contact_lines = (
        "Poprad, Slovakia, 05801",
        "info@jurisdigta.eu",
        "+421 950 425 113",
    )
    pdf.setFillColor(body_text)
    pdf.setFont(regular_font, 10)
    line_y = card_y + card_h - 24.0
    text_right = card_x + card_w - 30.0
    for contact_line in contact_lines:
        pdf.drawRightString(text_right, line_y, contact_line)
        line_y -= 14.0

    pdf.setStrokeColor(colors.HexColor("#333333"))
    pdf.setLineWidth(1.6)
    rule_x = card_x + card_w - 16.0
    pdf.line(rule_x, card_y + 18.0, rule_x, card_y + card_h - 18.0)

    _draw_jurisdicta_version_block(
        pdf=pdf,
        page_width=page_width,
        margin_bottom=52.0,
        regular_font=regular_font,
        bold_font=bold_font,
    )

    pdf.setFillColor(body_text)


def _draw_jurisdicta_version_block(
    *,
    pdf: canvas.Canvas,
    page_width: float,
    margin_bottom: float,
    regular_font: str,
    bold_font: str,
) -> None:
    label_color = colors.HexColor("#526575")
    value_color = colors.HexColor("#102A43")
    right_x = page_width - 24.0
    y = margin_bottom + 12.0
    version_lines = (
        ("API version:", _API_VERSION),
        ("Core Version:", _CORE_VERSION),
    )
    for label, value in version_lines:
        pdf.setFont(regular_font, 8.2)
        pdf.setFillColor(label_color)
        label_width = pdf.stringWidth(label + " ", regular_font, 8.2)
        value_width = pdf.stringWidth(value, bold_font, 8.2)
        start_x = right_x - label_width - value_width
        pdf.drawString(start_x, y, label)
        pdf.setFont(bold_font, 8.2)
        pdf.setFillColor(value_color)
        pdf.drawString(start_x + label_width, y, value)
        y -= 12.0


def _build_professional_document_qr_payload(
    *,
    generated_at: str,
    case_id: str,
    document_score: str | None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, str]:
    payload = {
        "generated_at": generated_at,
        "api_version": _API_VERSION,
        "core_system_version": _CORE_VERSION,
        "case_id": case_id,
        "document_score": document_score or "-",
    }
    if session_id:
        payload["session_id"] = session_id
    if user_id:
        payload["user_id"] = user_id
    return payload


def _with_document_score_qr_payload(
    *, payload: dict[str, str] | None, document_score: str | None
) -> dict[str, str] | None:
    if payload is None:
        return None
    return {**payload, "document_score": document_score or payload.get("document_score") or "-"}


def _document_verification_score(result: SessionResult | None) -> str | None:
    if result is None:
        return None
    return _format_validation_accuracy((result.metadata or {}).get("validation_accuracy"))


def _document_verification_score_value(score: str | None) -> float | None:
    if score is None:
        return None
    cleaned = score.strip().replace("%", "").replace(",", ".")
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _should_show_document_disclaimer(score: str | None) -> bool:
    value = _document_verification_score_value(score)
    if value is None:
        return True
    return value < DOCUMENT_SHOW_DISCLAIMER


def _draw_jurisdicta_professional_footer(
    *,
    pdf: canvas.Canvas,
    page_width: float,
    margin_left: float,
    margin_bottom: float,
    regular_font: str,
    bold_font: str,
    footer_line: str,
    qr_payload: dict[str, str] | None,
    verification_score: str | None,
    show_disclaimer: bool,
) -> None:
    footer_top = margin_bottom - 6.0
    qr_size = 38.0
    logo_size = 20.0
    brand_color = colors.HexColor("#174A8B")
    muted_color = colors.HexColor("#55616F")
    line_color = colors.HexColor("#D9E2EC")

    pdf.setStrokeColor(line_color)
    pdf.setLineWidth(0.6)
    pdf.line(margin_left, footer_top + 18.0, page_width - margin_left, footer_top + 18.0)

    logo_x = margin_left
    logo_y = footer_top - logo_size + 2.0
    _draw_jurisdicta_footer_logo(
        pdf=pdf,
        x=logo_x,
        y=logo_y,
        size=logo_size,
        color=brand_color,
    )
    pdf.setFillColor(brand_color)
    pdf.setFont(bold_font, 8.5)
    pdf.drawString(logo_x + logo_size + 7.0, footer_top - 2.0, "JurisDigta")
    pdf.setFillColor(muted_color)
    pdf.setFont(regular_font, 7.0)
    pdf.drawString(
        logo_x + logo_size + 7.0,
        footer_top - 12.0,
        f"Skore overenia dokumentu: {verification_score or '-'}",
    )
    if show_disclaimer:
        pdf.drawString(
            logo_x + logo_size + 7.0,
            footer_top - 22.0,
            "Dokument je právny návrh; odporúčam kontrolu právnickej entity.",
        )

    if qr_payload:
        qr_x = page_width - margin_left - qr_size
        qr_y = 6.0
        _draw_footer_qr_code(
            pdf=pdf,
            payload=qr_payload,
            x=qr_x,
            y=qr_y,
            size=qr_size,
        )


def _draw_jurisdicta_footer_logo(
    *,
    pdf: canvas.Canvas,
    x: float,
    y: float,
    size: float,
    color: colors.Color,
) -> None:
    pdf.setStrokeColor(color)
    pdf.setLineWidth(1.1)
    pdf.rect(x, y, size, size, stroke=1, fill=0)
    pdf.line(x + size / 2.0, y + size * 0.22, x + size / 2.0, y + size * 0.76)
    pdf.line(x + size * 0.24, y + size * 0.48, x + size / 2.0, y + size * 0.64)
    pdf.line(x + size / 2.0, y + size * 0.64, x + size * 0.76, y + size * 0.48)
    pdf.setFillColor(color)
    pdf.circle(x + size * 0.24, y + size * 0.48, size * 0.045, stroke=0, fill=1)
    pdf.circle(x + size * 0.76, y + size * 0.48, size * 0.045, stroke=0, fill=1)
    pdf.circle(x + size / 2.0, y + size * 0.22, size * 0.045, stroke=0, fill=1)


def _draw_footer_qr_code(
    *,
    pdf: canvas.Canvas,
    payload: dict[str, str],
    x: float,
    y: float,
    size: float,
) -> None:
    qr_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    widget = qr.QrCodeWidget(qr_payload)
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, pdf, x, y)


def _draw_document_disclaimer_page(
    *,
    pdf: canvas.Canvas,
    title: str,
    text: str,
    page_width: float,
    page_height: float,
    margin_left: float,
    regular_font: str,
    bold_font: str,
    draw_header: bool,
) -> None:
    if draw_header:
        _draw_jurisdicta_corporate_header(
            pdf=pdf,
            page_width=page_width,
            page_height=page_height,
            margin_left=margin_left,
            regular_font=regular_font,
            bold_font=bold_font,
        )
        y = page_height - 214.0
        wrap_width = 54
    else:
        y = page_height - 72.0
        wrap_width = 82
    pdf.setFont(bold_font, 18.0)
    pdf.drawCentredString(page_width / 2.0, y, title.strip() or "Dôležité upozornenie")
    y -= 34.0
    pdf.setFont(regular_font, 11.0)
    for line in _wrap_pdf_lines([text.strip()], width=wrap_width):
        if y <= 96.0:
            break
        _draw_pdf_body_line(
            pdf=pdf,
            line=line,
            x=margin_left,
            y=y,
            regular_font=regular_font,
            bold_font=bold_font,
            font_size=11.0,
        )
        y -= 18.0


def _is_pdf_article_heading(line: str) -> bool:
    text = line.strip()
    return bool(
        re.match(
            r"^(Čl\.|Cl\.|Článok|Clanok|Article)\s+([IVXLCDM]+|\d+)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _draw_pdf_body_line(
    *,
    pdf: canvas.Canvas,
    line: str,
    x: float,
    y: float,
    regular_font: str,
    bold_font: str,
    font_size: float,
) -> None:
    label_match = re.match(
        r"^([A-Za-zÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽáäčďéíĺľňóôŕšťúýž ./-]{1,28}:)(\s*)(.*)$",
        line,
    )
    if not label_match:
        pdf.setFont(regular_font, font_size)
        pdf.drawString(x, y, line)
        return

    label = label_match.group(1)
    separator = label_match.group(2)
    rest = label_match.group(3)
    pdf.setFont(bold_font, font_size)
    pdf.drawString(x, y, label)
    label_width = pdf.stringWidth(label + separator, bold_font, font_size)
    pdf.setFont(regular_font, font_size)
    pdf.drawString(x + label_width, y, rest)


def _wrap_pdf_lines(lines: List[str], width: int = 90) -> List[str]:
    wrapped: List[str] = []
    for line in lines:
        text = _repair_common_mojibake(line).strip()
        if not text:
            wrapped.append("")
            continue
        chunks = textwrap.wrap(
            text,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        wrapped.extend(chunks or [""])
    return wrapped


def _escape_pdf_line(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf_filename(*, session_id: UUID, kind: Literal["summary", "document"]) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if kind == "document":
        return f"{session_id}-{timestamp}-final-document.pdf"
    return f"{session_id}-{timestamp}-discussion-summary.pdf"


def _build_document_archive_filename(*, session_id: UUID) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{session_id}-{timestamp}-document-package.zip"


def _build_document_export_archive(
    *,
    assets: list[_DocumentExportAsset],
    country: str,
    language: str | None,
    generated_at: str,
    footer_line: str,
    case_id: str,
    session_id: str | None,
    user_id: str | None,
    verification_score: str | None,
) -> bytes:
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for asset in assets:
            pdf_content = _build_professional_document_pdf(
                title=asset.title,
                lines=asset.lines,
                country=country,
                language=language,
                generated_at=generated_at,
                case_id=case_id,
                session_id=session_id,
                user_id=user_id,
                footer_line=footer_line,
                verification_score=verification_score,
                disclaimer=asset.disclaimer,
            )
            archive.writestr(asset.filename, pdf_content)
    return archive_buffer.getvalue()


def _build_combined_document_export_pdf(
    *,
    assets: list[_DocumentExportAsset],
    country: str,
    language: str | None,
    generated_at: str,
    footer_line: str,
    case_id: str,
    session_id: str | None,
    user_id: str | None,
    verification_score: str | None,
) -> bytes:
    writer = PdfWriter()
    for asset in assets:
        pdf_content = _build_professional_document_pdf(
            title=asset.title,
            lines=asset.lines,
            country=country,
            language=language,
            generated_at=generated_at,
            case_id=case_id,
            session_id=session_id,
            user_id=user_id,
            footer_line=footer_line,
            verification_score=verification_score,
            disclaimer=asset.disclaimer,
        )
        reader = PdfReader(BytesIO(pdf_content))
        for page in reader.pages:
            writer.add_page(page)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _build_summary_export_content(
    *,
    session_id: UUID,
    result: SessionResult,
    messages: List[Message],
    country: str,
    language: str | None,
) -> tuple[str, List[str]]:
    user_count = len([m for m in messages if m.role == MessageRole.USER])
    assistant_count = len([m for m in messages if m.role == MessageRole.ASSISTANT])
    lang_label = (language or "auto").strip() or "auto"
    generated = result.generated_at.isoformat()
    metadata = result.metadata or {}
    api_version = str(metadata.get("api_version") or _API_VERSION)
    core_version = str(metadata.get("core_version") or _CORE_VERSION)
    last_law_update_date = str(metadata.get("last_law_update_date") or "").strip()
    last_law_update_source = str(metadata.get("last_law_update_source") or "").strip()
    validation_accuracy = _format_validation_accuracy(
        metadata.get("validation_accuracy")
    )
    validation_summary = str(metadata.get("validation_summary") or "").strip()
    law_reference_links = [
        str(link).strip()
        for link in (metadata.get("law_reference_links") or [])
        if str(link).strip()
    ]
    citation_lines = _summary_citation_lines(result.citations)
    document_law_basis_lines = _document_law_basis_lines(
        messages=messages,
        law_reference_links=law_reference_links,
        last_law_update_date=last_law_update_date,
        last_law_update_source=last_law_update_source,
        language=language,
    )
    if (language or "").strip().lower().startswith("sk"):
        lines = [
            "AI Jurisdiction",
            "Zhrnutie diskusie",
            "",
            "Systemove informacie",
            f"Session ID: {session_id}",
            f"Krajina: {country}",
            f"Jazyk: {lang_label}",
            f"Datum generovania: {generated}",
            f"Verzia API: {api_version}",
            f"Verzia system core: {core_version}",
            (
                f"Posledna aktualizacia zakonov v systeme: {last_law_update_date}"
                if last_law_update_date
                else "Posledna aktualizacia zakonov v systeme: nie je dostupna"
            ),
            (
                f"Zdroj aktualizacie zakonov: {last_law_update_source}"
                if last_law_update_source
                else "Zdroj aktualizacie zakonov: neznamy"
            ),
            "",
            "Pouzivatelske odporucanie",
            f"Finalne odporucanie: {result.final_recommendation}",
            f"Odovodnenie: {result.judge_rationale or 'neposkytnute'}",
            (
                f"Validacne zhrnutie: {validation_summary}"
                if validation_summary
                else "Validacne zhrnutie: neposkytnute"
            ),
            f"Pocet sprav pouzivatela: {user_count}",
            f"Pocet odpovedi asistenta: {assistant_count}",
        ]
        if citation_lines:
            lines.extend(["", "Relevantne odkazy alebo citacie"] + citation_lines)
        if law_reference_links:
            lines.extend(["", "Oficialne odkazy na pravne predpisy"])
            lines.extend([f"- {link}" for link in law_reference_links])
        if document_law_basis_lines:
            lines.extend(["", "Pravny zaklad hodnotenia dokumentu"] + document_law_basis_lines)
        lines.extend(
            [
                "",
                "Validacia pripadu",
                f"Presnost: {validation_accuracy}",
                (
                    f"Zhrnutie validacie: {validation_summary}"
                    if validation_summary
                    else "Zhrnutie validacie: neposkytnute"
                ),
            ]
        )
        return (
            f"Zhrnutie diskusie {session_id}",
            lines,
        )
    lines = [
        "AI Jurisdiction",
        "Discussion summary",
        "",
        "System information",
        f"Session ID: {session_id}",
        f"Country: {country}",
        f"Language: {lang_label}",
        f"Generation date: {generated}",
        f"API version: {api_version}",
        f"System core version: {core_version}",
        (
            f"Last law update date available to the system: {last_law_update_date}"
            if last_law_update_date
            else "Last law update date available to the system: unavailable"
        ),
        (
            f"Law update source: {last_law_update_source}"
            if last_law_update_source
            else "Law update source: unknown"
        ),
        "",
        "User recommendation",
        f"Final recommendation: {result.final_recommendation}",
        f"Rationale: {result.judge_rationale or 'not provided'}",
        (
            f"Validation summary: {validation_summary}"
            if validation_summary
            else "Validation summary: not provided"
        ),
        f"User messages: {user_count}",
        f"Assistant messages: {assistant_count}",
    ]
    if citation_lines:
        lines.extend(["", "Relevant links or citations"] + citation_lines)
    if law_reference_links:
        lines.extend(["", "Official law links available in the system"])
        lines.extend([f"- {link}" for link in law_reference_links])
    if document_law_basis_lines:
        lines.extend(["", "Legal basis used to evaluate the document"] + document_law_basis_lines)
    lines.extend(
        [
            "",
            "Case validation",
            f"Accuracy: {validation_accuracy}",
            (
                f"Validation summary: {validation_summary}"
                if validation_summary
                else "Validation summary: not provided"
            ),
        ]
    )
    return (
        f"Discussion Summary {session_id}",
        lines,
    )


def _document_law_basis_lines(
    *,
    messages: List[Message],
    law_reference_links: list[str],
    last_law_update_date: str,
    last_law_update_source: str,
    language: str | None,
) -> list[str]:
    if not _summary_requires_document_law_basis(messages):
        return []

    prefers_slovak = (language or "").strip().lower().startswith("sk")
    lines: list[str] = []
    if prefers_slovak:
        lines.append(
            (
                f"Dokument bol posudzovany podla najnovsich pravnych podkladov dostupnych v systeme k datumu {last_law_update_date}."
                if last_law_update_date
                else "Dokument bol posudzovany podla najnovsich pravnych podkladov dostupnych v systeme."
            )
        )
        if last_law_update_source:
            lines.append(f"Zdroj pravnych podkladov: {last_law_update_source}")
        if law_reference_links:
            lines.append("Pouzite odkazy na pravne predpisy:")
            lines.extend([f"- {link}" for link in law_reference_links])
        else:
            lines.append("Konkretny odkaz na pravny predpis nebol v metadatach dostupny.")
        return lines

    lines.append(
        (
            f"The document was evaluated against the latest legal materials available to the system as of {last_law_update_date}."
            if last_law_update_date
            else "The document was evaluated against the latest legal materials available to the system."
        )
    )
    if last_law_update_source:
        lines.append(f"Legal source used by the system: {last_law_update_source}")
    if law_reference_links:
        lines.append("Law references used for the document evaluation:")
        lines.extend([f"- {link}" for link in law_reference_links])
    else:
        lines.append("No specific law reference link was available in metadata.")
    return lines


def _summary_requires_document_law_basis(messages: List[Message]) -> bool:
    for message in messages:
        if message.role != MessageRole.USER:
            continue
        if is_document_modernization_request(message.content):
            return True
    return False


def _format_validation_accuracy(value: object) -> str:
    if isinstance(value, bool):
        return "-"
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return "-"
    else:
        return "-"
    return f"{numeric:.1f}%"


def _merge_session_citations(
    *,
    generic_citations: list[dict[str, str]],
    metadata: dict[str, object],
) -> list[dict[str, str]]:
    merged = list(generic_citations)
    for citation in _legal_source_session_citations(metadata):
        if citation not in merged:
            merged.append(citation)
    for citation in _law_citation_session_citations(metadata):
        if citation not in merged:
            merged.append(citation)
    return merged


def _legal_source_session_citations(metadata: dict[str, object]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    raw_citations = metadata.get("legal_source_citations")
    if not isinstance(raw_citations, list):
        return citations
    for raw_item in raw_citations:
        if not isinstance(raw_item, dict):
            continue
        label = str(raw_item.get("citation_label") or raw_item.get("title") or "").strip()
        if not label:
            continue
        source_type = str(raw_item.get("source_type") or "source").strip()
        source_url = str(raw_item.get("source_url") or "").strip()
        date = str(raw_item.get("decision_date") or raw_item.get("effective_from") or "").strip()
        retrieval_tool = str(raw_item.get("retrieval_tool") or "").strip()
        snippet_parts = [part for part in (source_type, date, retrieval_tool, source_url) if part]
        citations.append({"filename": label, "snippet": ", ".join(snippet_parts)})
    return citations


def _law_citation_session_citations(metadata: dict[str, object]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    raw_law_citations = metadata.get("law_citations")
    if not isinstance(raw_law_citations, list):
        return citations
    for raw_item in raw_law_citations:
        if not isinstance(raw_item, dict):
            continue
        label = str(raw_item.get("law_identifier") or raw_item.get("label") or "").strip()
        title = str(raw_item.get("title") or "").strip()
        version_token = str(raw_item.get("version_token") or "").strip()
        effective_from = str(raw_item.get("effective_from") or "").strip()
        summary_bits = [part for part in (title, f"version {version_token}" if version_token else "", f"effective from {effective_from}" if effective_from else "") if part]
        if not label:
            continue
        citations.append(
            {
                "filename": label,
                "snippet": ", ".join(summary_bits),
            }
        )
    return citations


def _summary_citation_lines(citations: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for citation in citations[:5]:
        filename = str(citation.get("filename") or "").strip()
        snippet = " ".join(str(citation.get("snippet") or "").split())
        if filename and snippet:
            lines.append(f"- {filename}: {snippet}")
        elif filename:
            lines.append(f"- {filename}")
        elif snippet:
            lines.append(f"- {snippet}")
    return lines


def _law_citation_export_lines(*, metadata: dict[str, object], language: str | None) -> list[str]:
    prefers_slovak = (language or "").strip().lower().startswith("sk")
    lines: list[str] = []
    raw_law_citations = metadata.get("law_citations")
    if not isinstance(raw_law_citations, list):
        return lines
    for raw_item in raw_law_citations:
        if not isinstance(raw_item, dict):
            continue
        identifier = str(raw_item.get("law_identifier") or raw_item.get("label") or "").strip()
        title = str(raw_item.get("title") or "").strip()
        version_token = str(raw_item.get("version_token") or "").strip()
        effective_from = str(raw_item.get("effective_from") or "").strip()
        if not identifier:
            continue
        if prefers_slovak:
            detail = f"- {identifier}"
            if title:
                detail += f": {title}"
            if version_token:
                detail += f", verzia {version_token}"
            if effective_from:
                detail += f", účinná od {effective_from}"
            detail += ", zdroj: laws connector DB, skóre zdroja 1.0"
        else:
            detail = f"- {identifier}"
            if title:
                detail += f": {title}"
            if version_token:
                detail += f", version {version_token}"
            if effective_from:
                detail += f", effective from {effective_from}"
            detail += ", source: laws connector DB, source score 1.0"
        lines.append(detail)
    return lines


def _build_document_export_assets(
    *,
    session_id: UUID,
    messages: List[Message],
    result: SessionResult | None,
    country: str,
    language: str | None,
    user_profile: User | None = None,
) -> list[_DocumentExportAsset]:
    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country=country,
        language=language,
        user_profile=user_profile,
    )
    (
        _context_lines,
        case_update,
        document_kind,
        facts,
        law_citation_lines,
    ) = _prepare_document_export_context(
        messages=messages,
        result=result,
        language=language,
    )
    facts = _apply_user_profile_document_defaults(facts=facts, user_profile=user_profile)
    facts = _sanitize_missing_document_facts(facts)
    document_entries = _case_update_document_entries(case_update)
    if not document_entries:
        document_entries = _fallback_document_entries_for_export(
            messages=messages,
            result=result,
            document_kind=document_kind,
        )
    if len(document_entries) <= 1:
        entry = document_entries[0] if document_entries else None
        disclaimer = _resolve_document_export_disclaimer(
            country=country,
            language=language,
            document_kind=document_kind,
        )
        if entry is not None and _document_entry_content(entry):
            entry_title, entry_lines = _build_document_asset_content(
                entry=entry,
                document_kind=document_kind,
                facts=facts,
                country=country,
                language=language,
                law_citation_lines=law_citation_lines,
                fallback_index=1,
            )
            export_title = entry_title or title
            return [
                _DocumentExportAsset(
                    filename=_document_asset_filename(
                        entry=entry,
                        fallback_filename=_build_pdf_filename(session_id=session_id, kind="document"),
                    ),
                    title=export_title,
                    lines=_strip_duplicate_body_title(title=export_title, lines=entry_lines),
                    disclaimer=disclaimer,
                    use_corporate_template=_is_third_party_document(
                        document_kind=document_kind,
                        entry=entry,
                        title=export_title,
                        lines=entry_lines,
                    ),
                )
            ]
        return [
            _DocumentExportAsset(
                filename=_document_asset_filename(
                    entry=entry,
                    fallback_filename=_build_pdf_filename(session_id=session_id, kind="document"),
                ),
                title=title,
                lines=_strip_duplicate_body_title(title=title, lines=lines),
                disclaimer=disclaimer,
                use_corporate_template=_is_third_party_document(
                    document_kind=document_kind,
                    entry=entry,
                    title=title,
                    lines=lines,
                ),
            )
        ]
    return _build_multi_document_export_assets(
        document_entries=document_entries,
        document_kind=document_kind,
        facts=facts,
        country=country,
        language=language,
        law_citation_lines=law_citation_lines,
    )


def _fallback_document_entries_for_export(
    *,
    messages: List[Message],
    result: SessionResult | None,
    document_kind: str,
) -> list[dict[str, Any]]:
    discussion_messages = [
        m.content
        for m in messages
        if m.role in {MessageRole.USER, MessageRole.ASSISTANT}
    ]
    lawyer_messages = [
        m.content
        for m in messages
        if m.role == MessageRole.ASSISTANT and (m.agent_name or "").lower().startswith("lawyer")
    ]
    result_text = [result.final_recommendation] if result is not None else []
    source = _pick_document_message(lawyer_messages) or _pick_document_message(discussion_messages) or "\n".join(result_text)
    sections = _extract_visible_document_sections_for_export(_user_visible_text(source))
    if len(sections) <= 1:
        return []
    entries: list[dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        title = section["title"]
        entry_type = _fallback_document_entry_type(title=title, document_kind=document_kind)
        filename = _fallback_document_entry_filename(
            title=title,
            document_kind=document_kind,
            entry_type=entry_type,
        )
        entries.append(
            {
                "doc_id": f"FALLBACK-{index:03d}",
                "type": entry_type,
                "filename": filename,
                "path": f"documents/{filename}",
                "content": section["content"],
            }
        )
    return entries


def _extract_visible_document_sections_for_export(content: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped in {"---", "___", "***"}:
            if current_title:
                current_lines.append("")
            continue
        if current_title and _is_visible_document_conversation_boundary(stripped):
            if current_lines:
                sections.append({"title": current_title, "content": "\n".join(current_lines)})
            current_title = ""
            current_lines = []
            continue
        title_candidate = _document_section_title_from_line(stripped)
        if title_candidate:
            if current_title and current_lines:
                sections.append({"title": current_title, "content": "\n".join(current_lines)})
            current_title = title_candidate
            current_lines = [title_candidate]
            continue
        if current_title:
            current_lines.append(raw_line)
    if current_title and current_lines:
        sections.append({"title": current_title, "content": "\n".join(current_lines)})
    cleaned_sections: list[dict[str, str]] = []
    seen: set[str] = set()
    for section in sections:
        body = _sanitize_generated_legal_document_body(section["content"])
        if not body or not _looks_like_exportable_legal_document_body(body):
            continue
        key = _canonicalize_document_text(section["title"])
        if key in seen:
            continue
        seen.add(key)
        cleaned_sections.append({"title": section["title"], "content": body})
    if cleaned_sections:
        return cleaned_sections
    return [{"title": title, "content": title} for title in _extract_document_titles_from_text(content)]


def _is_visible_document_conversation_boundary(line: str) -> bool:
    if not line:
        return False
    normalized = re.sub(r"^\s{0,3}#{1,6}\s+", "", line.strip())
    normalized = normalized.strip("*_#:- ")
    canonical = _canonicalize_document_text(normalized).rstrip("?")
    return canonical in {
        "co dalej",
        "what next",
        "next steps",
        "wie weiter",
        "zhrnutie pripadu",
        "chybajuce informacie dokumenty",
        "rizika slabe miesta",
        "navrhovany postup",
    }


def _document_section_title_from_line(line: str) -> str:
    if not line:
        return ""
    original = line.strip()
    if re.match(r"^[-*]\s+", original) and not original.startswith(("**", "__")):
        return ""
    explicit_title = bool(
        re.match(r"^(?:#{1,6}\s+|\*\*[^*]+\*\*$|__[^_]+__$|\d+[\.)]\s+)", original)
    )
    normalized = re.sub(r"^\d+[\.)]\s*", "", line)
    normalized = normalized.strip("*_#:- ")
    if ":" in normalized:
        normalized = normalized.split(":", 1)[0].strip()
    if not explicit_title:
        words = normalized.split()
        if len(words) > 8 or normalized.endswith((".", "?", "!")):
            return ""
    display_name = _repair_common_mojibake(normalized)
    return display_name if _looks_like_document_title(display_name) else ""


def _looks_like_exportable_legal_document_body(content: str) -> bool:
    normalized = _canonicalize_document_text(content)
    title_markers = (
        "splnomocnenie",
        "power of attorney",
        "potvrdenie",
        "zmluva",
        "vyzva",
        "zaloba",
        "navrh",
        "agreement",
        "contract",
    )
    body_markers = (
        "ja,",
        "tymto",
        "hereby",
        "authorize",
        "datum",
        "date:",
        "podpis",
        "signature",
        "zmluvne strany",
        "predmet",
    )
    return any(marker in normalized for marker in title_markers) and any(
        marker in normalized for marker in body_markers
    )


def _fallback_document_entry_type(*, title: str, document_kind: str) -> str:
    lowered = _canonicalize_document_text(title)
    if document_kind == "rental_agreement":
        if "zmluv" in lowered and ("najom" in lowered or "najm" in lowered or "lease" in lowered):
            return "contract"
        if "inventar" in lowered or "zoznam vybaven" in lowered:
            return "inventory"
        if any(token in lowered for token in ("prevzati", "odovzdani", "preberaci", "odovzdavaci")):
            return "handover_protocol"
    if document_kind == "share_transfer" or any(
        token in lowered for token in ("podiel", "rozhodnut", "spolocensk", "spoloensk", "zakladatels", "orsr")
    ):
        if "zmluv" in lowered and "podiel" in lowered:
            return "contract"
        if any(token in lowered for token in ("zapisnic", "pisnica", "rozhodnut")):
            return "minutes"
        if any(token in lowered for token in ("spolocensk", "spoloensk", "zakladatels")):
            return "articles"
        if "orsr" in lowered or "obchodn" in lowered or "podanie" in lowered:
            return "registry_filing"
    return "other"


def _fallback_document_entry_filename(title: str, *, document_kind: str, entry_type: str) -> str:
    if document_kind == "rental_agreement":
        known_filenames = {
            "contract": "Najomna_zmluva.pdf",
            "inventory": "Inventarny_zoznam.pdf",
            "handover_protocol": "Protokol_o_odovzdani_a_prevzati_bytu.pdf",
        }
        known_filename = known_filenames.get(entry_type)
        if known_filename is not None:
            return known_filename
    if document_kind == "share_transfer" or entry_type in {"contract", "minutes", "articles", "registry_filing"}:
        known_filenames = {
            "contract": "Zmluva_o_prevode_podielu.pdf",
            "minutes": "Zapisnica_z_rozhodnutia_spolocnikov.pdf",
            "articles": "Spolocenska_zmluva.pdf",
            "registry_filing": "Podanie_na_ORSR.pdf",
        }
        known_filename = known_filenames.get(entry_type)
        if known_filename is not None:
            return known_filename
    normalized = re.sub(r"[^\w\s-]+", "", _canonicalize_document_text(title), flags=re.UNICODE)
    normalized = re.sub(r"\s+", "_", normalized.strip())
    normalized = normalized.strip("_") or "document"
    return f"{normalized}.pdf"


def _prepare_document_export_context(
    *,
    messages: List[Message],
    result: SessionResult | None,
    language: str | None,
) -> tuple[List[str], dict[str, Any] | None, str, dict[str, str], list[str]]:
    discussion_messages = [
        m.content
        for m in messages
        if m.role in {MessageRole.USER, MessageRole.ASSISTANT}
    ]
    lawyer_messages = [
        m.content
        for m in messages
        if m.role == MessageRole.ASSISTANT and (m.agent_name or "").lower().startswith("lawyer")
    ]
    result_text = [result.final_recommendation] if result is not None else []
    source = _pick_document_message(lawyer_messages) or _pick_document_message(discussion_messages)
    source_lines = _normalize_document_lines(source)
    context_lines = _normalize_document_lines("\n".join([*discussion_messages, *result_text]))
    if not context_lines:
        context_lines = source_lines
    if not context_lines:
        context_lines = ["No lawyer-generated document content found in this session."]
    case_update = None
    for content in reversed(discussion_messages):
        case_update = _extract_case_update(content)
        if case_update is not None:
            break
    if case_update is None:
        case_update = _extract_case_update(source)
    document_kind = _detect_document_kind(context_lines, case_update)
    facts = _extract_document_facts(context_lines, case_update)
    law_citation_lines = _law_citation_export_lines(
        metadata=result.metadata if result is not None else {},
        language=language,
    )
    return context_lines, case_update, document_kind, facts, law_citation_lines


def _build_document_export_content(
    *,
    session_id: UUID,
    messages: List[Message],
    result: SessionResult | None,
    country: str,
    language: str | None,
    user_profile: User | None = None,
) -> tuple[str, List[str]]:
    context_lines, _case_update, document_kind, facts, law_citation_lines = (
        _prepare_document_export_context(
            messages=messages,
            result=result,
            language=language,
        )
    )
    facts = _apply_user_profile_document_defaults(facts=facts, user_profile=user_profile)
    facts = _sanitize_missing_document_facts(facts)
    title = _document_export_title_from_recommendation(
        context_lines=context_lines,
        document_kind=document_kind,
        language=language,
    )
    if country.strip().upper() == "SK" and document_kind == "share_transfer":
        from app.chat.country_services.slovakia import build_slovak_share_transfer_export_lines

        title = _document_export_title_from_recommendation(
            context_lines=context_lines,
            document_kind=document_kind,
            language=language,
        )
        export_lines = build_slovak_share_transfer_export_lines(
            messages=messages,
            normalize_document_lines=_normalize_document_lines,
            extract_document_facts=_extract_document_facts,
            build_share_transfer_lines=_build_slovak_share_transfer_lines,
        )
        if export_lines:
            return title, _append_document_law_citations(
                lines=export_lines,
                citations=law_citation_lines,
                language=language,
            )

    if (language or "").strip().lower().startswith("sk"):
        title = _document_export_title_from_recommendation(
            context_lines=context_lines,
            document_kind=document_kind,
            language=language,
        )
        if document_kind == "payment_confirmation":
            lines = _build_slovak_payment_confirmation_lines(facts)
            lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
            return title, _strip_duplicate_body_title(title=title, lines=lines)
        if document_kind == "rental_agreement":
            lines = _build_standard_slovak_agreement_lines(facts)
            lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
            return title, _strip_duplicate_body_title(title=title, lines=lines)
        if document_kind == "easement_demand":
            lines = _build_slovak_easement_demand_lines(facts)
            return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        if document_kind == "share_transfer":
            lines = _build_slovak_share_transfer_lines(facts)
            return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        lines = _build_generic_slovak_case_document_lines(facts)
        lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        return title, _strip_duplicate_body_title(title=title, lines=lines)

    title = _document_export_title_from_recommendation(
        context_lines=context_lines,
        document_kind=document_kind,
        language=language,
    )
    if document_kind == "rental_agreement":
        lines = _build_standard_english_agreement_lines(facts)
        lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        return title, _strip_duplicate_body_title(title=title, lines=lines)
    if document_kind == "payment_confirmation":
        lines = _build_english_payment_confirmation_lines(facts)
        lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        return title, _strip_duplicate_body_title(title=title, lines=lines)
    if document_kind == "easement_demand":
        lines = _build_english_easement_demand_lines(facts)
        lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        return title, _strip_duplicate_body_title(title=title, lines=lines)
    if document_kind == "share_transfer":
        lines = _build_english_share_transfer_lines(facts)
        lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        return title, _strip_duplicate_body_title(title=title, lines=lines)
    lines = _build_generic_english_case_document_lines(facts)
    lines = _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
    return title, _strip_duplicate_body_title(title=title, lines=lines)


def _document_export_title_from_recommendation(
    *,
    context_lines: list[str],
    document_kind: str,
    language: str | None,
) -> str:
    source = _repair_common_mojibake("\n".join(context_lines))
    for candidate in _extract_document_titles_from_text(source):
        normalized = _canonicalize_document_text(candidate)
        if (
            "generovany dokument" not in normalized
            and "generated document" not in normalized
            and not _is_document_title_request_sentence(normalized)
        ):
            return candidate

    lowered = _canonicalize_document_text(source)
    is_slovak = (language or "").strip().lower().startswith("sk")
    if is_slovak:
        if _mentions_purchase_sale_document(lowered):
            return "Kupno-predajna zmluva"
        if "darovac" in lowered and "zmluv" in lowered:
            return "Darovacia zmluva"
        if document_kind == "payment_confirmation" or (
            "potvrdenie" in lowered and any(token in lowered for token in ("zaplat", "uhrad", "platb"))
        ):
            return "Potvrdenie o zaplatení"
        if "plnomoc" in lowered or "splnomoc" in lowered:
            return "Plnomocenstvo"
        if "vypoved" in lowered and ("najom" in lowered or "najm" in lowered):
            return "Vypoved najomnej zmluvy"
        if document_kind == "rental_agreement":
            return "Najomna zmluva"
        if document_kind == "share_transfer":
            return "Zmluva o prevode obchodneho podielu"
        if document_kind == "easement_demand":
            return "Vyzva na zriadenie vecneho bremena"
        return "Pravny dokument"

    if _mentions_purchase_sale_document(lowered):
        return "Purchase Agreement"
    if "gift" in lowered and "agreement" in lowered:
        return "Gift Agreement"
    if document_kind == "payment_confirmation" or (
        "confirmation" in lowered and any(token in lowered for token in ("payment", "paid"))
    ):
        return "Payment Confirmation"
    if "payment confirmation" in lowered or ("confirmation" in lowered and "payment" in lowered):
        return "Payment Confirmation"
    if document_kind == "rental_agreement":
        return "Lease Agreement"
    if document_kind == "share_transfer":
        return "Share Transfer Agreement"
    if document_kind == "easement_demand":
        return "Easement Demand"
    return "Legal Document"


def _mentions_purchase_sale_document(lowered: str) -> bool:
    return (
        any(token in lowered for token in ("kupno predajn", "kupno-predajn", "kupnopredajn"))
        or ("kupna" in lowered and "zmluv" in lowered)
        or ("predajna" in lowered and "zmluv" in lowered)
        or ("purchase" in lowered and ("agreement" in lowered or "contract" in lowered))
        or ("sale" in lowered and ("agreement" in lowered or "contract" in lowered))
    )


def _is_document_title_request_sentence(normalized: str) -> bool:
    request_prefixes = (
        "priprav ",
        "pripravil som ",
        "pripravim ",
        "pripravím ",
        "odporucam ",
        "odporúčam ",
        "chcem ",
        "prosim ",
        "potrebujem ",
        "navrhni ",
        "vytvor ",
        "please ",
        "prepare ",
        "i need ",
    )
    return len(normalized) > 72 or normalized.startswith(request_prefixes)


def _strip_duplicate_body_title(*, title: str, lines: list[str]) -> list[str]:
    if not lines:
        return lines
    first_content_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_content_index is None:
        return lines
    first_line = lines[first_content_index].strip()
    if not _document_titles_are_equivalent(title, first_line):
        return lines
    return [*lines[:first_content_index], *lines[first_content_index + 1 :]]


def _document_titles_are_equivalent(left: str, right: str) -> bool:
    left_normalized = _canonicalize_document_text(left)
    right_normalized = _canonicalize_document_text(right)
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True
    both_rental_titles = all(
        "zmluv" in value and any(token in value for token in ("najom", "najm", "prenajom", "prenajm"))
        for value in (left_normalized, right_normalized)
    )
    if both_rental_titles:
        return True
    both_lease_titles = all(
        ("lease" in value or "rental" in value) and ("agreement" in value or "contract" in value)
        for value in (left_normalized, right_normalized)
    )
    return both_lease_titles


def _append_document_law_citations(
    *,
    lines: List[str],
    citations: list[str],
    language: str | None,
) -> List[str]:
    if not citations:
        return lines
    prefers_slovak = (language or "").strip().lower().startswith("sk")
    heading = "Právne citácie" if prefers_slovak else "Legal citations"
    return [*lines, "", heading, *citations]


def _case_update_document_entries(case_update: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(case_update, dict):
        return []
    case = case_update.get("case")
    if not isinstance(case, dict):
        return []
    raw_documents = case.get("documents")
    if not isinstance(raw_documents, list):
        return []
    return [item for item in raw_documents if isinstance(item, dict)]


def _document_asset_filename(
    *,
    entry: dict[str, Any] | None,
    fallback_filename: str,
) -> str:
    raw_name = ""
    if entry is not None:
        raw_name = str(entry.get("filename") or entry.get("path") or "").strip()
    candidate = Path(raw_name).name if raw_name else ""
    if not candidate:
        return fallback_filename
    stem = Path(candidate).stem.strip() or Path(fallback_filename).stem
    return f"{stem}.pdf"


def _build_multi_document_export_assets(
    *,
    document_entries: list[dict[str, Any]],
    document_kind: str,
    facts: dict[str, str],
    country: str,
    language: str | None,
    law_citation_lines: list[str],
) -> list[_DocumentExportAsset]:
    assets: list[_DocumentExportAsset] = []
    used_filenames: set[str] = set()
    disclaimer = _resolve_document_export_disclaimer(
        country=country,
        language=language,
        document_kind=document_kind,
    )
    for index, entry in enumerate(document_entries, start=1):
        filename = _document_asset_filename(
            entry=entry,
            fallback_filename=f"document-{index}.pdf",
        )
        unique_filename = _deduplicate_export_filename(filename=filename, used_filenames=used_filenames)
        title, lines = _build_document_asset_content(
            entry=entry,
            document_kind=document_kind,
            facts=facts,
            country=country,
            language=language,
            law_citation_lines=law_citation_lines,
            fallback_index=index,
        )
        assets.append(
            _DocumentExportAsset(
                filename=unique_filename,
                title=title,
                lines=_strip_duplicate_body_title(title=title, lines=lines),
                disclaimer=disclaimer,
                use_corporate_template=_is_third_party_document(
                    document_kind=document_kind,
                    entry=entry,
                    title=title,
                    lines=lines,
                ),
            )
        )
    return assets


def _is_third_party_document(
    *,
    document_kind: str,
    entry: dict[str, Any] | None,
    title: str,
    lines: list[str],
) -> bool:
    if document_kind in {"rental_agreement", "share_transfer", "easement_demand"}:
        return True
    entry_type = _canonicalize_document_text(str((entry or {}).get("type") or ""))
    if entry_type in {"contract", "minutes", "articles", "registry_filing", "handover_protocol", "inventory"}:
        return True
    candidate_text = " ".join(
        [
            title,
            str((entry or {}).get("filename") or ""),
            str((entry or {}).get("path") or ""),
            *(lines[:8]),
        ]
    )
    lowered = _canonicalize_document_text(candidate_text)
    if any(
        token in lowered
        for token in (
            "registry filing",
            "court filing",
            "contract",
            "agreement",
            "petition",
            "protocol",
            "receipt",
            "payment confirmation",
            "potvrdenie",
            "zaplateni",
            "uhrade",
        )
    ):
        return True
    internal_markers = (
        "legal summary and next-step memorandum",
        "pravne zhrnutie a navrh dalsieho postupu",
        "recommended next steps",
        "odporucany postup",
    )
    if any(marker in lowered for marker in internal_markers):
        return False
    return False


def _resolve_document_export_disclaimer(
    *,
    country: str,
    language: str | None,
    document_kind: str,
) -> tuple[str, str, str] | None:
    try:
        store = get_document_template_store()
        templates = store.list(include_deleted=False, jurisdiction=country.strip().upper())
    except Exception:
        templates = []
    return resolve_disclaimer_from_templates(
        templates=templates,
        country=country,
        language=language,
        template_kind=_template_kind_for_document_kind(document_kind),
    )


def _template_kind_for_document_kind(document_kind: str) -> str | None:
    mapping = {
        "rental_agreement": "rental_agreement",
        "share_transfer": "share_transfer_agreement",
        "easement_demand": "court_filing",
        "generic_case_document": "court_filing",
    }
    return mapping.get(document_kind)


def _deduplicate_export_filename(*, filename: str, used_filenames: set[str]) -> str:
    base = Path(filename).stem or "document"
    suffix = Path(filename).suffix or ".pdf"
    candidate = f"{base}{suffix}"
    counter = 2
    while candidate.lower() in used_filenames:
        candidate = f"{base}-{counter}{suffix}"
        counter += 1
    used_filenames.add(candidate.lower())
    return candidate


def _build_document_asset_content(
    *,
    entry: dict[str, Any],
    document_kind: str,
    facts: dict[str, str],
    country: str,
    language: str | None,
    law_citation_lines: list[str],
    fallback_index: int,
) -> tuple[str, list[str]]:
    entry_body = _document_entry_content(entry)
    if entry_body:
        title = _document_asset_title(entry=entry, language=language, fallback_index=fallback_index)
        lines = _normalize_document_lines(_sanitize_generated_legal_document_body(entry_body))
        return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)

    if document_kind == "rental_agreement":
        return _build_rental_document_asset_content(
            entry=entry,
            facts=facts,
            country=country,
            language=language,
            law_citation_lines=law_citation_lines,
            fallback_index=fallback_index,
        )
    if document_kind == "share_transfer":
        return _build_share_transfer_document_asset_content(
            entry=entry,
            facts=facts,
            country=country,
            language=language,
            law_citation_lines=law_citation_lines,
        )

    title = _document_asset_title(entry=entry, language=language, fallback_index=fallback_index)
    prefers_slovak = (language or "").strip().lower().startswith("sk")
    if prefers_slovak:
        lines = _build_generic_slovak_case_document_lines(facts)
    else:
        lines = _build_generic_english_case_document_lines(facts)
    return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)


def _document_asset_title(
    *,
    entry: dict[str, Any],
    language: str | None,
    fallback_index: int,
) -> str:
    raw_title = str(entry.get("title") or entry.get("name") or entry.get("label") or "").strip()
    if raw_title:
        return _repair_common_mojibake(raw_title.strip("*#:- "))
    raw_name = str(entry.get("filename") or entry.get("path") or "").strip()
    if raw_name:
        stem = Path(raw_name).stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return stem
    prefers_slovak = (language or "").strip().lower().startswith("sk")
    if prefers_slovak:
        return f"Dokument {fallback_index}"
    return f"Document {fallback_index}"


def _build_rental_document_asset_content(
    *,
    entry: dict[str, Any],
    facts: dict[str, str],
    country: str,
    language: str | None,
    law_citation_lines: list[str],
    fallback_index: int,
) -> tuple[str, list[str]]:
    prefers_slovak = country.strip().upper() == "SK" or (language or "").strip().lower().startswith("sk")
    asset_kind = _classify_rental_document_asset(entry)
    if prefers_slovak:
        if asset_kind == "inventory":
            title = "Inventárny zoznam"
            lines = _build_slovak_rental_inventory_lines(facts)
        elif asset_kind == "handover_protocol":
            title = "Protokol o odovzdaní a prevzatí bytu"
            lines = _build_slovak_rental_handover_lines(facts)
        else:
            title = "Nájomná zmluva"
            lines = _build_standard_slovak_agreement_lines(facts)
    else:
        title = _document_asset_title(entry=entry, language=language, fallback_index=fallback_index)
        lines = _build_standard_english_agreement_lines(facts)
    return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)


def _classify_rental_document_asset(
    entry: dict[str, Any]
) -> Literal["agreement", "inventory", "handover_protocol"]:
    raw_name = _canonicalize_document_text(
        " ".join(str(entry.get(key) or "").strip() for key in ("filename", "path", "type"))
    )
    if "inventar" in raw_name or "zoznam vybaven" in raw_name or "inventory" in raw_name:
        return "inventory"
    if any(
        token in raw_name
        for token in ("prevzati", "odovzdani", "preberaci", "odovzdavaci", "handover", "takeover")
    ):
        return "handover_protocol"
    return "agreement"


def _build_share_transfer_document_asset_content(
    *,
    entry: dict[str, Any],
    facts: dict[str, str],
    country: str,
    language: str | None,
    law_citation_lines: list[str],
) -> tuple[str, list[str]]:
    asset_kind = _classify_share_transfer_document_asset(entry)
    prefers_slovak = country.strip().upper() == "SK" or (language or "").strip().lower().startswith("sk")
    if prefers_slovak:
        if asset_kind == "minutes":
            title = "Rozhodnutie jedineho spolocnika / zapisnica"
            lines = _build_slovak_share_transfer_minutes_lines(facts)
        elif asset_kind == "articles":
            title = _share_transfer_articles_document_title(facts)
            lines = _build_slovak_share_transfer_articles_lines(facts)
        elif asset_kind == "registry_filing":
            title = "Podanie na ORSR"
            lines = _build_slovak_share_transfer_registry_filing_lines(facts)
        else:
            title = "Zmluva o prevode obchodneho podielu"
            lines = _build_slovak_share_transfer_agreement_lines(facts)
    else:
        if asset_kind == "minutes":
            title = "Sole shareholder decision / meeting minutes"
            lines = _build_english_share_transfer_minutes_lines(facts)
        elif asset_kind == "articles":
            title = _share_transfer_articles_document_title(facts)
            lines = _build_english_share_transfer_articles_lines(facts)
        elif asset_kind == "registry_filing":
            title = "Registry filing package"
            lines = _build_english_share_transfer_registry_filing_lines(facts)
        else:
            title = "Share transfer agreement"
            lines = _build_english_share_transfer_agreement_lines(facts)
    return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)


def _share_transfer_articles_document_title(facts: dict[str, str]) -> str:
    haystack = _canonicalize_document_text(" ".join(str(value) for value in facts.values()))
    if any(token in haystack for token in ("jediny spolocnik", "jedineho spolocnika", "sole shareholder")):
        return "Zakladatelska listina"
    return "Spolocenska zmluva"


def _classify_share_transfer_document_asset(
    entry: dict[str, Any]
) -> Literal["agreement", "minutes", "articles", "registry_filing"]:
    raw_name = " ".join(
        str(entry.get(key) or "").strip().lower()
        for key in ("filename", "path", "type")
    )
    if any(token in raw_name for token in ("zapisnic", "zÃ¡pisnic", "rozhodnut", "minutes", "decision")):
        return "minutes"
    if any(
        token in raw_name
        for token in ("spolocensk", "spoloÄensk", "zakladatelsk", "zakladateÄ¾sk", "articles", "founding")
    ):
        return "articles"
    if any(
        token in raw_name
        for token in ("orsr", "registry", "obchodneho_registra", "obchodnÃ©ho_registra", "filing")
    ):
        return "registry_filing"
    return "agreement"


def _pick_document_message(candidates: List[str]) -> str:
    if not candidates:
        return ""

    def _score(content: str) -> tuple[int, int]:
        lowered = content.lower()
        score = 0
        if _is_document_status_request(content):
            score -= 4
        if _looks_like_processing_placeholder_reply(content):
            score -= 3
        if any(
            token in lowered
            for token in (
                "vzor",
                "zmluv",
                "template",
                "draft",
                "contract",
                "agreement",
                "podiel",
                "spoloÄnÃ­k",
                "spolocnik",
                "share transfer",
                "obchodnÃ½ podiel",
                "obchodny podiel",
            )
        ):
            score += 2
        if any(token in lowered for token in ("1)", "2)", "3)", "clause", "article")):
            score += 2
        return score, len(content)

    return max(candidates, key=_score)


def _normalize_document_lines(content: str) -> List[str]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return []
    filtered: List[str] = []
    for line in lines:
        lowered = line.lower()
        if "pdf" in lowered and "?" in line:
            continue
        filtered.append(line)
    return filtered


def _extract_document_facts(
    source_lines: List[str],
    case_update: dict[str, Any] | None = None,
) -> dict[str, str]:
    text = _repair_common_mojibake(" ".join(source_lines))
    case = case_update.get("case", {}) if isinstance(case_update, dict) else {}
    next_discussion = case.get("next_discussion", {}) if isinstance(case, dict) else {}

    def _capture(pattern: str, default: str, flags: int = re.IGNORECASE) -> str:
        match = re.search(pattern, text, flags)
        if not match:
            return default
        return " ".join(match.group(1).strip().split())

    def _capture_line_value(labels: tuple[str, ...], default: str) -> str:
        for raw_line in source_lines:
            line = _repair_common_mojibake(raw_line).strip()
            if not line:
                continue
            line = re.sub(r"^[\-\*\s]+", "", line)
            line = re.sub(r"\*\*", "", line)
            canonical_line = _canonicalize_document_text(line)
            for label in labels:
                canonical_label = _canonicalize_document_text(label).rstrip(":")
                if not canonical_line.startswith(canonical_label):
                    continue
                separator_index = line.find(":")
                if separator_index < 0:
                    continue
                value = " ".join(line[separator_index + 1 :].strip().split())
                return value or default
        return default

    def _case_text(path: tuple[str, ...], default: str) -> str:
        node: Any = case_update
        for part in path:
            if not isinstance(node, dict):
                return default
            node = node.get(part)
        if node is None:
            return default
        value = str(node).strip()
        return value or default

    parties_line = _capture(r"zmluvne strany:\s*(.+?)(?:\s+\d+\)|$)", "")
    prenajimatel = _capture_line_value(
        ("prenajimatel", "prenajímateľ", "landlord", "lessor"),
        "Prenajimatel [doplnit udaje]",
    )
    najomca = _capture_line_value(
        ("najomca", "nájomca", "podnajomnik", "podnájomník", "tenant", "subtenant"),
        "Najomca [doplnit udaje]",
    )
    if parties_line and "doplnit" in prenajimatel.lower():
        prenajimatel = parties_line
    predmet = _capture_line_value(
        ("adresa nehnutelnosti", "adresa nehnuteľnosti", "adresa bytu", "adresa domu"),
        "",
    )
    if not predmet:
        predmet = _capture(
            r"(?:predmet\s+n[áa]jmu|adresa\s+bytu|adresa\s+domu|adresa\s+nehnute[ľl]nosti|byt\s+na\s+adrese|dom\s+na\s+adrese)\s*:?\s*(.+?)(?:\.|\s+\d+\)|$)",
            "",
        )
    if not predmet:
        predmet = _capture(
            r"nach[áa]dzaj[úu]ci\s+sa\s+na\s+adrese\s+(.+?)(?:\.|\s+\d+\)|$)",
            "",
        )
    if not predmet:
        predmet = "Nehnuteľnosť [adresa a identifikácia]"
    elif "nachadz" not in _canonicalize_document_text(predmet) and "adrese " not in _canonicalize_document_text(predmet):
        predmet = f"Nehnuteľnosť nachádzajúca sa na adrese {predmet}"
    doba = _capture_line_value(
        ("doba prenajmu", "doba prenájmu", "doba najmu", "doba nájmu"),
        "",
    )
    if not doba:
        doba = _capture(
            r"(?:doba\s+n[áa]jmu|doba\s+pren[áa]jmu|zmluva\s+sa\s+uzatv[áa]ra\s+na\s+dobu)\s*:?\s*(.+?)(?:\.|\s+\d+\)|$)",
            "Na dobu určitú 1 rok",
        )
    najomne = _capture_line_value(
        ("mesacne najomne", "mesačné nájomné", "najomne", "nájomné", "mesacny najom", "mesačný nájom"),
        "",
    )
    if not najomne:
        najomne = _capture(
            r"(?:n[áa]jomn[ée]|v[ýy][šs]ka\s+n[áa]jmu|mesa[čc]n[ýy]\s+n[áa]jom)\s*(?:je\s+stanoven[ýy]\s+na|je|:)?\s*([0-9\s]+(?:[.,][0-9]{1,2})?\s*(?:eur|eu|€)(?:\s+mesa[čc]ne)?)",
            "Nájomné [doplniť sumu], splatné do 5. dňa v mesiaci",
        )
    advance = _capture(r"platba vopred:\s*(.+?)(?:\s+\d+\)|$)", "2 mesačné nájomné vopred")
    deposit = _capture(r"kaucia:\s*(.+?)(?:\s+\d+\)|$)", "1 mesačné nájomné")
    notice = _capture(
        r"((?:v[ýy]povedn[áa]\s+lehota|v[ýy]povednou\s+lehotou|vypovedou|v[ýy]pove[ďd]ou)[^.]+)",
        "Výpovedná lehota 1 mesiac, doručenie písomne aj emailom",
    )
    payment_payer = _capture_line_value(
        ("platitel", "platiteľ", "payer", "dlznik", "dlžník"),
        "Platiteľ bude identifikovaný pred podpisom.",
    )
    if _is_missing_document_fact(payment_payer) or "bude identifikov" in _canonicalize_document_text(payment_payer):
        payment_payer = _capture(
            r"(?:platite[ľl]|payer|dl[žz]n[íi]k)\s*:\s*([^.;\n]+)",
            "Platiteľ bude identifikovaný pred podpisom.",
        )
    payment_recipient = _capture_line_value(
        ("prijemca", "príjemca", "recipient", "veritel", "veriteľ"),
        "Príjemca bude identifikovaný pred podpisom.",
    )
    if _is_missing_document_fact(payment_recipient) or "bude identifikov" in _canonicalize_document_text(payment_recipient):
        payment_recipient = _capture(
            r"(?:pr[íi]jemca|recipient|verite[ľl])\s*:\s*([^.;\n]+)",
            "Príjemca bude identifikovaný pred podpisom.",
        )
    payment_amount = _capture_line_value(("suma", "ciastka", "čiastka", "amount"), "")
    if not payment_amount:
        payment_amount = _capture(
            r"\b([0-9\s]+(?:[.,][0-9]{1,2})?\s*(?:eur|eu|€))\b",
            "Suma bude doplnená pred podpisom.",
        )
    payment_date = _capture_line_value(
        (
            "datum platby",
            "dátum platby",
            "datum splatnosti / platby",
            "dátum splatnosti / platby",
            "datum splatnosti",
            "dátum splatnosti",
            "payment date",
            "uhradene dna",
            "uhradené dňa",
        ),
        "Dátum platby bude doplnený pred podpisom.",
    )
    if "bude doplnen" in _canonicalize_document_text(payment_date):
        payment_date = _capture(
            r"(?:d[áa]tum platby|payment date|uhraden[ée] d[ňn]a)\s*:\s*(.+?)(?=\s+(?:[úu]čel platby|payment purpose|sp[ôo]sob platby|payment method)\s*:|$)",
            "Dátum platby bude doplnený pred podpisom.",
        )
    if "bude doplnen" in _canonicalize_document_text(payment_date):
        payment_date = _capture(
            r"(?:d[áa]tum splatnosti / platby|d[áa]tum splatnosti|splatnos[ťt]|splatn[ée]\s+k)\s*:?\s*([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})",
            payment_date,
        )
    payment_purpose = _capture_line_value(
        ("ucel platby", "účel platby", "payment purpose", "dovod platby", "dôvod platby"),
        "",
    )
    if not payment_purpose:
        payment_purpose = _capture(
            r"(?:[úu]čel platby|payment purpose|d[ôo]vod platby)\s*:\s*(.+?)(?=\s+(?:sp[ôo]sob platby|payment method)\s*:|\s+Pripravil som\b|\s+Prepared\b|$)",
            "",
        )
    if not payment_purpose:
        payment_purpose = _capture(
            r"(?:za|na)\s+([^.;\n]+?(?:fakt[úu]r[ua]|n[áa]jom|p[ôo]j[čc]k[au]|sl[uú][žz]b[uy]|tovar|dielo)[^.;\n]*)",
            "Účel platby bude doplnený pred podpisom.",
        )
    if _is_missing_document_fact(payment_purpose) or "bude doplnen" in _canonicalize_document_text(payment_purpose):
        payment_purpose = _capture(
            r"(?:[úu]čel platby|na)\s*:?\s*([^.;\n]*spl[áa]tk[au]\s+auta[^.;\n]*)",
            payment_purpose,
        )
    payment_method = _capture_line_value(
        ("sposob platby", "spôsob platby", "payment method"),
        "Spôsob platby bude doplnený pred podpisom.",
    )
    payment_sentence_facts = _extract_payment_confirmation_sentence_facts(text)
    if payment_sentence_facts:
        payment_payer = payment_sentence_facts.get("payment_payer", payment_payer)
        payment_recipient = payment_sentence_facts.get("payment_recipient", payment_recipient)
        payment_amount = payment_sentence_facts.get("payment_amount", payment_amount)
        payment_date = payment_sentence_facts.get("payment_date", payment_date)
        payment_purpose = payment_sentence_facts.get("payment_purpose", payment_purpose)
        payment_method = payment_sentence_facts.get("payment_method", payment_method)

    client_name = _case_text(("case", "parties", "client", "name"), "Klient")
    opponent_name = _case_text(("case", "parties", "opponent", "name"), "Protistrana")
    topic = _case_text(("case", "matter", "topic"), "pravny_problem")
    facts_summary = _case_text(("case", "matter", "facts_summary"), "Právny problém podľa diskusie.")
    client_goal = _case_text(("case", "matter", "client_goal"), "Dosiahnuť primerané právne riešenie.")
    scheduled_for = _case_text(("case", "next_discussion", "scheduled_for"), "")
    agenda_items = next_discussion.get("agenda", []) if isinstance(next_discussion, dict) else []
    agenda = ", ".join(str(item).strip() for item in agenda_items if str(item).strip())
    company_name = _capture(
        r"(?:firma|firmu|fima|spoloÄnosÅ¥|spolocnost|spoločnosť)\s+([^,.;\n]+?(?:s\.r\.o\.|a\.s\.|s\. r\. o\.))",
        "SpoloÄnosÅ¥ [doplnit obchodnÃ© meno]",
    )
    if _is_missing_document_fact(company_name):
        company_name = _capture(
            r"Verified company name:\s*([^.;\n]+?(?:s\.r\.o\.|a\.s\.|s\. r\. o\.))",
            company_name,
        )
    company_seat = _capture(
        r"(?:s\.r\.o\.|a\.s\.|s\. r\. o\.)\s*,\s*([^.;\n]+)",
        "SÃ­dlo spoloÄnosti [doplnit]",
    )
    if _is_missing_document_fact(company_seat):
        company_seat = _capture(r"Verified seat:\s*([^.;\n]+)", company_seat)
    company_identifier = _capture(
        r"(?:iÄo|ičo|ico|Verified registration number)\s*[:=]?\s*([0-9]{6,10})",
        "[doplnit IÄŒO]",
    )
    if _is_missing_document_fact(payment_recipient) and not _is_missing_document_fact(company_name):
        company_parts = [
            company_name,
            f"IČO: {company_identifier}" if not _is_missing_document_fact(company_identifier) else "",
            company_seat if not _is_missing_document_fact(company_seat) else "",
        ]
        payment_recipient = ", ".join(part for part in company_parts if part)
    transfer_share = _capture(r"(\d{1,3}\s*%)", "50 %")
    transfer_price = _capture(
        r"(?:cena prevodu(?: podielu)?(?: je)?|kÃºpna cena|kupna cena|odplata(?: za prevod)?)\s*[:=]?\s*([0-9\s]+(?:[.,][0-9]{1,2})?\s*(?:eur|eu|â‚¬))",
        "",
    )
    if not transfer_price.strip():
        transfer_price = _capture(r"\b([0-9\s]+(?:[.,][0-9]{1,2})?\s*(?:eur|eu|â‚¬))\b", "0 EUR")
    transferor_name = "SÃºÄasnÃ½ spoloÄnÃ­k / prevodca [doplnit Ãºdaje]"
    if "manÅ¾elka" in text.lower() or "manzelka" in text.lower():
        transferor_name = "SÃºÄasnÃ½ spoloÄnÃ­k / prevodca (manÅ¾elka) [doplnit Ãºdaje]"
    transferee_name = client_name if client_name != "Klient" else "NovÃ½ spoloÄnÃ­k / nadobÃºdateÄ¾ [doplnit Ãºdaje]"
    if "konateÄ¾ka" in text.lower() or "konatelka" in text.lower():
        transferor_name = "SÃºÄasnÃ½ spoloÄnÃ­k / konateÄ¾ka [doplnit Ãºdaje]"
    filing_authority = "ObchodnÃ½ register / slovensko.sk"
    estimated_timeline = _capture(
        r"(niekoÄ¾ko tÃ½Å¾dÅˆov|niekolko tyzdnov|[0-9]+\s*(?:pracovnÃ½ch|pracovnych)\s+dnÃ­|[0-9]+\s*dnÃ­)",
        "Spravidla niekoÄ¾ko pracovnÃ½ch dnÃ­ aÅ¾ tÃ½Å¾dÅˆov po Ãºplnom podanÃ­.",
    )

    return {
        "prenajimatel": prenajimatel,
        "najomca": najomca,
        "predmet": predmet,
        "doba": doba,
        "najomne": najomne,
        "advance": advance,
        "deposit": deposit,
        "notice": notice,
        "payment_payer": payment_payer,
        "payment_recipient": payment_recipient,
        "payment_amount": payment_amount,
        "payment_date": payment_date,
        "payment_purpose": payment_purpose,
        "payment_method": payment_method,
        "client_name": client_name,
        "opponent_name": opponent_name,
        "topic": topic,
        "facts_summary": facts_summary,
        "client_goal": client_goal,
        "scheduled_for": scheduled_for,
        "agenda": agenda or "Doplniť ďalší postup podľa vývoja komunikácie.",
        "company_name": company_name,
        "company_seat": company_seat,
        "company_identifier": company_identifier,
        "transfer_share": transfer_share,
        "transfer_price": transfer_price,
        "transferor_name": transferor_name,
        "transferee_name": transferee_name,
        "filing_authority": filing_authority,
        "estimated_timeline": estimated_timeline,
    }


def _extract_payment_confirmation_sentence_facts(text: str) -> dict[str, str]:
    normalized = " ".join(_repair_common_mojibake(text).split())
    pattern = re.compile(
        r"Ja,\s*(?P<payer>.+?),\s*bytom\s*(?P<payer_address>.+?),\s*"
        r"t[ýy]mto\s+potvrdzujem,\s*[žz]e\s+som\s+d[ňn]a\s*"
        r"(?P<payment_date>.+?)\s+zaplatil\s+sumu\s*"
        r"(?P<payment_amount>[0-9\s]+(?:[.,][0-9]{1,2})?\s*(?:eur|eu|€)(?:\s*\([^)]*\))?)\s+"
        r"(?:svojmu\s+susedovi|pr[íi]jemcovi|verite[ľl]ovi),\s*"
        r"(?P<recipient>.+?),\s*bytom\s*(?P<recipient_address>.+?),\s*"
        r"(?P<payment_method>prevodom\s+na\s+[úu]čet|bankov[ýy]m\s+prevodom|v\s+hotovosti)",
        flags=re.IGNORECASE,
    )
    matches = list(pattern.finditer(normalized))
    if not matches:
        return {}
    for match in reversed(matches):
        values = {key: " ".join(value.strip().split()) for key, value in match.groupdict().items()}
        if any("[" in value or "]" in value for value in values.values()):
            continue
        payer = values["payer"].strip(" ,.")
        payer_address = values["payer_address"].strip(" ,.")
        recipient = values["recipient"].strip(" ,.")
        recipient_address = values["recipient_address"].strip(" ,.")
        amount = values["payment_amount"].strip(" ,.")
        method = values["payment_method"].strip(" ,.")
        return {
            "payment_payer": f"{payer}, bytom {payer_address}",
            "payment_recipient": f"{recipient}, bytom {recipient_address}",
            "payment_amount": amount,
            "payment_date": values["payment_date"].strip(" ,."),
            "payment_purpose": f"zaplatenie sumy {amount}",
            "payment_method": method,
        }
    return {}


def _apply_user_profile_document_defaults(
    *, facts: dict[str, str], user_profile: User | None
) -> dict[str, str]:
    if user_profile is None:
        return facts
    profile_identity = _format_user_profile_document_identity(user_profile)
    if not profile_identity:
        return facts
    enriched = dict(facts)
    if _is_missing_document_fact(enriched.get("prenajimatel")):
        enriched["prenajimatel"] = profile_identity
    if _is_missing_document_fact(enriched.get("najomca")):
        enriched["najomca"] = profile_identity
    if _is_missing_document_fact(enriched.get("client_name")):
        enriched["client_name"] = profile_identity
    if _is_missing_document_fact(enriched.get("transferor_name")):
        enriched["transferor_name"] = profile_identity
    if _is_missing_document_fact(enriched.get("payment_payer")):
        enriched["payment_payer"] = profile_identity
    return enriched


def _sanitize_missing_document_facts(facts: dict[str, str]) -> dict[str, str]:
    enriched = dict(facts)
    if _is_missing_document_fact(enriched.get("prenajimatel")):
        opponent_name = enriched.get("opponent_name")
        enriched["prenajimatel"] = (
            str(opponent_name)
            if not _is_missing_document_fact(opponent_name)
            else "Údaje prenajímateľa budú doplnené pred podpisom."
        )
    if _is_missing_document_fact(enriched.get("najomca")):
        client_name = enriched.get("client_name")
        enriched["najomca"] = (
            str(client_name)
            if not _is_missing_document_fact(client_name)
            else "Údaje nájomcu budú doplnené pred podpisom."
        )
    if _is_missing_document_fact(enriched.get("client_name")):
        enriched["client_name"] = "Klient bude identifikovaný pred podpisom alebo podaním."
    if _is_missing_document_fact(enriched.get("transferor_name")):
        enriched["transferor_name"] = "Prevodca bude identifikovaný pred podpisom alebo podaním."
    if _is_missing_document_fact(enriched.get("transferee_name")):
        enriched["transferee_name"] = "Nadobúdateľ bude identifikovaný pred podpisom alebo podaním."
    if _is_missing_document_fact(enriched.get("payment_payer")):
        opponent_name = enriched.get("opponent_name")
        enriched["payment_payer"] = (
            str(opponent_name)
            if not _is_missing_document_fact(opponent_name)
            else "Platiteľ bude identifikovaný pred podpisom."
        )
    if _is_missing_document_fact(enriched.get("payment_recipient")):
        client_name = enriched.get("client_name")
        enriched["payment_recipient"] = (
            str(client_name)
            if not _is_missing_document_fact(client_name)
            else "Príjemca bude identifikovaný pred podpisom."
        )
    return enriched


def _format_user_profile_document_identity(user: User) -> str:
    display_name = _user_profile_document_display_name(user)
    parts: list[str] = [display_name] if display_name else []
    address_parts = _user_profile_document_address(user)
    if address_parts:
        parts.append(", ".join(address_parts))
    identity_parts = []
    if user.date_of_birth:
        identity_parts.append(f"datum narodenia: {user.date_of_birth}")
    if user.social_security_number:
        identity_parts.append(f"rodne cislo: {user.social_security_number}")
    if user.identity_card_number:
        identity_parts.append(f"OP: {user.identity_card_number}")
    if user.tax_number:
        identity_parts.append(f"DIC: {user.tax_number}")
    if identity_parts:
        parts.append("; ".join(identity_parts))
    return ", ".join(part for part in parts if part.strip())


def _user_profile_document_display_name(user: User) -> str:
    first_last = " ".join(part for part in (user.first_name, user.last_name) if part)
    if first_last.strip():
        return first_last.strip()
    full_name = (user.full_name or "").strip()
    if full_name and not _looks_like_phone_number(full_name):
        return full_name
    return ""


def _user_profile_document_address(user: User) -> list[str]:
    return [
        value
        for value in (
            user.address,
            " ".join(part for part in (user.zip_code, user.city) if part),
            user.country,
        )
        if value
    ]


def _looks_like_phone_number(value: str) -> bool:
    digits = re.sub(r"\D+", "", value)
    if len(digits) < 7:
        return False
    remainder = re.sub(r"[\d\s+().-]+", "", value)
    return not remainder.strip()


def _is_missing_document_fact(value: str | None) -> bool:
    if not value:
        return True
    lowered = _canonicalize_document_text(value)
    placeholder_tokens = (
        "doplnit",
        "doplni",
        "[",
        "]",
        "vase meno",
        "vasa adresa",
        "vasu adresu",
        "meno prenajimatela",
        "adresa prenajimatela",
        "meno najomcu",
        "adresa najomcu",
        "protistrana",
        "klient",
    )
    return any(token in lowered for token in placeholder_tokens)


def _build_standard_slovak_agreement_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Nájomná zmluva",
        "uzatvorená podľa § 663 a nasl. Občianskeho zákonníka",
        "",
        "Čl. I - Zmluvné strany",
        f"Prenajímateľ: {facts['prenajimatel']}",
        f"Nájomca: {facts['najomca']}",
        "",
        "Čl. II - Predmet nájmu",
        _with_period(facts["predmet"]),
        "",
        "Čl. III - Doba nájmu",
        _with_period(facts["doba"]),
        "",
        "Čl. IV - Nájomné a platobné podmienky",
        f"Nájomné: {_with_period(facts['najomne'])}",
        f"Platba vopred: {_with_period(facts['advance'])}",
        f"Kaucia: {_with_period(facts['deposit'])}",
        "",
        "Čl. V - Práva a povinnosti zmluvných strán",
        "Nájomca je povinný užívať predmet nájmu riadne, šetrne a v súlade so zmluvou.",
        "Prenajímateľ je povinný odovzdať predmet nájmu spôsobilý na dohodnuté užívanie.",
        "",
        "Čl. VI - Skončenie nájmu",
        _with_period(facts["notice"]),
        "",
        "Čl. VII - Záverečné ustanovenia",
        "Zmluva nadobúda platnosť dňom podpisu oboma zmluvnými stranami.",
        "Zmeny zmluvy je možné vykonať len písomným dodatkom.",
        "",
        "V [mesto], dňa [dátum]",
        "",
        "Podpis prenajímateľa: ____________________________",
        "Podpis nájomcu: _________________________________",
    ]


def _build_slovak_rental_inventory_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Inventárny zoznam bytu",
        "",
        f"Byt: {_with_period(facts['predmet'])}",
        f"Prenajímateľ: {facts['prenajimatel']}",
        f"Nájomca: {facts['najomca']}",
        "",
        "Vybavenie a stav pri odovzdaní:",
        "1. Kuchyňa a spotrebiče: [doplniť stav a príslušenstvo].",
        "2. Kúpeľňa a sanita: [doplniť stav].",
        "3. Nábytok a zariadenie izieb: [doplniť položky].",
        "4. Kľúče, čipy a ovládače: [doplniť počet].",
        "5. Počiatočné stavy meračov: elektrina [ ], voda [ ], plyn [ ].",
        "",
        "Nájomca potvrdzuje, že inventárny zoznam zodpovedá skutočnému stavu bytu pri prevzatí.",
        "",
        "Podpis prenajímateľa: ____________________________",
        "Podpis nájomcu: _________________________________",
    ]


def _build_slovak_rental_handover_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Protokol o odovzdaní a prevzatí bytu",
        "",
        f"Predmet odovzdania: {_with_period(facts['predmet'])}",
        f"Prenajímateľ: {facts['prenajimatel']}",
        f"Nájomca: {facts['najomca']}",
        "",
        "Stav bytu pri odovzdaní:",
        "Byt sa odovzdáva v stave spôsobilom na riadne užívanie, s výhradami uvedenými nižšie:",
        "[doplniť vady, poškodenia alebo poznámky]",
        "",
        "Odovzdané položky:",
        "1. Kľúče / čipy / ovládače: [doplniť].",
        "2. Inventárny zoznam: tvorí prílohu tohto protokolu.",
        "3. Fotodokumentácia stavu bytu: [áno/nie].",
        "",
        "Nájomca prevzatím potvrdzuje, že bol oboznámený so stavom bytu, vybavením a pravidlami užívania.",
        "",
        "V [mesto], dňa [dátum]",
        "",
        "Podpis prenajímateľa: ____________________________",
        "Podpis nájomcu: _________________________________",
    ]


def _build_standard_english_agreement_lines(facts: dict[str, str]) -> List[str]:
    return [
        "RESIDENTIAL LEASE AGREEMENT",
        "",
        "Article I - Parties",
        f"Landlord: {facts['prenajimatel']}",
        f"Tenant: {facts['najomca']}",
        "",
        "Article II - Leased Premises",
        _with_period(facts["predmet"]),
        "",
        "Article III - Lease Term",
        _with_period(facts["doba"]),
        "",
        "Article IV - Rent and Payments",
        f"Rent: {_with_period(facts['najomne'])}",
        f"Advance payment: {_with_period(facts['advance'])}",
        f"Security deposit: {_with_period(facts['deposit'])}",
        "",
        "Article V - Termination",
        _with_period(facts["notice"]),
        "",
        "Article VI - Final Provisions",
        "This agreement becomes effective upon signature by both parties.",
        "Any amendment must be made in writing.",
        "",
        "Signed at [city], on [date]",
        "",
        "Landlord signature: ____________________________",
        "Tenant signature: ______________________________",
    ]


def _build_slovak_payment_confirmation_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Potvrdenie o zaplatení",
        "",
        f"Platiteľ: {facts['payment_payer']}",
        f"Príjemca: {facts['payment_recipient']}",
        f"Suma: {facts['payment_amount']}",
        f"Dátum platby: {facts['payment_date']}",
        f"Účel platby: {facts['payment_purpose']}",
        f"Spôsob platby: {facts['payment_method']}",
        "",
        "Vyhlásenie:",
        (
            "Príjemca týmto potvrdzuje, že od platiteľa prijal vyššie uvedenú platbu "
            "v uvedenej sume a na uvedený účel."
        ),
        (
            "Toto potvrdenie slúži ako písomný doklad o prijatí platby; pred podpisom "
            "je potrebné doplniť alebo overiť všetky chýbajúce identifikačné údaje."
        ),
        "",
        "V [mesto], dňa [dátum vystavenia]",
        "",
        "Podpis príjemcu: _______________________________",
    ]


def _build_english_payment_confirmation_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Payment Confirmation",
        "",
        f"Payer: {facts['payment_payer']}",
        f"Recipient: {facts['payment_recipient']}",
        f"Amount: {facts['payment_amount']}",
        f"Payment date: {facts['payment_date']}",
        f"Payment purpose: {facts['payment_purpose']}",
        f"Payment method: {facts['payment_method']}",
        "",
        "Statement:",
        (
            "The recipient confirms receipt of the payment identified above from the "
            "payer in the stated amount and for the stated purpose."
        ),
        (
            "This confirmation is a written payment record; any missing identification "
            "details should be completed or verified before signature."
        ),
        "",
        "Signed at [city], on [date of issue]",
        "",
        "Recipient signature: ____________________________",
    ]


def _build_slovak_easement_demand_lines(facts: dict[str, str]) -> List[str]:
    return [
        "PredÅ¾alobnÃ¡ vÃ½zva na umoÅ¾nenie vÃ½konu vecnÃ©ho bremena",
        "",
        f"AdresÃ¡t: {facts['opponent_name']}",
        f"OdosielateÄ¾: {facts['client_name']}",
        "",
        "Vec:",
        "VÃ½zva na zdrÅ¾anie sa zÃ¡sahu do vÃ½konu vecnÃ©ho bremena a na vytvorenie prÃ­stupu",
        "",
        "SkutkovÃ½ zÃ¡klad:",
        _with_period(facts["facts_summary"]),
        "",
        "PrÃ¡vny zÃ¡ujem klienta:",
        _with_period(facts["client_goal"]),
        "",
        "PoÅ¾iadavka:",
        "Å½iadam, aby ste sa zdrÅ¾ali akÃ½chkoÄ¾vek stavebnÃ½ch zÃ¡sahov, ktorÃ© by znemoÅ¾nili alebo podstatne sÅ¥aÅ¾ili vÃ½kon vecnÃ©ho bremena.",
        "ZÃ¡roveÅˆ Å¾iadam, aby ste na mieste vÃ½konu vecnÃ©ho bremena zabezpeÄili primeranÃ½ vstup, najmÃ¤ brÃ¡nku alebo inÃ© technickÃ© rieÅ¡enie umoÅ¾ÅˆujÃºce prÃ­stup k plynovej prÃ­pojke.",
        "",
        "Lehota na plnenie:",
        "Å½iadam o pÃ­somnÃ© stanovisko bez zbytoÄnÃ©ho odkladu, najneskÃ´r do 7 dnÃ­ od doruÄenia tejto vÃ½zvy.",
        "",
        "Upozornenie:",
        "Ak nedÃ´jde k nÃ¡prave, klient zvÃ¡Å¾i ÄalÅ¡ie prÃ¡vne kroky vrÃ¡tane nÃ¡vrhu na neodkladnÃ© opatrenie a uplatnenia sÃºdnej ochrany.",
        "",
        "NavrhovanÃ© podklady k prÃ­lohe:",
        "1. Zmluva alebo rozhodnutie o vecnom bremene.",
        "2. PÃ­somnÃ¡ komunikÃ¡cia so susedom.",
        "3. FotodokumentÃ¡cia miesta prÃ­pojky a plÃ¡novanÃ©ho plotu.",
        "",
        "PoznÃ¡mka k ÄalÅ¡iemu postupu:",
        _with_period(facts["agenda"]),
        "",
        "Podpis klienta / zÃ¡stupcu: ____________________________",
    ]


def _build_english_easement_demand_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Formal demand regarding easement access",
        "",
        f"Recipient: {facts['opponent_name']}",
        f"Sender: {facts['client_name']}",
        "",
        "Subject:",
        "Demand to refrain from interfering with easement access and to preserve an entry point",
        "",
        "Factual background:",
        _with_period(facts["facts_summary"]),
        "",
        "Client objective:",
        _with_period(facts["client_goal"]),
        "",
        "Demand:",
        "You are requested to refrain from any construction that would prevent or materially hinder the exercise of the easement.",
        "You are further requested to provide a gate or another technically suitable access point at the easement location so that the gas connection remains reachable.",
        "",
        "Response deadline:",
        "Please provide a written response within 7 days of delivery of this notice.",
        "",
        "Notice:",
        "If the matter is not resolved, the client may pursue further legal remedies, including interim relief and court protection.",
        "",
        "Recommended attachments:",
        "1. Easement agreement or decision.",
        "2. Written communication with the neighbor.",
        "3. Photos of the gas connection and the planned wall.",
        "",
        "Next-step note:",
        _with_period(facts["agenda"]),
        "",
        "Client / counsel signature: ____________________________",
    ]


def _build_slovak_share_transfer_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Pracovny balik dokumentacie k prevodu obchodneho podielu v s.r.o.",
        "",
        "Identifikacia spolocnosti",
        f"Obchodne meno: {facts['company_name']}",
        f"Sidlo: {facts['company_seat']}",
        f"ICO: {facts['company_identifier']}",
        "",
        "Zakladne parametre prevodu",
        f"Predmet prevodu: obchodny podiel vo vyske {facts['transfer_share']}.",
        f"Odplata za prevod: {_with_period(facts['transfer_price'])}",
        f"Prevodca: {facts['transferor_name']}",
        f"Nadobudatel: {facts['transferee_name']}",
        "",
        "1. Navrh zmluvy o prevode obchodneho podielu",
        "Clanok I - Zmluvne strany",
        f"Prevodca: {facts['transferor_name']}.",
        f"Nadobudatel: {facts['transferee_name']}.",
        "",
        "Clanok II - Predmet prevodu",
        f"Prevodca prevadza na nadobudatela obchodny podiel v spolocnosti {facts['company_name']} vo vyske {facts['transfer_share']}.",
        "",
        "Clanok III - Odplata",
        f"Zmluvne strany sa dohodli na odplate {_with_period(facts['transfer_price'])}",
        "",
        "Clanok IV - Vyhlasenia stran",
        "Prevodca vyhlasuje, ze je opravneny s obchodnym podielom nakladat a ze podiel nie je zatazeny pravami tretich osob, ak sa v prilohach neuvedie inak.",
        "Nadobudatel vyhlasuje, ze pristupuje k spolocenskej zmluve a prebera prava a povinnosti spolocnika v rozsahu prevadzaneho podielu.",
        "",
        "2. Navrh rozhodnutia jedineho spolocnika / zapisnice",
        f"Spolocnost: {facts['company_name']}, ICO {facts['company_identifier']}, sidlo {facts['company_seat']}.",
        "Jediny spolocnik alebo valne zhromazdenie berie na vedomie prevod obchodneho podielu a schvaluje znenie zmluvy, ak to vyzaduje spolocenska zmluva.",
        f"Po ucinnosti prevodu bude spolocnicka struktura zapisana tak, aby nadobudatel {facts['transferee_name']} nadobudol podiel vo vyske {facts['transfer_share']}.",
        "",
        "3. Navrh aktualizovaneho uplneho znenia spolocenskej zmluvy / zakladatelskej listiny",
        f"Obchodne meno spolocnosti: {facts['company_name']}.",
        f"Sidlo spolocnosti: {facts['company_seat']}.",
        f"ICO: {facts['company_identifier']}.",
        "Ustanovenie o spolocnikoch a vkladoch sa upravi tak, aby zodpovedalo novej vlastnickej strukture po prevode podielu.",
        f"Novy spolocnik / nadobudatel: {facts['transferee_name']}.",
        f"Prevodca po prevode ponecha alebo prevedie podiel podla dohodnuteho rozsahu {facts['transfer_share']}.",
        "",
        "4. Podklady a prilohy pre obchodny register",
        "1. Zmluva o prevode obchodneho podielu s doplnenymi identifikacnymi udajmi stran.",
        "2. Rozhodnutie jedineho spolocnika alebo zapisnica z valneho zhromazdenia, ak to vyzaduje spolocenska zmluva alebo sa meni statutar / obchodne vedenie.",
        "3. Uplne znenie spolocenskej zmluvy alebo zakladatelskej listiny po zapracovani zmeny spolocnikov a podielov.",
        "4. Navrh na zapis zmeny do obchodneho registra vratane priloh podla typu zmeny.",
        "",
        "5. Prakticky postup podania",
        f"Podanie smeruje na: {facts['filing_authority']}.",
        "Najprv doplnte identifikacne udaje stran, presny rozsah podielu a pripadne zmeny v konateloch alebo sposobe konania.",
        "Nasledne pripravte podpisove verzie dokumentov a skontrolujte, ci spolocenska zmluva nevyzaduje osobitny suhlas alebo predkupne pravidla.",
        "Po podpise podajte navrh na zapis zmeny do obchodneho registra spolu so vsetkymi povinnymi prilohami.",
        "",
        "6. Odhad trvania",
        _with_period(facts["estimated_timeline"]),
        "",
        "Poznamka",
        "Tento vystup je pracovny balik draftov. Pred podpisom a podanim je potrebne doplnit presne identifikacne udaje, preverit spolocensku zmluvu a zvolit spravny balik priloh podla konkretnej zmeny.",
        "",
        "Podpis pravneho zastupcu / klienta: ____________________________",
    ]


def _build_slovak_share_transfer_agreement_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Clanok I - Zmluvne strany",
        f"Prevodca: {facts['transferor_name']}.",
        f"Nadobudatel: {facts['transferee_name']}.",
        "",
        "Clanok II - Identifikacia spolocnosti",
        f"Obchodne meno: {facts['company_name']}.",
        f"Sidlo: {facts['company_seat']}.",
        f"ICO: {facts['company_identifier']}.",
        "",
        "Clanok III - Predmet prevodu",
        f"Prevodca prevadza na nadobudatela obchodny podiel vo vyske {facts['transfer_share']}.",
        "",
        "Clanok IV - Odplata",
        f"Zmluvne strany sa dohodli na odplate {_with_period(facts['transfer_price'])}",
        "",
        "Clanok V - Vyhlasenia stran",
        "Prevodca vyhlasuje, ze je opravneny s podielom nakladat a podiel nie je zatazeny pravami tretich osob, ak sa v zmluve neuvedie inak.",
        "Nadobudatel vyhlasuje, ze pristupuje k spolocenskej zmluve a prebera prava a povinnosti spolocnika v rozsahu prevadzaneho podielu.",
        "",
        "Clanok VI - Ucinnost",
        "Tato zmluva nadobuda ucinnost dnom podpisu, ak zo spolocenskej zmluvy alebo zakona nevyplyva neskorsi okamih.",
        "",
        "Podpis prevodcu: ____________________________",
        "Podpis nadobudatela: ________________________",
    ]


def _build_slovak_share_transfer_minutes_lines(facts: dict[str, str]) -> List[str]:
    return [
        f"Spolocnost: {facts['company_name']}.",
        f"Sidlo: {facts['company_seat']}.",
        f"ICO: {facts['company_identifier']}.",
        "",
        "Program rokovania / rozhodnutia",
        "1. Vzatie na vedomie prevodu obchodneho podielu.",
        "2. Schvalenie znenia zmluvy o prevode obchodneho podielu, ak to vyzaduje spolocenska zmluva.",
        "3. Schvalenie aktualizovaneho uplneho znenia spolocenskej zmluvy / zakladatelskej listiny.",
        "",
        "Rozhodnutie",
        f"Schvaluje sa prevod obchodneho podielu vo vyske {facts['transfer_share']} z prevodcu {facts['transferor_name']} na nadobudatela {facts['transferee_name']}.",
        "Po ucinnosti prevodu sa zapise nova spolocnicka struktura do obchodneho registra.",
        "",
        "Poverenie",
        "Konatel alebo poverena osoba zabezpeci podpis dokumentov a podanie navrhu na zapis zmeny s prislusnymi prilohami.",
        "",
        "Podpis spolocnika / predsedajuceho: ____________________________",
    ]


def _build_slovak_share_transfer_articles_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Clanok I - Obchodne meno a sidlo spolocnosti",
        f"Obchodne meno: {facts['company_name']}.",
        f"Sidlo: {facts['company_seat']}.",
        f"ICO: {facts['company_identifier']}.",
        "",
        "Clanok II - Spolocnici a podiely",
        f"Novy spolocnik / nadobudatel: {facts['transferee_name']}.",
        f"Rozsah prevadzaneho podielu: {facts['transfer_share']}.",
        f"Prevodca: {facts['transferor_name']}.",
        "",
        "Clanok III - Vyhlasenie o zmene",
        "Ustanovenia o spolocnikoch, podieloch a vkladoch sa upravuju tak, aby zodpovedali novej vlastnickej strukture po prevode podielu.",
        "",
        "Clanok IV - Zaverecne ustanovenia",
        "Ostatne ustanovenia spolocenskej zmluvy / zakladatelskej listiny zostavaju nezmenene, ak sa dodatkom vyslovne neupravia.",
        "",
        "Podpis spolocnika / statutarneho organu: ____________________________",
    ]


def _build_slovak_share_transfer_registry_filing_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Navrh podania na zapis zmeny do obchodneho registra",
        "",
        "Identifikacia spolocnosti",
        f"Obchodne meno: {facts['company_name']}.",
        f"Sidlo: {facts['company_seat']}.",
        f"ICO: {facts['company_identifier']}.",
        "",
        "Predmet navrhu",
        f"Zapis zmeny spolocnika po prevode obchodneho podielu vo vyske {facts['transfer_share']}.",
        f"Prevodca: {facts['transferor_name']}.",
        f"Nadobudatel: {facts['transferee_name']}.",
        "",
        "Priloha k podaniu",
        "1. Zmluva o prevode obchodneho podielu s overenymi podpismi, ak to vyzaduje zakon alebo interny rezim spolocnosti.",
        "2. Rozhodnutie jedineho spolocnika / zapisnica valneho zhromazdenia, ak je potrebna.",
        "3. Spolocenska zmluva alebo zakladatelska listina podla struktury spolocnosti.",
        "4. Dalsie listiny pozadovane registrovym sudom alebo formularom ORSR.",
        "",
        "Poznamka k podaniu",
        f"Navrh sa podava cez {facts['filing_authority']} po podpise kompletneho balika dokumentov.",
        f"Orientacny cas vybavenia: {_with_period(facts['estimated_timeline'])}",
        "",
        "Podpis navrhovatela / splnomocnenej osoby: ____________________________",
    ]


def _build_english_share_transfer_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Working draft for a limited-liability company share transfer package",
        "",
        "Company identification",
        f"Company name: {facts['company_name']}",
        f"Registered seat: {facts['company_seat']}",
        f"Company ID: {facts['company_identifier']}",
        "",
        "Core transfer terms",
        f"Transferred share: {facts['transfer_share']}.",
        f"Transfer price: {_with_period(facts['transfer_price'])}",
        f"Transferor: {facts['transferor_name']}",
        f"Transferee: {facts['transferee_name']}",
        "",
        "1. Draft share transfer agreement",
        f"The transferor transfers a business share in {facts['company_name']} to the transferee in the amount of {facts['transfer_share']}.",
        f"The agreed consideration is {_with_period(facts['transfer_price'])}",
        "",
        "2. Supporting filings and resolutions",
        "1. Signed share transfer agreement with completed identification details.",
        "2. Sole shareholder decision or shareholders' meeting minutes if required by the constitutional documents or if management details also change.",
        "3. Articles of association or founding deed reflecting the new ownership structure.",
        "4. Registry filing package with all required annexes.",
        "",
        "3. Filing steps",
        f"Filing authority: {facts['filing_authority']}.",
        "Complete the party details, exact transferred share, and any changes to managing directors or signing powers.",
        "Check the company constitutional documents for consent or pre-emption requirements before signing.",
        "After execution, file the registry update with the complete annex package.",
        "",
        "Estimated timing",
        _with_period(facts["estimated_timeline"]),
        "",
        "Note",
        "This output is a working draft and checklist. Complete legal details should be verified before signature and filing.",
        "",
        "Counsel / client signature: ____________________________",
    ]


def _build_english_share_transfer_agreement_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Article I - Parties",
        f"Transferor: {facts['transferor_name']}.",
        f"Transferee: {facts['transferee_name']}.",
        "",
        "Article II - Company identification",
        f"Company name: {facts['company_name']}.",
        f"Registered seat: {facts['company_seat']}.",
        f"Company ID: {facts['company_identifier']}.",
        "",
        "Article III - Transferred share",
        f"The transferor transfers a business share in the amount of {facts['transfer_share']}.",
        "",
        "Article IV - Consideration",
        f"The agreed consideration is {_with_period(facts['transfer_price'])}",
        "",
        "Article V - Representations",
        "The transferor represents that the share may be transferred and is not encumbered unless expressly stated otherwise.",
        "The transferee joins the company's constitutional documents and assumes the related shareholder rights and obligations.",
        "",
        "Signatures",
        "Transferor: ____________________________",
        "Transferee: ____________________________",
    ]


def _build_english_share_transfer_minutes_lines(facts: dict[str, str]) -> List[str]:
    return [
        f"Company: {facts['company_name']}.",
        f"Registered seat: {facts['company_seat']}.",
        f"Company ID: {facts['company_identifier']}.",
        "",
        "Agenda",
        "1. Acknowledge the share transfer.",
        "2. Approve the share transfer agreement if required by the constitutional documents.",
        "3. Approve the updated articles / founding deed.",
        "",
        "Resolution",
        f"The company acknowledges the transfer of a {facts['transfer_share']} business share from {facts['transferor_name']} to {facts['transferee_name']}.",
        "The authorized representative is instructed to sign and file the registry update with the required annexes.",
        "",
        "Signature: ____________________________",
    ]


def _build_english_share_transfer_articles_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Article I - Company identification",
        f"Company name: {facts['company_name']}.",
        f"Registered seat: {facts['company_seat']}.",
        f"Company ID: {facts['company_identifier']}.",
        "",
        "Article II - Shareholders and holdings",
        f"Transferee / new shareholder: {facts['transferee_name']}.",
        f"Transferred share: {facts['transfer_share']}.",
        f"Transferor: {facts['transferor_name']}.",
        "",
        "Article III - Amendment",
        "The provisions dealing with shareholders, ownership percentages, and contributions are updated to reflect the post-transfer structure.",
        "",
        "Signature: ____________________________",
    ]


def _build_english_share_transfer_registry_filing_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Registry filing package for the share transfer update",
        "",
        "Company identification",
        f"Company name: {facts['company_name']}.",
        f"Registered seat: {facts['company_seat']}.",
        f"Company ID: {facts['company_identifier']}.",
        "",
        "Requested filing",
        f"Registration of the shareholder change following a transfer of {facts['transfer_share']}.",
        f"Transferor: {facts['transferor_name']}.",
        f"Transferee: {facts['transferee_name']}.",
        "",
        "Annex package",
        "1. Signed share transfer agreement.",
        "2. Sole shareholder decision / meeting minutes if required.",
        "3. Articles of association or founding deed.",
        "4. Any additional forms or annexes required by the registry court.",
        "",
        "Filing note",
        f"The filing should be submitted via {facts['filing_authority']} after the full package is finalized.",
        f"Indicative processing time: {_with_period(facts['estimated_timeline'])}",
        "",
        "Applicant / authorized representative signature: ____________________________",
    ]


def _build_generic_slovak_case_document_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Právne zhrnutie a návrh ďalšieho postupu",
        "",
        f"Klient: {facts['client_name']}",
        f"Protistrana: {facts['opponent_name']}",
        f"Téma: {facts['topic']}",
        "",
        "Skutkový stav:",
        _with_period(facts["facts_summary"]),
        "",
        "Cieľ klienta:",
        _with_period(facts["client_goal"]),
        "",
        "Odporúčaný postup:",
        "1. Zabezpečiť a usporiadať všetky relevantné listiny a komunikáciu.",
        "2. Písomne vyzvať protistranu na dobrovoľné riešenie.",
        "3. Vyhodnotiť potrebu predžalobnej výzvy alebo návrhu na súdnu ochranu.",
        "",
        "Ďalšia konzultácia:",
        _with_period(facts["agenda"]),
        "",
        "Podpis klienta / zástupcu: ____________________________",
    ]


def _build_generic_english_case_document_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Legal summary and next-step memorandum",
        "",
        f"Client: {facts['client_name']}",
        f"Counterparty: {facts['opponent_name']}",
        f"Topic: {facts['topic']}",
        "",
        "Facts:",
        _with_period(facts["facts_summary"]),
        "",
        "Client objective:",
        _with_period(facts["client_goal"]),
        "",
        "Recommended next steps:",
        "1. Organize the relevant documents and communications.",
        "2. Send a written request for voluntary resolution.",
        "3. Assess whether a formal demand or court filing is required.",
        "",
        "Next consultation:",
        _with_period(facts["agenda"]),
        "",
        "Client / counsel signature: ____________________________",
    ]


def _extract_case_update(content: str) -> dict[str, Any] | None:
    payload = _extract_case_update_payload(content)
    if not payload:
        return None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _extract_case_update_payload(content: str) -> str | None:
    bounds = _case_update_payload_bounds(content)
    if bounds is None:
        return None
    start_index, end_index = bounds
    json_start = content.find("{", start_index, end_index)
    if json_start < 0:
        return None
    return _extract_json_object(content[:end_index], json_start)


def _case_update_payload_bounds(content: str) -> tuple[int, int] | None:
    marker = re.search(r"\*{0,2}\s*CASE_UPDATE_JSON\s*:?\s*\*{0,2}", content, flags=re.IGNORECASE)
    if marker is not None:
        return marker.start(), len(content)

    fenced_json_pattern = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
    for match in fenced_json_pattern.finditer(content):
        candidate = match.group(1).strip()
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict) and isinstance(decoded.get("case"), dict):
            return match.start(), match.end()
    bare_json_bounds = _bare_json_payload_bounds(content, require_case=True)
    if bare_json_bounds is not None:
        return bare_json_bounds
    return None


def _technical_payload_bounds(content: str) -> tuple[int, int, str] | None:
    case_update_bounds = _case_update_payload_bounds(content)
    if case_update_bounds is not None:
        start_index, end_index = case_update_bounds
        return start_index, end_index, "json"

    fenced_payload_pattern = re.compile(r"```(json|xml)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
    for match in fenced_payload_pattern.finditer(content):
        language = (match.group(1) or "").strip().lower()
        candidate = match.group(2).strip()
        if language == "json" or _looks_like_json_payload(candidate):
            return match.start(), match.end(), "json"
        if language == "xml" or _looks_like_xml_payload(candidate):
            return match.start(), match.end(), "xml"

    bare_json_bounds = _bare_json_payload_bounds(content, require_case=False)
    if bare_json_bounds is not None:
        start_index, end_index = bare_json_bounds
        return start_index, end_index, "json"

    bare_xml_bounds = _bare_xml_payload_bounds(content)
    if bare_xml_bounds is not None:
        start_index, end_index = bare_xml_bounds
        return start_index, end_index, "xml"

    return None


def _bare_json_payload_bounds(content: str, *, require_case: bool) -> tuple[int, int] | None:
    for match in re.finditer(r"(?m)^[ \t]*(?=[{\[])", content):
        line_start = match.start()
        json_start = line_start
        while json_start < len(content) and content[json_start] in " \t":
            json_start += 1
        payload = _extract_json_value(content, json_start)
        if payload is None:
            continue
        end_index = json_start + len(payload)
        if content[end_index:].strip():
            continue
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if require_case and not (isinstance(decoded, dict) and isinstance(decoded.get("case"), dict)):
            continue
        if not require_case and not isinstance(decoded, (dict, list)):
            continue
        return line_start, end_index
    return None


def _bare_xml_payload_bounds(content: str) -> tuple[int, int] | None:
    for match in re.finditer(r"(?m)^[ \t]*(?=<\??[A-Za-z_])", content):
        line_start = match.start()
        xml_start = line_start
        while xml_start < len(content) and content[xml_start] in " \t":
            xml_start += 1
        candidate = content[xml_start:].strip()
        if _looks_like_xml_payload(candidate):
            return line_start, len(content)
    return None


def _looks_like_json_payload(content: str) -> bool:
    stripped = content.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _looks_like_xml_payload(content: str) -> bool:
    stripped = content.strip()
    if not stripped.startswith("<") or ">" not in stripped:
        return False
    if stripped.startswith("<!--"):
        return False
    return stripped.startswith("<?xml") or "</" in stripped or "/>" in stripped


def _extract_json_object(content: str, start_index: int) -> str | None:
    value = _extract_json_value(content, start_index)
    if value is None or not value.startswith("{"):
        return None
    return value


def _extract_json_value(content: str, start_index: int) -> str | None:
    if start_index >= len(content) or content[start_index] not in "{[":
        return None
    opening_to_closing = {"{": "}", "[": "]"}
    stack: list[str] = []
    depth = 0
    in_string = False
    escape = False
    for index in range(start_index, len(content)):
        char = content[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in opening_to_closing:
            stack.append(opening_to_closing[char])
            depth += 1
        elif stack and char == stack[-1]:
            stack.pop()
            depth -= 1
            if not stack and depth == 0:
                return content[start_index : index + 1]
    return None


def _detect_document_kind(
    source_lines: List[str],
    case_update: dict[str, Any] | None,
) -> Literal["rental_agreement", "easement_demand", "share_transfer", "payment_confirmation", "generic_case_document"]:
    combined = _canonicalize_document_text(" ".join(source_lines))
    case = case_update.get("case", {}) if isinstance(case_update, dict) else {}
    matter = case.get("matter", {}) if isinstance(case, dict) else {}
    topic = _canonicalize_document_text(str(matter.get("topic", "")))
    facts_summary = _canonicalize_document_text(str(matter.get("facts_summary", "")))
    client_goal = _canonicalize_document_text(str(matter.get("client_goal", "")))
    haystack = " ".join(part for part in (combined, topic, facts_summary, client_goal) if part)

    rental_tokens = (
        "prenaj",
        "nÃ¡jom",
        "najom",
        "lease",
        "landlord",
        "tenant",
        "byt",
    )
    easement_tokens = (
        "vecnÃ© bremeno",
        "vecne bremeno",
        "easement",
        "plynov",
        "prÃ­poj",
        "pripoj",
        "sused",
        "plot",
        "brÃ¡n",
        "brÃ¡nk",
        "brank",
    )
    share_transfer_tokens = (
        "prevod podielu",
        "obchodnÃ½ podiel",
        "obchodny podiel",
        "spoloÄnÃ­k",
        "spolocnik",
        "konateÄ¾",
        "konatel",
        "vlastnÃ­ckych prÃ¡v firmy",
        "vlastnickych prav firmy",
        "s.r.o.",
        "share transfer",
        "ownership transfer",
    )
    purchase_sale_tokens = (
        "kupno predajn",
        "kupno-predajn",
        "kupna zmluva",
        "predajna zmluva",
        "purchase agreement",
        "sale agreement",
    )
    payment_confirmation_tokens = (
        "potvrdenie o zaplat",
        "potvrdenie o platbe",
        "potvrdenie o uhrad",
        "potvrdenie o prijati plat",
        "potvrdenie prijatia plat",
        "doklad o zaplat",
        "doklad o uhrad",
        "payment confirmation",
        "confirmation of payment",
        "receipt of payment",
    )
    if any(token in haystack for token in purchase_sale_tokens):
        return "generic_case_document"
    if any(token in haystack for token in payment_confirmation_tokens):
        return "payment_confirmation"
    if any(token in haystack for token in rental_tokens):
        return "rental_agreement"
    if any(token in haystack for token in easement_tokens):
        return "easement_demand"
    if any(token in haystack for token in share_transfer_tokens):
        return "share_transfer"
    return "generic_case_document"


def _with_period(value: str) -> str:
    cleaned = value.strip()
    while cleaned.endswith("."):
        cleaned = cleaned[:-1].rstrip()
    return f"{cleaned}."


def _resolve_pdf_fonts(*, country: str, language: str | None) -> tuple[str, str]:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    if normalized_country in {"SK", "CZ", "DE", "AT"} or normalized_language.startswith(
        ("sk", "cs", "de")
    ):
        font_candidates: list[tuple[str, Path, Path]] = []
        for font_dir in _LINUX_DEJAVU_FONT_DIRS:
            font_candidates.extend(
                [
                    (
                        "AIJDejaVuSerif",
                        font_dir / "DejaVuSerif.ttf",
                        font_dir / "DejaVuSerif-Bold.ttf",
                    ),
                    (
                        "AIJDejaVuSans",
                        font_dir / "DejaVuSans.ttf",
                        font_dir / "DejaVuSans-Bold.ttf",
                    ),
                ]
            )
        for font_dir in _LINUX_LIBERATION_FONT_DIRS:
            font_candidates.extend(
                [
                    (
                        "AIJLiberationSerif",
                        font_dir / "LiberationSerif-Regular.ttf",
                        font_dir / "LiberationSerif-Bold.ttf",
                    ),
                    (
                        "AIJLiberationSans",
                        font_dir / "LiberationSans-Regular.ttf",
                        font_dir / "LiberationSans-Bold.ttf",
                    ),
                ]
            )
        font_candidates.extend(
            [
                (
                    "AIJTimesNewRoman",
                    _WINDOWS_FONT_DIR / "times.ttf",
                    _WINDOWS_FONT_DIR / "timesbd.ttf",
                ),
                (
                    "AIJArial",
                    _WINDOWS_FONT_DIR / "arial.ttf",
                    _WINDOWS_FONT_DIR / "arialbd.ttf",
                ),
                (
                    "AIJVera",
                    _REPORTLAB_FONT_DIR / "Vera.ttf",
                    _REPORTLAB_FONT_DIR / "VeraBd.ttf",
                ),
            ]
        )
        for family_name, regular_path, bold_path in font_candidates:
            family = _register_ttf_font_family(
                family_name=family_name,
                regular_path=regular_path,
                bold_path=bold_path,
            )
            if family is not None:
                return family
    return ("Helvetica", "Helvetica-Bold")


def _prefers_slovak_legal_pdf_profile(*, country: str, language: str | None) -> bool:
    normalized_country = (country or "").strip().upper()
    normalized_language = (language or "").strip().lower()
    return normalized_country == "SK" or normalized_language.startswith("sk")


def _register_ttf_font_family(
    *,
    family_name: str,
    regular_path: Path,
    bold_path: Path,
) -> tuple[str, str] | None:
    if not regular_path.exists() or not bold_path.exists():
        return None
    if family_name not in _REGISTERED_PDF_FONT_FAMILIES:
        try:
            pdfmetrics.registerFont(TTFont(family_name, str(regular_path)))
            pdfmetrics.registerFont(TTFont(f"{family_name}-Bold", str(bold_path)))
        except Exception:  # noqa: BLE001
            return None
        _REGISTERED_PDF_FONT_FAMILIES.add(family_name)
    return (family_name, f"{family_name}-Bold")


def _ai_jurisdicta_logo_ops(*, x: float, y: float, size: float) -> List[str]:
    if not (_LOGO_SVG_PRIMARY.exists() or _LOGO_SVG_FALLBACK.exists()):
        return []

    scale = size / 120.0
    teal = "0.106 0.498 0.557"
    dark = "0.043 0.071 0.125"
    gold = "0.843 0.659 0.310"
    ops: List[str] = [
        "q",
        f"{scale:.6f} 0 0 {-scale:.6f} {x:.2f} {y + size:.2f} cm",
        "1 J",
        "1 j",
        f"{teal} RG",
        "3 w",
        # outer frame (square fallback for rounded SVG frame)
        "6 6 108 108 re S",
        f"{dark} RG",
        "4 w",
        "60 26 m 60 74 l S",
        "34 44 m 60 34 l 86 44 l S",
        "3 w",
        "34 44 m 22 64 l S",
        "86 44 m 98 64 l S",
        f"{gold} rg",
    ]
    ops.extend(_pdf_circle_ops(22.0, 64.0, 6.0))
    ops.append("f")
    ops.extend(_pdf_circle_ops(98.0, 64.0, 6.0))
    ops.append("f")
    ops.append(f"{teal} rg")
    ops.extend(_pdf_circle_ops(60.0, 34.0, 6.0))
    ops.append("f")
    ops.append(f"{dark} rg")
    ops.append("44 74 32 18 re f")
    ops.append("Q")
    return ops


def _pdf_circle_ops(cx: float, cy: float, r: float) -> List[str]:
    k = 0.5522847498 * r
    x0 = cx - r
    x1 = cx + r
    y0 = cy - r
    y1 = cy + r
    return [
        f"{x1:.3f} {cy:.3f} m",
        f"{x1:.3f} {cy + k:.3f} {cx + k:.3f} {y1:.3f} {cx:.3f} {y1:.3f} c",
        f"{cx - k:.3f} {y1:.3f} {x0:.3f} {cy + k:.3f} {x0:.3f} {cy:.3f} c",
        f"{x0:.3f} {cy - k:.3f} {cx - k:.3f} {y0:.3f} {cx:.3f} {y0:.3f} c",
        f"{cx + k:.3f} {y0:.3f} {x1:.3f} {cy - k:.3f} {x1:.3f} {cy:.3f} c",
        "h",
    ]
