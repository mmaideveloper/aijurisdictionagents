import os

from aijurisdictionagents.llm import azure_foundry_client
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


def test_azure_foundry_client_clears_blank_sdk_auth_env(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeAzureOpenAI:
        def __init__(self, **kwargs: str) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(azure_foundry_client, "AzureOpenAI", FakeAzureOpenAI)
    monkeypatch.setenv("AZURE_OPENAI_AD_TOKEN", "   ")

    config = azure_foundry_client.AzureFoundryConfig(
        endpoint="https://example.openai.azure.com/",
        deployment="gpt-4o-mini",
        api_version="2024-12-01-preview",
        temperature=0.2,
        api_key="test-key",
        azure_ad_token=None,
    )

    azure_foundry_client.AzureFoundryClient(config)

    assert captured["api_key"] == "test-key"
    assert "azure_ad_token" not in captured
    assert os.getenv("AZURE_OPENAI_AD_TOKEN") is None


def test_azure_foundry_client_uses_openai_client_for_project_v1_api_key(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: str) -> None:
            captured.update(kwargs)

    class UnexpectedAzureOpenAI:
        def __init__(self, **kwargs: str) -> None:
            raise AssertionError(f"AzureOpenAI must not be used for v1: {kwargs}")

    monkeypatch.setattr(azure_foundry_client, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(azure_foundry_client, "AzureOpenAI", UnexpectedAzureOpenAI)

    config = azure_foundry_client.AzureFoundryConfig(
        endpoint="https://example.services.ai.azure.com/api/projects/legal/",
        deployment="gpt-5-mini",
        api_version="preview",
        temperature=0.2,
        api_key="test-key",
        azure_ad_token=None,
    )

    azure_foundry_client.AzureFoundryClient(config)

    assert captured["base_url"] == (
        "https://example.services.ai.azure.com/api/projects/legal/openai/v1"
    )
    assert captured["api_key"] == "test-key"
    assert "api_version" not in captured
    assert "azure_endpoint" not in captured


def test_azure_foundry_client_uses_bearer_token_as_v1_api_key(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: str) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(azure_foundry_client, "OpenAI", FakeOpenAI)

    config = azure_foundry_client.AzureFoundryConfig(
        endpoint="https://example.openai.azure.com/openai/v1/",
        deployment="gpt-5-mini",
        api_version="v1",
        temperature=0.2,
        api_key=None,
        azure_ad_token="test-entra-token",
    )

    azure_foundry_client.AzureFoundryClient(config)

    assert captured["base_url"] == "https://example.openai.azure.com/openai/v1"
    assert captured["api_key"] == "test-entra-token"
    assert "api_version" not in captured
    assert "azure_ad_token" not in captured


def test_azure_foundry_client_keeps_legacy_dated_azure_api(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeAzureOpenAI:
        def __init__(self, **kwargs: str) -> None:
            captured.update(kwargs)

    class UnexpectedOpenAI:
        def __init__(self, **kwargs: str) -> None:
            raise AssertionError(f"OpenAI must not be used for a dated Azure API: {kwargs}")

    monkeypatch.setattr(azure_foundry_client, "AzureOpenAI", FakeAzureOpenAI)
    monkeypatch.setattr(azure_foundry_client, "OpenAI", UnexpectedOpenAI)

    config = azure_foundry_client.AzureFoundryConfig(
        endpoint="https://example.openai.azure.com/",
        deployment="gpt-4o-mini",
        api_version="2024-12-01-preview",
        temperature=0.2,
        api_key="test-key",
        azure_ad_token=None,
    )

    azure_foundry_client.AzureFoundryClient(config)

    assert captured["azure_endpoint"] == "https://example.openai.azure.com/"
    assert captured["api_version"] == "2024-12-01-preview"
    assert captured["api_key"] == "test-key"
    assert "base_url" not in captured
