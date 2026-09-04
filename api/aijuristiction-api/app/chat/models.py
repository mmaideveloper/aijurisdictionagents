from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
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
    agent_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attachments: List[Attachment] = Field(default_factory=list)
    citations: List[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    status: str = "pending"


class Session(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: Optional[UUID] = None
    case_id: str | None = None
    country: str = ""
    language: str | None = None
    discussion_type: str = "advice"
    selected_model_profile_id: str | None = None
    state: SessionState = SessionState.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionResult(BaseModel):
    final_recommendation: str
    judge_rationale: str
    citations: List[dict[str, str]] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
