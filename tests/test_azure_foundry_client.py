import os

from aijurisdictionagents.llm.azure_foundry_client import load_azure_foundry_config_from_env


def test_load_azure_foundry_config_ignores_blank_ad_token(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_AD_TOKEN", "   ")

    config = load_azure_foundry_config_from_env()

    assert config.api_key == "test-key"
    assert config.azure_ad_token is None
    assert os.getenv("AZURE_OPENAI_AD_TOKEN") is None
