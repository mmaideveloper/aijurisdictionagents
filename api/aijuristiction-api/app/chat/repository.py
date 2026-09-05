from __future__ import annotations

from threading import Lock
from typing import Dict, List
from uuid import UUID
from datetime import datetime, timedelta, timezone

from app.chat.models import Message, Session, SessionResult, SessionState
from aijurisdictionagents.correlation import record_debug_event


class InMemoryChatRepository:
    def __init__(self) -> None:
        self._sessions: Dict[UUID, Session] = {}
        self._messages_by_session: Dict[UUID, List[Message]] = {}
        self._results: Dict[UUID, SessionResult] = {}
        self._lock = Lock()

    def create_session(self, session: Session) -> Session:
        with self._lock:
            self._sessions[session.id] = session
            self._messages_by_session.setdefault(session.id, [])
        return session

    def get_session(self, session_id: UUID) -> Session | None:
        return self._sessions.get(session_id)

    def get_session_by_correlation_id(self, correlation_id: str) -> Session | None:
        target = correlation_id.strip()
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return next(
            (
                session
                for session in self._sessions.values()
                if session.correlation_id == target and session.created_at > cutoff
            ),
            None,
        )

    def add_message(self, message: Message) -> Message:
        with self._lock:
            if message.session_id not in self._sessions:
                raise KeyError(f"Session {message.session_id} not found")
            self._messages_by_session.setdefault(message.session_id, []).append(message)
        record_debug_event(
            "chat",
            "message_persisted",
            "completed",
            {
                "message_id": str(message.id),
                "session_id": str(message.session_id),
                "role": message.role.value,
                "agent_name": message.agent_name or "",
                "content": message.content,
            },
        )
        return message

    def list_messages(self, session_id: UUID) -> List[Message]:
        return list(self._messages_by_session.get(session_id, []))

    def set_result(self, session_id: UUID, result: SessionResult) -> None:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"Session {session_id} not found")
            self._results[session_id] = result
            self._sessions[session_id].state = SessionState.COMPLETED
        record_debug_event(
            "chat",
            "session_result",
            "completed",
            {"session_id": str(session_id), "result": result.model_dump(mode="json")},
        )

    def reactivate_session(self, session_id: UUID) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].state = SessionState.ACTIVE

    def get_result(self, session_id: UUID) -> SessionResult | None:
        return self._results.get(session_id)

    def mark_failed(self, session_id: UUID) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].state = SessionState.FAILED
