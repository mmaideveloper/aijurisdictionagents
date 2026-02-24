from __future__ import annotations

import json
import time
from collections import deque
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

from aijurisdictionagents.schemas import Document as CoreDocument
from aijurisdictionagents.schemas import Message as CoreMessage

router = APIRouter(prefix="/v1/chat", tags=["chat"], dependencies=[Depends(require_api_key)])
_repository = InMemoryChatRepository()
_FINISH_RESPONSES = {"finish", "no", "nope", "done", "exit", "quit", "stop"}


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

    def stream() -> str:
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
    if cleaned.lower() in _FINISH_RESPONSES:
        return _continue_discussion_reply(language, turn_index)
    if previous_reply and cleaned.lower() == previous_reply.strip().lower():
        return _continue_discussion_reply(language, turn_index + 1)
    return cleaned


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
            language=session.language,
        )
        filename = f"session-{session_id}-document.pdf"
    else:
        title, lines = _build_summary_export_content(
            session_id=session_id,
            result=result,
            messages=messages,
            language=session.language,
        )
        filename = f"session-{session_id}-summary.pdf"

    pdf_content = _build_simple_pdf(title=title, lines=lines)
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_simple_pdf(title: str, lines: List[str]) -> bytes:
    escaped_lines = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    text_lines = [f"({title}) Tj", "T*", "(----------------) Tj", "T*"]
    for line in escaped_lines:
        text_lines.append(f"({line}) Tj")
        text_lines.append("T*")
    content_stream = "BT /F1 11 Tf 50 770 Td " + " ".join(text_lines) + " ET"
    stream_bytes = content_stream.encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream_bytes)} >> stream\n".encode("latin-1") + stream_bytes + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]

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
        f"trailer << /Root 1 0 R /Size {len(objects)+1} >>\nstartxref\n{xref_pos}\n%%EOF".encode(
            "latin-1"
        )
    )
    return bytes(output)


def _build_summary_export_content(
    *,
    session_id: UUID,
    result: SessionResult,
    messages: List[Message],
    language: str | None,
) -> tuple[str, List[str]]:
    user_count = len([m for m in messages if m.role == MessageRole.USER])
    assistant_count = len([m for m in messages if m.role == MessageRole.ASSISTANT])
    if (language or "").strip().lower().startswith("sk"):
        return (
            f"Zhrnutie diskusie {session_id}",
            [
                "Zhrnutie diskusie",
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
            "Discussion summary",
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

    if (language or "").strip().lower().startswith("sk"):
        title = f"Generovany Dokument {session_id}"
        lines = ["Generovany dokument podla diskusie", ""] + source_lines
        return title, lines

    title = f"Generated Document {session_id}"
    lines = ["Generated document from discussion", ""] + source_lines
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
