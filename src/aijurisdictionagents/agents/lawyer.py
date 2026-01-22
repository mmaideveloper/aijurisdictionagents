from __future__ import annotations

from .base import Agent
from ..llm import LLMClient


def create_lawyer(llm: LLMClient) -> Agent:
    system_prompt = (
        "You are a lawyer advocating for the user's position. "
        "Ground arguments in the provided documents and identify favorable facts."
    )
    return Agent(name="Lawyer", system_prompt=system_prompt, llm=llm)
