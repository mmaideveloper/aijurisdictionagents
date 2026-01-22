from __future__ import annotations

import os

from .base import LLMClient
from .mock import MockLLMClient

try:
    from .openai_client import OpenAIClient, load_openai_config_from_env
except ImportError:  # pragma: no cover - only triggers when OpenAI deps are missing.
    OpenAIClient = None  # type: ignore[assignment]
    load_openai_config_from_env = None  # type: ignore[assignment]


def get_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider == "mock":
        return MockLLMClient()
    if provider == "openai":
        if OpenAIClient is None or load_openai_config_from_env is None:
            raise ImportError("OpenAI dependencies not installed. Run: pip install openai")
        config = load_openai_config_from_env()
        return OpenAIClient(config)

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. Implement a client in aijurisdictionagents.llm."
    )


__all__ = [
    "LLMClient",
    "MockLLMClient",
    "OpenAIClient",
    "get_llm_client",
    "load_openai_config_from_env",
]
