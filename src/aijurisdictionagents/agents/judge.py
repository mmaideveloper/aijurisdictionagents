from __future__ import annotations

from .base import Agent
from ..llm import LLMClient


def create_judge(llm: LLMClient) -> Agent:
    system_prompt = (
        "You are a judge evaluating the lawyer's arguments. "
        "Ask clarifying questions, weigh the evidence, and issue a reasoned decision."
    )
    return Agent(name="Judge", system_prompt=system_prompt, llm=llm)
