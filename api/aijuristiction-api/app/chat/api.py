from __future__ import annotations

import json
import re
import time
import textwrap
from collections import deque
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.chat.core_runtime import core_message_role, run_orchestration
from app.chat.models import Message, MessageRole, Session, SessionResult, SessionState
from app.chat.repository import InMemoryChatRepository
from app.security import require_api_key
from app.versioning import get_api_version, get_core_version

from aijurisdictionagents.schemas import Document as CoreDocument
from aijurisdictionagents.schemas import Message as CoreMessage

router = APIRouter(prefix="/v1/chat", tags=["chat"], dependencies=[Depends(require_api_key)])
_repository = InMemoryChatRepository()
_FINISH_RESPONSES = {"finish", "no", "nope", "done", "exit", "quit", "stop"}
_API_VERSION = get_api_version()
_CORE_VERSION = get_core_version()
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOGO_SVG_PRIMARY = _REPO_ROOT / "corporate-web" / "assets" / "ai-log.svg"
_LOGO_SVG_FALLBACK = _REPO_ROOT / "corporate-web" / "assets" / "aj-logo.svg"


class CreateSessionRequest(BaseModel):
    user_id: Optional[UUID] = None
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
        country=payload.country,
        language=payload.language,
        discussion_type=payload.discussion_type,
    )
    return _repository.create_session(session)


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

    _repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.USER,
            content=content,
            agent_name="User",
        )
    )

    from aijurisdictionagents.agents import create_lawyer_agent
    from aijurisdictionagents.llm import get_llm_client

    llm = get_llm_client()
    lawyer = create_lawyer_agent(llm, session.country)

    history = _repository.list_messages(session_id)
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

    lawyer_message = lawyer.respond(
        conversation=conversation,
        documents=[],
        sources=[],
        system_prompt_override=prompt_override,
    )
    persisted_lawyer = _repository.add_message(
        Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=lawyer_message.content,
            agent_name=lawyer_message.agent_name,
        )
    )

    return persisted_lawyer


@router.get("/sessions/{session_id}/messages", response_model=List[Message])
def list_session_messages(session_id: UUID) -> List[Message]:
    if _repository.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return _repository.list_messages(session_id)


@router.post("/sessions/{session_id}/stream")
def stream_session(session_id: UUID, payload: StartSessionStreamRequest) -> StreamingResponse:
    session = _repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.state == SessionState.COMPLETED:
        raise HTTPException(status_code=409, detail="Session already completed")

    event_queue: Queue[tuple[str, dict[str, object]] | None] = Queue()
    replies = deque(payload.user_replies)
    communication_minutes = payload.communication_minutes or payload.max_discussion_minutes
    simulation_deadline = time.monotonic() + max(communication_minutes, 0) * 60
    core_conversation: list[CoreMessage] = []
    question_attempts: dict[str, int] = {}
    simulation_turn = 0
    last_simulator_reply = ""
    assistant_messages_seen = 0
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
                last_simulator_reply = "finish"
                return "finish"

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
                    last_simulator_reply = "finish"
                    return "finish"
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
        if core_message_role(core_message.role) == "assistant":
            assistant_messages_seen += 1
        core_conversation.append(core_message)
        persisted = _repository.add_message(
            Message(
                session_id=session_id,
                role=MessageRole(core_message_role(core_message.role)),
                content=core_message.content,
                agent_name=core_message.agent_name,
            )
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

    def worker() -> None:
        try:
            docs = [
                CoreDocument(doc_id=d.doc_id, path=d.path, content=d.content)
                for d in payload.documents
            ]
            result = run_orchestration(
                session=session,
                instruction=payload.instruction,
                documents=docs,
                question_timeout_seconds=payload.question_timeout_seconds,
                max_discussion_minutes=payload.max_discussion_minutes,
                user_response_provider=user_response_provider,
                message_callback=message_callback,
            )
            session_result = SessionResult(
                final_recommendation=result.final_recommendation,
                judge_rationale=result.judge_rationale,
                citations=[{"filename": c.filename, "snippet": c.snippet} for c in result.citations],
                metadata={"message_count": len(result.messages)},
            )
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


def _is_followup_termination_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    return "finish" in lowered and ("type" in lowered or "nap" in lowered)


def _is_pdf_format_question(prompt: str) -> bool:
    lowered = prompt.lower()
    return "pdf" in lowered and "?" in prompt


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

    if kind == "document":
        title, lines = _build_document_export_content(
            session_id=session_id,
            messages=messages,
            country=session.country,
            language=session.language,
        )
        filename = _build_pdf_filename(session_id=session_id, kind="document")
    else:
        title, lines = _build_summary_export_content(
            session_id=session_id,
            result=result,
            messages=messages,
            country=session.country,
            language=session.language,
        )
        filename = _build_pdf_filename(session_id=session_id, kind="summary")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    footer_line = f"AIJ | API {_API_VERSION} | Core {_CORE_VERSION}"
    pdf_content = _build_simple_pdf(
        title=title,
        lines=lines,
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
    header_line: str | None = None,
    footer_line: str | None = None,
    draw_logo_mark: bool = False,
    include_title_block: bool = True,
) -> bytes:
    header_lines: list[str] = []
    if header_line:
        header_lines.append(header_line)
    if header_lines:
        header_lines.append("")

    title_block: list[str] = [title, "----------------"] if include_title_block else []
    prepared_lines = header_lines + title_block + _wrap_pdf_lines(lines)
    lines_per_page = 48
    pages: list[list[str]] = []
    for index in range(0, len(prepared_lines), lines_per_page):
        pages.append(prepared_lines[index : index + lines_per_page])
    if not pages:
        pages = [[title, "----------------"]]

    page_count = len(pages)
    font_id = 3
    first_page_id = 4
    page_ids = [first_page_id + i * 2 for i in range(page_count)]
    content_ids = [page_id + 1 for page_id in page_ids]

    kids_refs = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects: list[bytes] = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        f"2 0 obj << /Type /Pages /Kids [{kids_refs}] /Count {page_count} >> endobj\n".encode("latin-1"),
        b"3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]

    for page_id, content_id, page_lines in zip(page_ids, content_ids, pages):
        objects.append(
            f"{page_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >> endobj\n".encode(
                "latin-1"
            )
        )
        escaped_lines = [_escape_pdf_line(line) for line in page_lines]
        text_ops = ["BT", "/F1 11 Tf", "14 TL", "50 790 Td"]
        for line in escaped_lines:
            text_ops.append(f"({line}) Tj")
            text_ops.append("T*")
        text_ops.append("ET")
        if draw_logo_mark:
            text_ops.extend(_ai_jurisdicta_logo_ops(x=500.0, y=718.0, size=66.0))
        if footer_line:
            escaped_footer = _escape_pdf_line(footer_line)
            text_ops.extend(
                [
                    "BT",
                    "/F1 9 Tf",
                    "50 30 Td",
                    f"({escaped_footer}) Tj",
                    "ET",
                ]
            )
        stream_bytes = " ".join(text_ops).encode("latin-1", errors="replace")
        objects.append(
            f"{content_id} 0 obj << /Length {len(stream_bytes)} >> stream\n".encode("latin-1")
            + stream_bytes
            + b"\nendstream endobj\n"
        )

    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref_pos = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        output.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    output.extend(
        f"trailer << /Root 1 0 R /Size {len(objects)+1} >>\nstartxref\n{xref_pos}\n%%EOF".encode("latin-1")
    )
    return bytes(output)


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
    if (language or "").strip().lower().startswith("sk"):
        return (
            f"Zhrnutie diskusie {session_id}",
            [
                "AI Jurisdiction",
                "Zhrnutie diskusie",
                "",
                f"Session ID: {session_id}",
                f"Krajina: {country}",
                f"Jazyk: {lang_label}",
                f"Vygenerovane: {generated}",
                "",
                f"Finalne odporucanie: {result.final_recommendation}",
                f"Odovodnenie: {result.judge_rationale or 'neposkytnute'}",
                f"Pocet sprav pouzivatela: {user_count}",
                f"Pocet odpovedi asistenta: {assistant_count}",
            ],
        )
    return (
        f"Discussion Summary {session_id}",
        [
            "AI Jurisdiction",
            "Discussion summary",
            "",
            f"Session ID: {session_id}",
            f"Country: {country}",
            f"Language: {lang_label}",
            f"Generated at: {generated}",
            "",
            f"Final recommendation: {result.final_recommendation}",
            f"Rationale: {result.judge_rationale or 'not provided'}",
            f"User messages: {user_count}",
            f"Assistant messages: {assistant_count}",
        ],
    )


def _build_document_export_content(
    *,
    session_id: UUID,
    messages: List[Message],
    country: str,
    language: str | None,
) -> tuple[str, List[str]]:
    lawyer_messages = [
        m.content
        for m in messages
        if m.role == MessageRole.ASSISTANT and (m.agent_name or "").lower().startswith("lawyer")
    ]
    source = _pick_document_message(lawyer_messages)
    source_lines = _normalize_document_lines(source)
    if not source_lines:
        source_lines = ["No lawyer-generated document content found in this session."]
    facts = _extract_document_facts(source_lines)

    if (language or "").strip().lower().startswith("sk"):
        title = f"Generovany Dokument {session_id}"
        lines = _build_standard_slovak_agreement_lines(facts)
        return title, lines

    title = f"Generated Document {session_id}"
    lines = _build_standard_english_agreement_lines(facts)
    return title, lines


def _pick_document_message(candidates: List[str]) -> str:
    if not candidates:
        return ""

    def _score(content: str) -> tuple[int, int]:
        lowered = content.lower()
        score = 0
        if any(token in lowered for token in ("vzor", "zmluv", "template", "draft", "contract", "agreement")):
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


def _extract_document_facts(source_lines: List[str]) -> dict[str, str]:
    text = " ".join(source_lines)

    def _capture(pattern: str, default: str, flags: int = re.IGNORECASE) -> str:
        match = re.search(pattern, text, flags)
        if not match:
            return default
        return " ".join(match.group(1).strip().split())

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

    return {
        "prenajimatel": prenajimatel,
        "najomca": najomca,
        "predmet": predmet,
        "doba": doba,
        "najomne": najomne,
        "advance": advance,
        "deposit": deposit,
        "notice": notice,
    }


def _build_standard_slovak_agreement_lines(facts: dict[str, str]) -> List[str]:
    return [
        "NAJOMNA ZMLUVA",
        "uzatvorena podla paragrafu 663 a nasl. Obcianskeho zakonnika",
        "",
        "Cl. I - Zmluvne strany",
        f"Prenajimatel: {facts['prenajimatel']}",
        f"Najomca: {facts['najomca']}",
        "",
        "Cl. II - Predmet najmu",
        _with_period(facts["predmet"]),
        "",
        "Cl. III - Doba najmu",
        _with_period(facts["doba"]),
        "",
        "Cl. IV - Najomne a platobne podmienky",
        f"Najomne: {_with_period(facts['najomne'])}",
        f"Platba vopred: {_with_period(facts['advance'])}",
        f"Kaucia: {_with_period(facts['deposit'])}",
        "",
        "Cl. V - Prava a povinnosti zmluvnych stran",
        "Najomca je povinny uzivat predmet najmu riadne, setrne a v sulade so zmluvou.",
        "Prenajimatel je povinny odovzdat predmet najmu sposobily na dohodnute uzivanie.",
        "",
        "Cl. VI - Skoncenie najmu",
        _with_period(facts["notice"]),
        "",
        "Cl. VII - Zaverecne ustanovenia",
        "Zmluva nadobuda platnost dnom podpisu oboma zmluvnymi stranami.",
        "Zmeny zmluvy je mozne vykonat len pisomnym dodatkom.",
        "",
        "V [mesto], dna [datum]",
        "",
        "Podpis prenajimatela: ____________________________",
        "Podpis najomcu: _________________________________",
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


def _with_period(value: str) -> str:
    cleaned = value.strip()
    while cleaned.endswith("."):
        cleaned = cleaned[:-1].rstrip()
    return f"{cleaned}."


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
