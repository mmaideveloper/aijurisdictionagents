from __future__ import annotations

from io import BytesIO
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
from app.chat.models import Message, MessageRole, Session, SessionResult, SessionState
from app.chat.repository import InMemoryChatRepository
from app.security import require_api_key
from app.versioning import get_api_version, get_core_version

from aijurisdictionagents.api_db import ApiDatabaseStore
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
_WINDOWS_FONT_DIR = Path("C:/Windows/Fonts")
_LINUX_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
_REGISTERED_PDF_FONT_FAMILIES: set[str] = set()


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


def _persist_case_document_marker_if_needed(*, session: Session, content: str) -> None:
    case_id = session.case_id
    if case_id is None or not case_id.strip():
        return
    match = re.search(r"\[Attached local document path:\s*([^\]]+)\]", content, flags=re.IGNORECASE)
    if not match:
        return
    path_value = match.group(1).strip()
    if not path_value:
        return
    store = _get_store()
    store.add_case_text_document(
        case_id=case_id,
        original_filename=Path(path_value).name or "attachment.txt",
        content=f"Local path reference: {path_value}",
        uploaded_by_user_id=str(session.user_id) if session.user_id else None,
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
    _persist_case_message_if_needed(session=session, role="user", content=content, agent_name="User")
    _persist_case_document_marker_if_needed(session=session, content=content)

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
    _persist_case_message_if_needed(
        session=session,
        role="assistant",
        content=lawyer_message.content,
        agent_name=lawyer_message.agent_name,
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
        _persist_case_message_if_needed(
            session=session,
            role=core_message_role(core_message.role),
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
    case_update = _extract_case_update(source)
    document_kind = _detect_document_kind(source_lines, case_update)
    facts = _extract_document_facts(source_lines, case_update)

    if (language or "").strip().lower().startswith("sk"):
        title = f"Generovaný Dokument {session_id}"
        if document_kind == "rental_agreement":
            return title, _build_standard_slovak_agreement_lines(facts)
        if document_kind == "easement_demand":
            return title, _build_slovak_easement_demand_lines(facts)
        return title, _build_generic_slovak_case_document_lines(facts)

    title = f"Generated Document {session_id}"
    if document_kind == "rental_agreement":
        return title, _build_standard_english_agreement_lines(facts)
    if document_kind == "easement_demand":
        return title, _build_english_easement_demand_lines(facts)
    return title, _build_generic_english_case_document_lines(facts)


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
    facts_summary = _case_text(("case", "matter", "facts_summary"), "Právny problém podľa diskusie.")
    client_goal = _case_text(("case", "matter", "client_goal"), "Dosiahnuť primerané právne riešenie.")
    scheduled_for = _case_text(("case", "next_discussion", "scheduled_for"), "")
    agenda_items = next_discussion.get("agenda", []) if isinstance(next_discussion, dict) else []
    agenda = ", ".join(str(item).strip() for item in agenda_items if str(item).strip())

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
        "agenda": agenda or "Doplniť ďalší postup podľa vývoja komunikácie.",
    }


def _build_standard_slovak_agreement_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Nájomná zmluva",
        "uzatvorená podľa paragrafu 663 a nasl. Občianskeho zákonníka",
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
        "V [mesto], dna [datum]",
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


def _build_slovak_easement_demand_lines(facts: dict[str, str]) -> List[str]:
    return [
        "Predžalobná výzva na umožnenie výkonu vecného bremena",
        "",
        f"Adresát: {facts['opponent_name']}",
        f"Odosielateľ: {facts['client_name']}",
        "",
        "Vec:",
        "Výzva na zdržanie sa zásahu do výkonu vecného bremena a na vytvorenie prístupu",
        "",
        "Skutkový základ:",
        _with_period(facts["facts_summary"]),
        "",
        "Právny záujem klienta:",
        _with_period(facts["client_goal"]),
        "",
        "Požiadavka:",
        "Žiadam, aby ste sa zdržali akýchkoľvek stavebných zásahov, ktoré by znemožnili alebo podstatne sťažili výkon vecného bremena.",
        "Zároveň žiadam, aby ste na mieste výkonu vecného bremena zabezpečili primeraný vstup, najmä bránku alebo iné technické riešenie umožňujúce prístup k plynovej prípojke.",
        "",
        "Lehota na plnenie:",
        "Žiadam o písomné stanovisko bez zbytočného odkladu, najneskôr do 7 dní od doručenia tejto výzvy.",
        "",
        "Upozornenie:",
        "Ak nedôjde k náprave, klient zváži ďalšie právne kroky vrátane návrhu na neodkladné opatrenie a uplatnenia súdnej ochrany.",
        "",
        "Navrhované podklady k prílohe:",
        "1. Zmluva alebo rozhodnutie o vecnom bremene.",
        "2. Písomná komunikácia so susedom.",
        "3. Fotodokumentácia miesta prípojky a plánovaného plotu.",
        "",
        "Poznámka k ďalšiemu postupu:",
        _with_period(facts["agenda"]),
        "",
        "Podpis klienta / zástupcu: ____________________________",
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
    marker = content.lower().find("case_update_json")
    if marker < 0:
        return None
    json_start = content.find("{", marker)
    if json_start < 0:
        return None
    payload = _extract_json_object(content, json_start)
    if not payload:
        return None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


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
) -> Literal["rental_agreement", "easement_demand", "generic_case_document"]:
    combined = " ".join(source_lines).lower()
    case = case_update.get("case", {}) if isinstance(case_update, dict) else {}
    matter = case.get("matter", {}) if isinstance(case, dict) else {}
    topic = str(matter.get("topic", "")).lower()
    facts_summary = str(matter.get("facts_summary", "")).lower()
    client_goal = str(matter.get("client_goal", "")).lower()
    haystack = " ".join(part for part in (combined, topic, facts_summary, client_goal) if part)

    rental_tokens = (
        "prenaj",
        "nájom",
        "najom",
        "lease",
        "landlord",
        "tenant",
        "byt",
    )
    easement_tokens = (
        "vecné bremeno",
        "vecne bremeno",
        "easement",
        "plynov",
        "prípoj",
        "pripoj",
        "sused",
        "plot",
        "brán",
        "bránk",
        "brank",
    )
    if any(token in haystack for token in rental_tokens):
        return "rental_agreement"
    if any(token in haystack for token in easement_tokens):
        return "easement_demand"
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
        font_candidates = (
            (
                "AIJArial",
                _WINDOWS_FONT_DIR / "arial.ttf",
                _WINDOWS_FONT_DIR / "arialbd.ttf",
            ),
            (
                "AIJDejaVuSans",
                _LINUX_FONT_DIR / "DejaVuSans.ttf",
                _LINUX_FONT_DIR / "DejaVuSans-Bold.ttf",
            ),
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
        pdfmetrics.registerFont(TTFont(family_name, str(regular_path)))
        pdfmetrics.registerFont(TTFont(f"{family_name}-Bold", str(bold_path)))
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
