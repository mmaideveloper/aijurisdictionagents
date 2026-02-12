from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.chat.models import Message, MessageRole, Session
from app.chat.repository import InMemoryChatRepository

router = APIRouter(prefix="/v1/chat", tags=["chat"])
_repository = InMemoryChatRepository()


class CreateSessionRequest(BaseModel):
    user_id: Optional[UUID] = None


class CreateMessageRequest(BaseModel):
    session_id: UUID
    role: MessageRole
    content: str


@router.post("/sessions", response_model=Session)
def create_session(payload: CreateSessionRequest) -> Session:
    session = Session(user_id=payload.user_id)
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
