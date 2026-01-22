from __future__ import annotations

from typing import Protocol, Sequence

from ..schemas import Document, Message


class LLMClient(Protocol):
    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        ...
