from pathlib import Path

from dotenv import load_dotenv

from aijurisdictionagents.llm.azure_foundry_client import (
    AzureFoundryClient,
    load_azure_foundry_config_from_env,
)
from aijurisdictionagents.schemas import Message

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

print("Testing Azure Foundry client")

config = load_azure_foundry_config_from_env()
client = AzureFoundryClient(config)
response = client.complete(
    agent_name="smoke-test",
    system_prompt="You are a helpful assistant.",
    conversation=[
        Message(
            role="user",
            agent_name="user",
            content="I am going to Paris, what should I see?",
        )
    ],
    documents=[],
)

print(response)
