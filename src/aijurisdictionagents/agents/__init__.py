from .base import Agent
from .ai_web_search import AIWebSearchAgent, CompanySearchAgent, EntityScreeningAgent, PersonSearchAgent
from .judge import create_judge
from .lawyer import create_lawyer
from .slovakia import create_lawyer_slovakia
from .user_simulator import AIUserSimulatorAgent
from .validator import AIAgentsValidator, ValidationReport, ValidatorInputs
from ..jurisdiction import is_slovakia
from ..llm import LLMClient


def create_lawyer_agent(llm: LLMClient, country: str) -> Agent:
    if is_slovakia(country):
        return create_lawyer_slovakia(llm)
    return create_lawyer(llm)


__all__ = [
    "Agent",
    "AIWebSearchAgent",
    "EntityScreeningAgent",
    "CompanySearchAgent",
    "PersonSearchAgent",
    "AIUserSimulatorAgent",
    "AIAgentsValidator",
    "ValidationReport",
    "ValidatorInputs",
    "create_judge",
    "create_lawyer",
    "create_lawyer_agent",
    "create_lawyer_slovakia",
]
