from aijurisdictionagents.agents import AIUserSimulatorAgent, create_lawyer_agent
from aijurisdictionagents.llm import MockLLMClient
from aijurisdictionagents.schemas import Message


def test_lawyer_agent_routing() -> None:
    llm = MockLLMClient()
    slovak_agent = create_lawyer_agent(llm, "SK")
    assert slovak_agent.name == "LawyerSlovakia"

    default_agent = create_lawyer_agent(llm, "US")
    assert default_agent.name == "Lawyer"


def test_ai_user_simulator_agent_generates_answer() -> None:
    llm = MockLLMClient()
    simulator = AIUserSimulatorAgent(llm=llm, language="sk")

    answer = simulator.prepare_random_answer(
        question="Aký bol dátum podpisu zmluvy?",
        conversation=[Message(role="assistant", agent_name="CoreSystem", content="Aký bol dátum podpisu zmluvy?")],
        documents=[],
    )

    assert answer


def test_lawyer_prompt_requires_old_document_review() -> None:
    llm = MockLLMClient()
    lawyer = create_lawyer_agent(llm, "US")

    prompt_lower = lawyer.system_prompt.lower()
    assert "older version" in prompt_lower
    assert "upload" in prompt_lower
    assert "out of date" in prompt_lower
