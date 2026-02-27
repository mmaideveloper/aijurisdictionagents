from __future__ import annotations

from .base import Agent
from ..llm import LLMClient


def create_judge(llm: LLMClient) -> Agent:
    system_prompt = (
        "You are a judge evaluating the lawyer's arguments. "
        "Ask clarifying questions, weigh the evidence, issue a reasoned decision, and check whether the exchange feels realistic for human legal intake."
    )
    return Agent(name="Judge", system_prompt=system_prompt, llm=llm)
