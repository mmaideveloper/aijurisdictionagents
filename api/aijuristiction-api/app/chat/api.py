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


class CreateSessionRequest(BaseModel):
    user_id: Optional[UUID] = None
    country: str = "SK"
    language: str | None = None
    discussion_type: Literal["advice", "court"] = "advice"


class CreateMessageRequest(BaseModel):
    session_id: UUID
    role: MessageRole
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

    simulator = None
    simulator_documents = [CoreDocument(doc_id=d.doc_id, path=d.path, content=d.content) for d in payload.documents]
    if payload.user_simulation_mode == "AIUserSimulatorAgent":
        from aijurisdictionagents.agents import AIUserSimulatorAgent
        from aijurisdictionagents.llm import get_llm_client

        simulator = AIUserSimulatorAgent(get_llm_client(), language=session.language)

    def user_response_provider(_question: str, _timeout: float) -> str | None:
        if time.monotonic() > simulation_deadline:
            return None
        if simulator is not None and communication_minutes > 0:
            conversation = [
                CoreMessage(
                    role="assistant",
                    content=_question,
                    agent_name="CoreSystem",
                )
            ]
            return simulator.prepare_random_answer(
                _question,
                conversation=conversation,
                documents=simulator_documents,
            )
        if replies:
            return replies.popleft()
        return None

    def message_callback(core_message: CoreMessage) -> None:
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


@router.get("/sessions/{session_id}/result", response_model=SessionResult)
def get_session_result(session_id: UUID) -> SessionResult:
    result = _repository.get_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for session {session_id} not found")
    return result


@router.get("/sessions/{session_id}/export")
def export_session_result(session_id: UUID, format: Literal["json", "pdf"] = Query("json")) -> Response:
    result = _repository.get_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for session {session_id} not found")

    if format == "json":
        body = result.model_dump_json(indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="session-{session_id}.json"'},
        )

    pdf_content = _build_simple_pdf(
        title=f"Session {session_id}",
        lines=[
            "AI Jurisdiction Session Result",
            "",
            f"Final recommendation: {result.final_recommendation}",
            f"Judge rationale: {result.judge_rationale}",
        ],
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id}.pdf"'},
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
