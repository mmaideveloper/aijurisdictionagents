from __future__ import annotations

from importlib import import_module
import os
from typing import Any

from .base import LLMClient
from .mock import MockLLMClient
from .embeddings import (
    AzureFoundryEmbeddingClient,
    EmbeddingClient,
    EmbeddingRuntimeSummary,
    LocalEmbeddingClient,
    LocalEmbeddingConfig,
    MockEmbeddingClient,
    OpenAIEmbeddingClient,
    get_embedding_client,
    load_azure_foundry_embedding_config_from_env,
    load_embedding_model_option_from_env,
    load_embedding_runtime_summary_from_env,
    load_local_embedding_config_from_env,
    load_openai_embedding_config_from_env,
)


def get_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "azurefoundry").lower()
    if provider == "mock":
        return MockLLMClient()
    if provider == "openai":
        openai_client_type = __getattr__("OpenAIClient")
        load_openai_config = __getattr__("load_openai_config_from_env")
        config = load_openai_config()
        return openai_client_type(config)
    if provider in {"azurefoundry", "azure"}:
        azure_foundry_client_type = __getattr__("AzureFoundryClient")
        load_azure_foundry_config = __getattr__("load_azure_foundry_config_from_env")
        config = load_azure_foundry_config()
        return azure_foundry_client_type(config)

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. Implement a client in aijurisdictionagents.llm."
    )


def __getattr__(name: str) -> Any:
    if name in {"OpenAIClient", "load_openai_config_from_env"}:
        module = import_module(".openai_client", __name__)
        return getattr(module, name)
    if name in {"AzureFoundryClient", "load_azure_foundry_config_from_env"}:
        module = import_module(".azure_foundry_client", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLMClient",
    "EmbeddingClient",
    "EmbeddingRuntimeSummary",
    "MockLLMClient",
    "MockEmbeddingClient",
    "AzureFoundryClient",
    "AzureFoundryEmbeddingClient",
    "LocalEmbeddingClient",
    "LocalEmbeddingConfig",
    "OpenAIClient",
    "OpenAIEmbeddingClient",
    "get_llm_client",
    "get_embedding_client",
    "load_embedding_model_option_from_env",
    "load_embedding_runtime_summary_from_env",
    "load_azure_foundry_config_from_env",
    "load_azure_foundry_embedding_config_from_env",
    "load_local_embedding_config_from_env",
    "load_openai_config_from_env",
    "load_openai_embedding_config_from_env",
]
