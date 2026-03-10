from __future__ import annotations

import random
import textwrap
from dataclasses import dataclass
from typing import Sequence

from ..llm import LLMClient
from ..schemas import Document, Message

DEFAULT_INITIAL_LEGAL_PROBLEM = textwrap.dedent(
    """
    Potreboval by som pravnu analyzu k nasledujucemu problemu. Sused sme sa sudili
    o rozdelenie pozemku koli plynovej pripojke. Nepodarilo sa nam rozdelit pozemok
    tak, aby pripojka bola na hranici rozdeleneho pozemku, ale mame od nasho
    pozemku az k pripojke vecne bremeno. Teraz sa sused rozhodol postavit na svojom
    pozemku murovany 2 m plot, cim stratime moznost prist k plynovej pripojke v
    pripade poruchy. Co mozeme robit? Mozeme poziadat suseda, aby v plote na mieste
    vecneho bremena urobil branku alebo vstup? Ake su moznosti?
    """
).strip()


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
    - Do not ask follow-up questions back to the lawyer.
    - Do not repeat your initial legal question verbatim.
    - If the question asks for unknown facts, provide a plausible placeholder and
      clearly indicate uncertainty.
    - Keep all answers consistent with the same underlying legal dispute unless the
      conversation explicitly overrides a fact.
    - If the lawyer asks for dates, names, addresses, amounts, or timeline details,
      provide those details directly in one concise response.
    - Prefer one short paragraph.
    - Keep style natural, as if written by a real client in chat (small imperfections are acceptable).
    """
).strip()


@dataclass
class AIUserSimulatorAgent:
    llm: LLMClient
    language: str | None = None
    initial_legal_problem: str = DEFAULT_INITIAL_LEGAL_PROBLEM

    def prepare_random_answer(
        self,
        question: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        seed_hint = random.randint(1000, 9999)
        lang = self.language or "en"
        initial_legal_problem = self._resolve_initial_legal_problem(conversation)
        simulated_user_prompt = (
            f"Language: {lang}\n"
            f"Seed hint: {seed_hint}\n"
            f"Initial legal problem: {initial_legal_problem}\n"
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

    def _resolve_initial_legal_problem(self, conversation: Sequence[Message]) -> str:
        for message in conversation:
            if message.role.strip().lower() != "user":
                continue
            content = message.content.strip()
            if not content:
                continue
            if _looks_like_placeholder_opening(content):
                break
            return content
        return self.initial_legal_problem


def _looks_like_placeholder_opening(content: str) -> bool:
    normalized = " ".join(content.lower().split())
    if len(normalized) < 20:
        return True
    placeholders = {
        "ano",
        "áno",
        "ok",
        "okej",
        "start",
        "prosim",
        "prosím",
        "hi",
        "hello",
        "test",
    }
    return normalized in placeholders
