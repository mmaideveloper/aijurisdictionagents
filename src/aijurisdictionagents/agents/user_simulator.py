from __future__ import annotations

import random
import textwrap
from dataclasses import dataclass
from typing import Sequence

from ..llm import LLMClient
from ..schemas import Document, Message


USER_SIMULATOR_PROMPT = textwrap.dedent(
    """
    You are AIUserSimulatorAgent.
    Your role is to act as an end user in a legal intake chat.

    TASK
    - Answer the latest core system question in the requested language.
    - Keep answers realistic, concise, and fact-oriented.
    - Provide valid but random details (dates, durations, amounts, timeline clues)
      without using real personal data.

    RULES
    - Return only a plain text answer (no markdown, no JSON).
    - If the question asks for unknown facts, provide a plausible placeholder and
      clearly indicate uncertainty.
    - Prefer one short paragraph.
    """
).strip()


@dataclass
class AIUserSimulatorAgent:
    llm: LLMClient
    language: str | None = None

    def prepare_random_answer(
        self,
        question: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        seed_hint = random.randint(1000, 9999)
        lang = self.language or "en"
        simulated_user_prompt = (
            f"Language: {lang}\n"
            f"Seed hint: {seed_hint}\n"
            f"Core question: {question}\n"
            "Generate one concise user answer with random but valid data."
        )
        user_turn = Message(role="user", agent_name="EndUser", content=simulated_user_prompt)
        answer = self.llm.complete(
            agent_name="AIUserSimulatorAgent",
            system_prompt=USER_SIMULATOR_PROMPT,
            conversation=[*conversation, user_turn],
            documents=documents,
        ).strip()
        if answer:
            return answer
        return "I can share additional details, but I need a bit more context about what to provide first."
