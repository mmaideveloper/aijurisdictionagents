from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .base import LLMClient
from ..schemas import Document, Message


class MockLLMClient:
    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        user_message = _latest_user_message(conversation)
        doc_list = ", ".join(Path(doc.path).name for doc in documents[:3])
        if not doc_list:
            doc_list = "no documents"

        agent_key = agent_name.lower()
        if "lawyer" in agent_key:
            return (
                "Legal position: I advocate for the user's requested outcome. "
                f"Key facts referenced from {doc_list}. "
                f"User focus: {user_message}"
            )
        if "judge" in agent_key:
            return (
                "Judicial view: I weigh the arguments and evidence neutrally. "
                "Clarifying question: What jurisdiction or governing law applies? "
                f"User focus: {user_message}"
            )
        if "finalsummary" in agent_key:
            return (
                "Recommendation: Proceed with the user's requested position.\n"
                "Rationale: The discussion supports the user's arguments based on the provided facts."
            )

        return f"Response prepared for {agent_name}. User focus: {user_message}"


def _latest_user_message(conversation: Sequence[Message]) -> str:
    for message in reversed(conversation):
        if message.role == "user":
            return message.content
    return ""
