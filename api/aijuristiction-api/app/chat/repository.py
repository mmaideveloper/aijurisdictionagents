from __future__ import annotations

from threading import Lock
from typing import Dict, List
from uuid import UUID

from app.chat.models import Message, Session


class InMemoryChatRepository:
    def __init__(self) -> None:
        self._sessions: Dict[UUID, Session] = {}
        self._messages_by_session: Dict[UUID, List[Message]] = {}
        self._lock = Lock()

    def create_session(self, session: Session) -> Session:
        with self._lock:
            self._sessions[session.id] = session
            self._messages_by_session.setdefault(session.id, [])
        return session

    def get_session(self, session_id: UUID) -> Session | None:
        return self._sessions.get(session_id)

    def add_message(self, message: Message) -> Message:
        with self._lock:
            if message.session_id not in self._sessions:
                raise KeyError(f"Session {message.session_id} not found")
            self._messages_by_session.setdefault(message.session_id, []).append(message)
        return message

    def list_messages(self, session_id: UUID) -> List[Message]:
        return list(self._messages_by_session.get(session_id, []))
