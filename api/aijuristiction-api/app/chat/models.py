from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SessionState(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class User(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    email: str


class Attachment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    filename: str
    content_type: str


class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    role: MessageRole
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attachments: List[Attachment] = Field(default_factory=list)


class GenerationJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    status: str = "pending"


class Session(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: Optional[UUID] = None
    state: SessionState = SessionState.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
