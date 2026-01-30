from .base import Agent
from .judge import create_judge
from .lawyer import create_lawyer
from .slovakia import create_layer_slovakia
from ..jurisdiction import is_slovakia
from ..llm import LLMClient


def create_layer_agent(llm: LLMClient, country: str) -> Agent:
    if is_slovakia(country):
        return create_layer_slovakia(llm)
    return create_lawyer(llm)


__all__ = ["Agent", "create_judge", "create_lawyer", "create_layer_agent", "create_layer_slovakia"]
