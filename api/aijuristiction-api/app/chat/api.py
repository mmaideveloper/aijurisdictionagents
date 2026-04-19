from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import logging
import re
import time
import textwrap
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile
from collections import deque
from collections.abc import Callable, Generator
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, List, Literal, Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from app.chat.core_runtime import core_message_role, run_orchestration
from app.chat.country_services import prepare_country_direct_reply
from app.flow_packs.api import get_flow_pack_store
from app.chat.intent_policy_service import (
    build_document_task_plan_note,
    is_document_modernization_request,
)
from app.chat.models import Message, MessageRole, Session, SessionResult, SessionState
from app.chat.repository import InMemoryChatRepository
from app.chat.result_metadata import build_session_result_metadata
from app.security import require_api_key
from app.versioning import get_api_version, get_core_version

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm import get_embedding_client
from aijurisdictionagents.schemas import Document as CoreDocument
from aijurisdictionagents.schemas import Message as CoreMessage
from services.document_processor.runtime import (
    cosine_similarity,
    lexical_overlap_score,
    parse_embedding_vector,
)

router = APIRouter(prefix="/v1/chat", tags=["chat"], dependencies=[Depends(require_api_key)])
_repository = InMemoryChatRepository()
_FINISH_RESPONSES = {"finish", "no", "nope", "done", "exit", "quit", "stop"}
_API_VERSION = get_api_version()
_CORE_VERSION = get_core_version()
_LOGGER = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOGO_SVG_PRIMARY = _REPO_ROOT / "corporate-web" / "assets" / "ai-log.svg"
_LOGO_SVG_FALLBACK = _REPO_ROOT / "corporate-web" / "assets" / "aj-logo.svg"
_WINDOWS_FONT_DIR = Path("C:/Windows/Fonts")
_LINUX_DEJAVU_FONT_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
)
_REGISTERED_PDF_FONT_FAMILIES: set[str] = set()


@dataclass(frozen=True)
class _DocumentExportAsset:
    filename: str
    title: str
    lines: list[str]


class CreateSessionRequest(BaseModel):
    user_id: Optional[UUID] = None
    case_id: str | None = None
    country: str = "SK"
    language: str | None = None
    discussion_type: Literal["advice", "court"] = "advice"


class CreateMessageRequest(BaseModel):
    session_id: UUID
    role: MessageRole
    content: str


class ReplyRequest(BaseModel):
    content: str


class InputDocument(BaseModel):
    doc_id: str = Field(default="doc")
    path: str
    content: str


def _get_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


def _persist_case_message_if_needed(*, session: Session, role: str, content: str, agent_name: str | None = None) -> None:
    case_id = session.case_id
    if case_id is None or not case_id.strip():
        return
    store = _get_store()
    store.add_case_message(case_id=case_id, role=role, content=content, agent_name=agent_name)


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
        content = message.content.strip()
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
        add_session_history_document(
            case_id=case_id,
            session_id=str(session_id),
            content=transcript,
            uploaded_by_user_id=str(session.user_id) if session.user_id else None,
        )


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
        if document.kind not in {'uploaded', 'session_history'}:
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
        return _limit_chunks_per_document(
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
        lines.append('Processed documents available for search: ' + ', '.join(processed_names) + '.')
    if unprocessed_names:
        lines.append('Still processing: ' + ', '.join(unprocessed_names) + '.')
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
    return {
        "id": str(visible_message.id),
        "session_id": str(visible_message.session_id),
        "role": visible_message.role.value,
        "agent_name": visible_message.agent_name,
        "content": visible_message.content,
        "created_at": visible_message.created_at.isoformat(),
    }


def _assistant_requests_user_reply(content: str) -> bool:
    return "?" in _user_visible_text(content)


def _persist_direct_assistant_message(
    *,
    session_id: UUID,
    session: Session,
    content: str,
    agent_name: str,
) -> Message:
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


def _run_direct_lawyer_turn(
    *,
    session_id: UUID,
    session: Session,
    content: str,
    supplemental_documents: list[CoreDocument] | None = None,
    processing_event_callback: Callable[[dict[str, object]], None] | None = None,
    user_message_callback: Callable[[Message], None] | None = None,
) -> tuple[Message, Message, str, list[dict[str, object]]]:
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

    from aijurisdictionagents.agents import create_lawyer_agent
    from aijurisdictionagents.llm import get_llm_client

    llm = get_llm_client()
    lawyer = create_lawyer_agent(llm, session.country)

    history = _repository.list_messages(session_id)
    prior_messages = history[:-1]
    conversation = [
        CoreMessage(
            role=msg.role.value,
            content=msg.content,
            agent_name=msg.agent_name or ("User" if msg.role == MessageRole.USER else "Assistant"),
        )
        for msg in history
    ]

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
    if _user_requested_document_generation(content=content, previous_messages=prior_messages):
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
            "- Include CASE_UPDATE_JSON after the user-facing content."
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
    if preparation.direct_reply is not None:
        normalized_direct_reply = _enforce_single_question_turn(preparation.direct_reply)
        persisted_lawyer = _persist_direct_assistant_message(
            session_id=session_id,
            session=session,
            content=normalized_direct_reply,
            agent_name="LawyerSlovakia",
        )
        return (
            persisted_user,
            persisted_lawyer,
            _user_visible_text(normalized_direct_reply),
            preparation.processing_events,
        )
    if preparation.prompt_note:
        prompt_override = f"{prompt_override}\n\n{preparation.prompt_note}"
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
    all_documents.extend(case_documents)
    lawyer_message = lawyer.respond(
        conversation=conversation,
        documents=all_documents,
        sources=[],
        system_prompt_override=prompt_override,
    )
    normalized_lawyer_content = _enforce_single_question_turn(
        _prepend_document_status_note(
            reply=lawyer_message.content,
            processed_names=processed_names,
            unprocessed_names=unprocessed_names,
        )
    )
    visible_lawyer_content = _user_visible_text(normalized_lawyer_content)
    persisted_lawyer = _persist_direct_assistant_message(
        session_id=session_id,
        session=session,
        content=normalized_lawyer_content,
        agent_name=lawyer_message.agent_name,
    )
    return persisted_user, persisted_lawyer, visible_lawyer_content, preparation.processing_events


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


class StartSessionStreamRequest(BaseModel):
    instruction: str
    documents: List[InputDocument] = Field(default_factory=list)
    question_timeout_seconds: float = 300
    max_discussion_minutes: float = 15
    communication_minutes: float | None = None
    user_simulation_mode: Literal["ReadUser", "AIUserSimulatorAgent"] = "ReadUser"
    user_replies: List[str] = Field(default_factory=list)


@router.post("/sessions", response_model=Session)
def create_session(payload: CreateSessionRequest) -> Session:
    session = Session(
        user_id=payload.user_id,
        case_id=payload.case_id,
        country=payload.country,
        language=payload.language,
        discussion_type=payload.discussion_type,
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

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Reply content is required")

    _persisted_user, persisted_lawyer, visible_lawyer_content, _processing_events = _run_direct_lawyer_turn(
        session_id=session_id,
        session=session,
        content=content,
    )
    _persist_session_history_document_if_needed(session=session, session_id=session_id)
    _repository.set_result(
        session_id,
        _build_direct_reply_result(
            session_id=session_id,
            session=session,
            messages=_repository.list_messages(session_id),
            lawyer_message=visible_lawyer_content,
        ),
    )

    return _message_for_user(persisted_lawyer)


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
    if session.state == SessionState.COMPLETED:
        raise HTTPException(status_code=409, detail="Session already completed")
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
    answered_agent_questions = 0
    followup_prompts_seen = 0
    pdf_request_sent = False
    thank_you_sent = False

    simulator = None
    simulator_documents = [CoreDocument(doc_id=d.doc_id, path=d.path, content=d.content) for d in payload.documents]
    if payload.user_simulation_mode == "AIUserSimulatorAgent":
        from aijurisdictionagents.agents import AIUserSimulatorAgent
        from aijurisdictionagents.llm import get_llm_client

        simulator = AIUserSimulatorAgent(get_llm_client(), language=session.language)

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
        nonlocal assistant_messages_seen
        normalized_role = core_message_role(core_message.role)
        if normalized_role == "assistant":
            assistant_messages_seen += 1
        core_conversation.append(core_message)
        persisted = _repository.add_message(
            Message(
                session_id=session_id,
                role=MessageRole(normalized_role),
                content=core_message.content,
                agent_name=core_message.agent_name,
            )
        )
        _persist_case_message_if_needed(
            session=session,
            role=normalized_role,
            content=core_message.content,
            agent_name=core_message.agent_name,
        )
        event_queue.put(
            (
                "message",
                {
                    "id": str(persisted.id),
                    "session_id": str(session_id),
                    "role": persisted.role.value,
                    "agent_name": persisted.agent_name,
                    "content": persisted.content,
                    "created_at": persisted.created_at.isoformat(),
                },
            )
        )
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
            result = run_orchestration(
                session=session,
                instruction=payload.instruction,
                documents=docs,
                question_timeout_seconds=payload.question_timeout_seconds,
                max_discussion_minutes=payload.max_discussion_minutes,
                user_response_provider=user_response_provider,
                message_callback=message_callback,
            )
            persisted_messages = _repository.list_messages(session_id)
            metadata = build_session_result_metadata(
                session=session,
                messages=persisted_messages,
                final_recommendation=result.final_recommendation,
                base_metadata={"message_count": len(result.messages), "mode": "discussion_stream"},
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
            event_queue.put(("error", {"message": str(exc)}))
        finally:
            event_queue.put(None)

    Thread(target=worker, daemon=True).start()

    def stream() -> Generator[str, None, None]:
        while True:
            item = event_queue.get()
            if item is None:
                break
            event_name, body = item
            yield f"event: {event_name}\ndata: {json.dumps(body)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


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
            _persisted_user, persisted_lawyer, visible_lawyer_content, _processing_events = _run_direct_lawyer_turn(
                session_id=session_id,
                session=session,
                content=payload.instruction,
                supplemental_documents=inline_documents,
                processing_event_callback=processing_event_callback,
                user_message_callback=user_message_callback,
            )
            current_messages = _repository.list_messages(session_id)
            if not current_messages:
                current_messages = [message for message in (_persisted_user, persisted_lawyer) if message is not None]
            for document_event in _document_generation_progress_events(
                session=session,
                messages=current_messages,
                lawyer_message=visible_lawyer_content,
            ):
                event_queue.put(("processing", document_event))
            event_queue.put(("message", _message_payload(persisted_lawyer)))

            if _assistant_requests_user_reply(visible_lawyer_content):
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
                session_result = _build_direct_reply_result(
                    session_id=session_id,
                    session=session,
                    messages=current_messages,
                    lawyer_message=visible_lawyer_content,
                )
                _persist_session_history_document_if_needed(session=session, session_id=session_id)
                _repository.set_result(session_id, session_result)
                event_queue.put(("result", session_result.model_dump(mode="json")))
                event_queue.put(("done", {"session_id": str(session_id), "status": "completed"}))
        except Exception as exc:  # noqa: BLE001
            _repository.mark_failed(session_id)
            event_queue.put(("error", {"message": str(exc)}))
        finally:
            event_queue.put(None)

    Thread(target=worker, daemon=True).start()

    def stream() -> Generator[str, None, None]:
        while True:
            item = event_queue.get()
            if item is None:
                break
            event_name, body = item
            yield f"event: {event_name}\ndata: {json.dumps(body)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def _is_followup_termination_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    return "finish" in lowered and ("type" in lowered or "nap" in lowered)


def _is_pdf_format_question(prompt: str) -> bool:
    lowered = prompt.lower()
    return "pdf" in lowered and "?" in prompt


def _user_requested_document_generation(*, content: str, previous_messages: list[Message]) -> bool:
    normalized = " ".join(content.lower().split())
    if _is_explicit_document_request(normalized):
        return True
    if not _is_affirmative_reply(normalized):
        return False
    for message in reversed(previous_messages):
        if message.role != MessageRole.ASSISTANT:
            continue
        if _assistant_requests_document_confirmation(message.content):
            return True
        if message.role == MessageRole.ASSISTANT:
            break
    return False


def _is_explicit_document_request(normalized: str) -> bool:
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
        "predÅ¾alob",
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
    affirmatives = (
        "ano",
        "Ã¡no",
        "yes",
        "sure",
        "ok",
        "okay",
        "prosim",
        "please",
        "chcem",
        "potvrdzujem",
    )
    return any(token in normalized for token in affirmatives)


def _assistant_requests_document_confirmation(content: str) -> bool:
    lowered = content.lower()
    document_markers = ("pdf", "document", "draft", "template", "zmluv", "dokument")
    confirmation_markers = (
        "do you want",
        "would you like",
        "chcete",
        "mÃ¡m pripraviÅ¥",
        "mam pripravit",
        "pripraviÅ¥",
        "pripravit",
    )
    return (
        any(marker in lowered for marker in document_markers)
        and "?" in content
        and any(marker in lowered for marker in confirmation_markers)
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
        for marker in ("pripravil som", "pripravila som", "prepared", "ready", "hotove", "hotovÃ½")
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
        for content in discussion_messages:
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
    document_prefixes = (
        "zmluva",
        "zapisnica",
        "rozhodnutie",
        "aktualizacia",
        "aktualizovane",
        "podanie na orsr",
        "navrh rozhodnutia",
        "share transfer agreement",
        "sole shareholder decision",
        "updated articles",
        "registry filing",
        "founding deed",
    )
    document_phrases = (
        "spolocenska zmluva",
        "spolocenskej zmluvy",
        "zakladatelska listina",
        "zakladatelskej listiny",
        "podanie na orsr",
        "obchodneho registra",
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
        ("pisnica", "rozhodnut"),
        ("aktualiz", "zmluv"),
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
    if not any(marker in value for marker in ("Ã", "Â", "Ä", "Å", "â")):
        return value
    for source_encoding in ("latin-1", "cp1252"):
        try:
            repaired = value.encode(source_encoding, errors="ignore").decode("utf-8", errors="ignore").strip()
        except UnicodeError:
            continue
        if repaired:
            return repaired
    return value


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
            "Aktualizovane uplne znenie spolocenskej zmluvy / zakladatelskej listiny",
        ]
    return [
        "Share transfer agreement",
        "Sole shareholder decision / meeting minutes",
        "Updated articles / founding deed",
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


def _current_turn_confirms_document_generation(
    content: str,
    previous_messages: list[Message],
) -> bool:
    normalized = " ".join(content.lower().split())
    if not any(
        message.role == MessageRole.ASSISTANT and _assistant_requests_document_confirmation(message.content)
        for message in previous_messages
    ):
        return False
    return _is_affirmative_reply(normalized) or _is_explicit_document_request(normalized)


def _build_direct_reply_result(
    *,
    session_id: UUID,
    session: Session,
    messages: list[Message],
    lawyer_message: str,
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
        },
    )
    return SessionResult(
        final_recommendation=visible_text or f"Direct lawyer reply for session {session_id}.",
        judge_rationale=rationale,
        citations=_merge_session_citations(generic_citations=[], metadata=metadata),
        metadata=metadata,
    )


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
        if not any(
            prior.role == MessageRole.ASSISTANT and _assistant_requests_document_confirmation(prior.content)
            for prior in previous_messages
        ):
            continue
        normalized = " ".join(message.content.lower().split())
        if _is_affirmative_reply(normalized) or _is_explicit_document_request(normalized):
            return True
    return False


def _document_export_ready(messages: list[Message]) -> bool:
    if not _document_generation_confirmed(messages):
        return False
    assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]
    if not assistant_messages:
        return False
    last_assistant = assistant_messages[-1]
    if _assistant_requests_document_confirmation(last_assistant.content):
        return False
    if any(_contains_case_update_json(message.content) for message in assistant_messages):
        return True
    visible_text = _user_visible_text(last_assistant.content).lower()
    ready_markers = (
        "pripravil som",
        "pripravila som",
        "prepared the final",
        "prepared the draft",
        "draft is ready",
        "navrh zmluvy",
        "predzalobna vyzva",
        "predÅ¾alobnÃ¡ vÃ½zva",
        "legal summary",
        "pravne zhrnutie",
    )
    if any(marker in visible_text for marker in ready_markers):
        return True
    return "?" not in last_assistant.content and bool(visible_text.strip())


def _contains_case_update_json(content: str) -> bool:
    return "case_update_json" in content.lower()


def _user_visible_text(content: str) -> str:
    bounds = _case_update_payload_bounds(content)
    if bounds is None:
        return _strip_user_visible_technical_trailer(content)
    start_index, _end_index = bounds
    return _strip_user_visible_technical_trailer(content[:start_index])


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
    )
    technical_fragments = (
        "json pre uchovanie prÃ­padu",
        "json pre uchovanie pripadu",
        "json for case persistence",
        "json for storing the case",
        "machine payload",
        "technical payload",
    )
    return normalized_line.startswith(technical_prefixes) or any(
        fragment in normalized_line for fragment in technical_fragments
    )


def _looks_like_fake_download_intro(normalized_line: str) -> bool:
    if not normalized_line:
        return False
    markers = (
        "mÃ´Å¾ete si ich stiahnuÅ¥ pomocou nasledujÃºcich odkazov",
        "mozete si ich stiahnut pomocou nasledujucich odkazov",
        "mÃ´Å¾ete si ich stiahnuÅ¥ na nasledujÃºcich odkazoch",
        "mozete si ich stiahnut na nasledujucich odkazoch",
        "nasledujÃºce odkazy na stiahnutie",
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
            r"^\d+\.\s*\[[^\]]+\]\(\s*documents/[^)]+\)$",
            stripped,
            flags=re.IGNORECASE,
        )
    )


def _message_for_user(message: Message) -> Message:
    if message.role != MessageRole.ASSISTANT:
        return message
    visible_content = _user_visible_text(message.content)
    if visible_content == message.content:
        return message
    return message.model_copy(update={"content": visible_content})


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


def _enforce_single_question_turn(content: str) -> str:
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
    result = _repository.get_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for session {session_id} not found")
    return result


@router.get("/sessions/{session_id}/export")
def export_session_result(
    session_id: UUID,
    format: Literal["json", "pdf"] = Query("json"),
    kind: Literal["summary", "document"] = Query("summary"),
) -> Response:
    result = _repository.get_result(session_id)
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

    if kind == "document":
        document_assets = _build_document_export_assets(
            session_id=session_id,
            messages=messages,
            result=result,
            country=session.country,
            language=session.language,
        )
        if len(document_assets) > 1:
            archive_name = _build_document_archive_filename(session_id=session_id)
            archive_content = _build_document_export_archive(
                assets=document_assets,
                country=session.country,
                language=session.language,
                generated_at=generated_at,
                footer_line=footer_line,
            )
            return Response(
                content=archive_content,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
            )
        asset = document_assets[0]
        title = asset.title
        lines = asset.lines
        filename = asset.filename
    else:
        title, lines = _build_summary_export_content(
            session_id=session_id,
            result=result,
            messages=messages,
            country=session.country,
            language=session.language,
        )
        filename = _build_pdf_filename(session_id=session_id, kind="summary")

    pdf_content = _build_simple_pdf(
        title=title,
        lines=lines,
        country=session.country,
        language=session.language,
        header_line=(f"AI Jurisdicta Solution | Generated: {generated_at}" if kind == "document" else None),
        footer_line=(footer_line if kind == "document" else None),
        draw_logo_mark=(kind == "document"),
        include_title_block=(kind != "document"),
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_simple_pdf(
    title: str,
    lines: List[str],
    *,
    country: str,
    language: str | None,
    header_line: str | None = None,
    footer_line: str | None = None,
    draw_logo_mark: bool = False,
    include_title_block: bool = True,
) -> bytes:
    regular_font, bold_font = _resolve_pdf_fonts(country=country, language=language)
    page_width, page_height = cast(tuple[float, float], A4)
    margin_left = 50.0
    margin_top = 52.0
    margin_bottom = 42.0
    body_font_size = 11.0
    body_line_height = 14.0
    title_font_size = 14.0
    footer_font_size = 9.0

    header_lines: list[str] = []
    if header_line:
        header_lines.append(header_line)
        header_lines.append("")

    title_block: list[str] = [title, "----------------"] if include_title_block else []
    prepared_lines = header_lines + title_block + _wrap_pdf_lines(lines)
    if not prepared_lines:
        prepared_lines = [title]

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)

    def start_page() -> float:
        if draw_logo_mark:
            pdf.setFont(bold_font, 10)
            pdf.drawRightString(page_width - margin_left, page_height - 28, "AI Jurisdicta")
        return page_height - margin_top

    def draw_footer() -> None:
        if footer_line:
            pdf.setFont(regular_font, footer_font_size)
            pdf.drawString(margin_left, margin_bottom - 8, footer_line)

    y = start_page()
    for index, line in enumerate(prepared_lines):
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
        pdf.setFont(regular_font, body_font_size)
        pdf.drawString(margin_left, y, line)
        y -= body_line_height

    draw_footer()
    pdf.save()
    return buffer.getvalue()


def _wrap_pdf_lines(lines: List[str], width: int = 90) -> List[str]:
    wrapped: List[str] = []
    for line in lines:
        text = line.strip()
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
) -> bytes:
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for asset in assets:
            pdf_content = _build_simple_pdf(
                title=asset.title,
                lines=asset.lines,
                country=country,
                language=language,
                header_line=f"AI Jurisdicta Solution | Generated: {generated_at}",
                footer_line=footer_line,
                draw_logo_mark=True,
                include_title_block=True,
            )
            archive.writestr(asset.filename, pdf_content)
    return archive_buffer.getvalue()


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
    for citation in _law_citation_session_citations(metadata):
        if citation not in merged:
            merged.append(citation)
    return merged


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
                detail += f", ÃºÄinnÃ¡ od {effective_from}"
        else:
            detail = f"- {identifier}"
            if title:
                detail += f": {title}"
            if version_token:
                detail += f", version {version_token}"
            if effective_from:
                detail += f", effective from {effective_from}"
        lines.append(detail)
    return lines


def _build_document_export_assets(
    *,
    session_id: UUID,
    messages: List[Message],
    result: SessionResult | None,
    country: str,
    language: str | None,
) -> list[_DocumentExportAsset]:
    title, lines = _build_document_export_content(
        session_id=session_id,
        messages=messages,
        result=result,
        country=country,
        language=language,
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
    document_entries = _case_update_document_entries(case_update)
    if len(document_entries) <= 1:
        document_entries = _fallback_document_entries_for_export(
            messages=messages,
            result=result,
            document_kind=document_kind,
        )
    if len(document_entries) <= 1:
        entry = document_entries[0] if document_entries else None
        return [
            _DocumentExportAsset(
                filename=_document_asset_filename(
                    entry=entry,
                    fallback_filename=_build_pdf_filename(session_id=session_id, kind="document"),
                ),
                title=title,
                lines=lines,
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
    titles = _extract_document_titles_from_text(_user_visible_text(source))
    if len(titles) <= 1:
        return []
    entries: list[dict[str, Any]] = []
    for index, title in enumerate(titles, start=1):
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
            }
        )
    return entries


def _fallback_document_entry_type(*, title: str, document_kind: str) -> str:
    lowered = _canonicalize_document_text(title)
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
    if document_kind == "share_transfer" or entry_type in {"contract", "minutes", "articles", "registry_filing"}:
        known_filenames = {
            "contract": "Zmluva_o_prevode_podielu.pdf",
            "minutes": "Zapisnica_z_rozhodnutia_spolocnikov.pdf",
            "articles": "Aktualizovana_spolocenska_zmluva.pdf",
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
    case_update = _extract_case_update(source)
    if case_update is None:
        for content in discussion_messages:
            case_update = _extract_case_update(content)
            if case_update is not None:
                break
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
) -> tuple[str, List[str]]:
    context_lines, _case_update, document_kind, facts, law_citation_lines = (
        _prepare_document_export_context(
            messages=messages,
            result=result,
            language=language,
        )
    )
    if country.strip().upper() == "SK" and document_kind == "share_transfer":
        from app.chat.country_services.slovakia import build_slovak_share_transfer_export_lines

        title = f"GenerovanÃƒÂ½ Dokument {session_id}"
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
        title = f"GenerovanÃ½ Dokument {session_id}"
        if document_kind == "rental_agreement":
            lines = _build_standard_slovak_agreement_lines(facts)
            return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        if document_kind == "easement_demand":
            lines = _build_slovak_easement_demand_lines(facts)
            return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        if document_kind == "share_transfer":
            lines = _build_slovak_share_transfer_lines(facts)
            return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
        lines = _build_generic_slovak_case_document_lines(facts)
        return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)

    title = f"Generated Document {session_id}"
    if document_kind == "rental_agreement":
        lines = _build_standard_english_agreement_lines(facts)
        return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
    if document_kind == "easement_demand":
        lines = _build_english_easement_demand_lines(facts)
        return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
    if document_kind == "share_transfer":
        lines = _build_english_share_transfer_lines(facts)
        return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)
    lines = _build_generic_english_case_document_lines(facts)
    return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)


def _append_document_law_citations(
    *,
    lines: List[str],
    citations: list[str],
    language: str | None,
) -> List[str]:
    if not citations:
        return lines
    prefers_slovak = (language or "").strip().lower().startswith("sk")
    heading = "PrÃ¡vne citÃ¡cie" if prefers_slovak else "Legal citations"
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
                lines=lines,
            )
        )
    return assets


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
    raw_name = str(entry.get("filename") or entry.get("path") or "").strip()
    if raw_name:
        stem = Path(raw_name).stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return stem
    prefers_slovak = (language or "").strip().lower().startswith("sk")
    if prefers_slovak:
        return f"Dokument {fallback_index}"
    return f"Document {fallback_index}"


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
            title = "Aktualizovane uplne znenie spolocenskej zmluvy / zakladatelskej listiny"
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
            title = "Updated articles / founding deed"
            lines = _build_english_share_transfer_articles_lines(facts)
        elif asset_kind == "registry_filing":
            title = "Registry filing package"
            lines = _build_english_share_transfer_registry_filing_lines(facts)
        else:
            title = "Share transfer agreement"
            lines = _build_english_share_transfer_agreement_lines(facts)
    return title, _append_document_law_citations(lines=lines, citations=law_citation_lines, language=language)


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
    text = " ".join(source_lines)
    case = case_update.get("case", {}) if isinstance(case_update, dict) else {}
    next_discussion = case.get("next_discussion", {}) if isinstance(case, dict) else {}

    def _capture(pattern: str, default: str, flags: int = re.IGNORECASE) -> str:
        match = re.search(pattern, text, flags)
        if not match:
            return default
        return " ".join(match.group(1).strip().split())

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
    prenajimatel = _capture(r"prenajimatel\s*([^,.;]+)", "Prenajimatel [doplnit udaje]")
    najomca = _capture(r"najomca\s*([^,.;]+)", "Najomca [doplnit udaje]")
    if parties_line and "doplnit" in prenajimatel.lower():
        prenajimatel = parties_line
    predmet = _capture(r"predmet najmu:\s*(.+?)(?:\s+\d+\)|$)", "Byt [adresa a identifikacia]")
    doba = _capture(r"doba najmu:\s*(.+?)(?:\s+\d+\)|$)", "Na dobu urcitu 1 rok")
    najomne = _capture(r"najomne:\s*(.+?)(?:\s+\d+\)|$)", "850 EUR mesacne, splatne do 5. dna v mesiaci")
    advance = _capture(r"platba vopred:\s*(.+?)(?:\s+\d+\)|$)", "2 mesacne najomne vopred")
    deposit = _capture(r"kaucia:\s*(.+?)(?:\s+\d+\)|$)", "1 mesacne najomne")
    notice = _capture(r"(vypovedna lehota[^.]+)", "Vypovedna lehota 1 mesiac, dorucenie pisomne aj emailom")

    client_name = _case_text(("case", "parties", "client", "name"), "Klient")
    opponent_name = _case_text(("case", "parties", "opponent", "name"), "Protistrana")
    topic = _case_text(("case", "matter", "topic"), "pravny_problem")
    facts_summary = _case_text(("case", "matter", "facts_summary"), "PrÃ¡vny problÃ©m podÄ¾a diskusie.")
    client_goal = _case_text(("case", "matter", "client_goal"), "DosiahnuÅ¥ primeranÃ© prÃ¡vne rieÅ¡enie.")
    scheduled_for = _case_text(("case", "next_discussion", "scheduled_for"), "")
    agenda_items = next_discussion.get("agenda", []) if isinstance(next_discussion, dict) else []
    agenda = ", ".join(str(item).strip() for item in agenda_items if str(item).strip())
    company_name = _capture(
        r"(?:firma|fima|spoloÄnosÅ¥|spolocnost)\s+([^,.;\n]+?(?:s\.r\.o\.|a\.s\.|s\. r\. o\.))",
        "SpoloÄnosÅ¥ [doplnit obchodnÃ© meno]",
    )
    company_seat = _capture(
        r"(?:s\.r\.o\.|a\.s\.|s\. r\. o\.)\s*,\s*([^.;\n]+)",
        "SÃ­dlo spoloÄnosti [doplnit]",
    )
    company_identifier = _capture(r"iÄo\s*[:=]?\s*([0-9]{6,10})", "[doplnit IÄŒO]")
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
        "client_name": client_name,
        "opponent_name": opponent_name,
        "topic": topic,
        "facts_summary": facts_summary,
        "client_goal": client_goal,
        "scheduled_for": scheduled_for,
        "agenda": agenda or "DoplniÅ¥ ÄalÅ¡Ã­ postup podÄ¾a vÃ½voja komunikÃ¡cie.",
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


def _build_standard_slovak_agreement_lines(facts: dict[str, str]) -> List[str]:
    return [
        "NÃ¡jomnÃ¡ zmluva",
        "uzatvorenÃ¡ podÄ¾a paragrafu 663 a nasl. ObÄianskeho zÃ¡konnÃ­ka",
        "",
        "ÄŒl. I - ZmluvnÃ© strany",
        f"PrenajÃ­mateÄ¾: {facts['prenajimatel']}",
        f"NÃ¡jomca: {facts['najomca']}",
        "",
        "ÄŒl. II - Predmet nÃ¡jmu",
        _with_period(facts["predmet"]),
        "",
        "ÄŒl. III - Doba nÃ¡jmu",
        _with_period(facts["doba"]),
        "",
        "ÄŒl. IV - NÃ¡jomnÃ© a platobnÃ© podmienky",
        f"NÃ¡jomnÃ©: {_with_period(facts['najomne'])}",
        f"Platba vopred: {_with_period(facts['advance'])}",
        f"Kaucia: {_with_period(facts['deposit'])}",
        "",
        "ÄŒl. V - PrÃ¡va a povinnosti zmluvnÃ½ch strÃ¡n",
        "NÃ¡jomca je povinnÃ½ uÅ¾Ã­vaÅ¥ predmet nÃ¡jmu riadne, Å¡etrne a v sÃºlade so zmluvou.",
        "PrenajÃ­mateÄ¾ je povinnÃ½ odovzdaÅ¥ predmet nÃ¡jmu spÃ´sobilÃ½ na dohodnutÃ© uÅ¾Ã­vanie.",
        "",
        "ÄŒl. VI - SkonÄenie nÃ¡jmu",
        _with_period(facts["notice"]),
        "",
        "ÄŒl. VII - ZÃ¡vereÄnÃ© ustanovenia",
        "Zmluva nadobÃºda platnosÅ¥ dÅˆom podpisu oboma zmluvnÃ½mi stranami.",
        "Zmeny zmluvy je moÅ¾nÃ© vykonaÅ¥ len pÃ­somnÃ½m dodatkom.",
        "",
        "V [mesto], dna [datum]",
        "",
        "Podpis prenajÃ­mateÄ¾a: ____________________________",
        "Podpis nÃ¡jomcu: _________________________________",
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
        "3. Aktualizovane uplne znenie spolocenskej zmluvy alebo zakladatelskej listiny.",
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
        "3. Updated articles / founding deed reflecting the new ownership structure.",
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
        "3. Updated articles or founding deed.",
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
        "PrÃ¡vne zhrnutie a nÃ¡vrh ÄalÅ¡ieho postupu",
        "",
        f"Klient: {facts['client_name']}",
        f"Protistrana: {facts['opponent_name']}",
        f"TÃ©ma: {facts['topic']}",
        "",
        "SkutkovÃ½ stav:",
        _with_period(facts["facts_summary"]),
        "",
        "CieÄ¾ klienta:",
        _with_period(facts["client_goal"]),
        "",
        "OdporÃºÄanÃ½ postup:",
        "1. ZabezpeÄiÅ¥ a usporiadaÅ¥ vÅ¡etky relevantnÃ© listiny a komunikÃ¡ciu.",
        "2. PÃ­somne vyzvaÅ¥ protistranu na dobrovoÄ¾nÃ© rieÅ¡enie.",
        "3. VyhodnotiÅ¥ potrebu predÅ¾alobnej vÃ½zvy alebo nÃ¡vrhu na sÃºdnu ochranu.",
        "",
        "ÄŽalÅ¡ia konzultÃ¡cia:",
        _with_period(facts["agenda"]),
        "",
        "Podpis klienta / zÃ¡stupcu: ____________________________",
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
    return None


def _extract_json_object(content: str, start_index: int) -> str | None:
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
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start_index : index + 1]
    return None


def _detect_document_kind(
    source_lines: List[str],
    case_update: dict[str, Any] | None,
) -> Literal["rental_agreement", "easement_demand", "share_transfer", "generic_case_document"]:
    combined = " ".join(source_lines).lower()
    case = case_update.get("case", {}) if isinstance(case_update, dict) else {}
    matter = case.get("matter", {}) if isinstance(case, dict) else {}
    topic = str(matter.get("topic", "")).lower()
    facts_summary = str(matter.get("facts_summary", "")).lower()
    client_goal = str(matter.get("client_goal", "")).lower()
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
