from .base import Agent
from .judge import create_judge
from .lawyer import create_lawyer
from .slovakia import create_lawyer_slovakia
from ..jurisdiction import is_slovakia
from ..llm import LLMClient


def create_lawyer_agent(llm: LLMClient, country: str) -> Agent:
    if is_slovakia(country):
        return create_lawyer_slovakia(llm)
    return create_lawyer(llm)


__all__ = ["Agent", "create_judge", "create_lawyer", "create_lawyer_agent", "create_lawyer_slovakia"]
