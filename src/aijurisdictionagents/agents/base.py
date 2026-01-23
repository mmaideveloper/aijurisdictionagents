from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..llm import LLMClient
from ..schemas import Document, Message, Source


@dataclass
class Agent:
    name: str
    system_prompt: str
    llm: LLMClient

    def respond(
        self,
        conversation: Sequence[Message],
        documents: Sequence[Document],
        sources: Sequence[Source],
        system_prompt_override: str | None = None,
    ) -> Message:
        prompt = system_prompt_override or self.system_prompt
        content = self.llm.complete(self.name, prompt, conversation, documents)
        return Message(
            role="assistant",
            agent_name=self.name,
            content=content,
            sources=list(sources),
        )
