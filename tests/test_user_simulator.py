from __future__ import annotations

from dataclasses import dataclass

from aijurisdictionagents.agents.user_simulator import (
    AIUserSimulatorAgent,
    DEFAULT_INITIAL_LEGAL_PROBLEM,
)
from aijurisdictionagents.schemas import Message


@dataclass
class _FakeLLM:
    last_user_prompt: str = ""

    def complete(self, agent_name, system_prompt, conversation, documents) -> str:  # type: ignore[no-untyped-def]
        self.last_user_prompt = conversation[-1].content
        return "Test answer"


def test_ai_user_simulator_includes_initial_legal_problem_in_prompt() -> None:
    fake_llm = _FakeLLM()
    agent = AIUserSimulatorAgent(fake_llm, language="sk")

    answer = agent.prepare_random_answer(
        "Co presne chcete dosiahnut?",
        conversation=[],
        documents=[],
    )

    assert answer == "Test answer"
    assert "Co presne chcete dosiahnut?" in fake_llm.last_user_prompt
    assert DEFAULT_INITIAL_LEGAL_PROBLEM in fake_llm.last_user_prompt


def test_ai_user_simulator_prefers_real_initial_user_instruction() -> None:
    fake_llm = _FakeLLM()
    agent = AIUserSimulatorAgent(fake_llm, language="sk")
    opening = "Potrebujem analyzu k vypovedi z najmu a mam uz pisomnu zmluvu."

    agent.prepare_random_answer(
        "Aku mate dokumentaciu?",
        conversation=[
            Message(role="user", agent_name="User", content=opening),
        ],
        documents=[],
    )

    assert opening in fake_llm.last_user_prompt
