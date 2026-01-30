from aijurisdictionagents.agents import create_layer_agent
from aijurisdictionagents.llm import MockLLMClient


def test_layer_agent_routing() -> None:
    llm = MockLLMClient()
    slovak_agent = create_layer_agent(llm, "SK")
    assert slovak_agent.name == "LayerSlovakia"

    default_agent = create_layer_agent(llm, "US")
    assert default_agent.name == "Lawyer"
