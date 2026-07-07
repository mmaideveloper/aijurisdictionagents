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
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "mock":
        return MockLLMClient()

    raise ValueError(
        "Direct chat LLM setup from LLM_PROVIDER/.env is disabled. "
        "Use database model routing via get_routed_llm_client(), or set LLM_PROVIDER=mock "
        "only for deterministic offline tests."
    )


def __getattr__(name: str) -> Any:
    if name in {"OpenAIClient", "load_openai_config_from_env"}:
        module = import_module(".openai_client", __name__)
        return getattr(module, name)
    if name in {"OllamaClient", "OllamaConfig"}:
        module = import_module(".ollama_client", __name__)
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
    "OllamaClient",
    "OllamaConfig",
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
