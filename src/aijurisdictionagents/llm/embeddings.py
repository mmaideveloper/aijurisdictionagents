from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
import time
from typing import Any, Callable, Protocol, Sequence


@dataclass(frozen=True)
class EmbeddingBatchResult:
    model_name: str
    vectors: list[list[float]]


class EmbeddingClient(Protocol):
    @property
    def model_name(self) -> str:
        ...

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        ...


@dataclass(frozen=True)
class OpenAIEmbeddingConfig:
    api_key: str
    model: str


class OpenAIEmbeddingClient:
    def __init__(self, config: OpenAIEmbeddingConfig) -> None:
        openai_client_type = _load_openai_client_type()
        self._config = config
        self._client = openai_client_type(api_key=config.api_key)

    @property
    def model_name(self) -> str:
        return self._config.model

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        normalized_inputs = [_normalize_embedding_input(text) for text in texts]
        response = _request_embeddings_with_retry(
            lambda: self._client.embeddings.create(
                model=self._config.model,
                input=normalized_inputs,
            )
        )
        vectors = [list(item.embedding) for item in response.data]
        return EmbeddingBatchResult(model_name=self.model_name, vectors=vectors)


@dataclass(frozen=True)
class AzureFoundryEmbeddingConfig:
    endpoint: str
    deployment: str
    api_version: str
    api_key: str | None
    azure_ad_token: str | None


class AzureFoundryEmbeddingClient:
    def __init__(self, config: AzureFoundryEmbeddingConfig) -> None:
        azure_openai_client_type = _load_azure_openai_client_type()
        self._config = config
        _clear_blank_azure_openai_auth_env()
        if config.azure_ad_token:
            self._client = azure_openai_client_type(
                azure_endpoint=config.endpoint,
                api_version=config.api_version,
                azure_ad_token=config.azure_ad_token,
            )
        else:
            self._client = azure_openai_client_type(
                azure_endpoint=config.endpoint,
                api_version=config.api_version,
                api_key=config.api_key,
            )

    @property
    def model_name(self) -> str:
        return self._config.deployment

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        normalized_inputs = [_normalize_embedding_input(text) for text in texts]
        response = _request_embeddings_with_retry(
            lambda: self._client.embeddings.create(
                model=self._config.deployment,
                input=normalized_inputs,
            )
        )
        vectors = [list(item.embedding) for item in response.data]
        return EmbeddingBatchResult(model_name=self.model_name, vectors=vectors)


class MockEmbeddingClient:
    @property
    def model_name(self) -> str:
        return "mock-embedding-32d"

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        vectors = [_build_mock_embedding(_normalize_embedding_input(text)) for text in texts]
        return EmbeddingBatchResult(model_name=self.model_name, vectors=vectors)


def get_embedding_client() -> EmbeddingClient:
    provider = os.getenv("LLM_PROVIDER", "azurefoundry").strip().lower()
    if provider == "mock":
        return MockEmbeddingClient()
    if provider == "openai":
        return OpenAIEmbeddingClient(load_openai_embedding_config_from_env())
    if provider in {"azurefoundry", "azure"}:
        return AzureFoundryEmbeddingClient(load_azure_foundry_embedding_config_from_env())
    raise ValueError(f"Unsupported embedding provider '{provider}'.")


def load_openai_embedding_config_from_env() -> OpenAIEmbeddingConfig:
    api_key = os.getenv("OPENAI_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_KEY is required when LLM_PROVIDER=openai.")
    model = (
        os.getenv("OPENAI_EMBEDDINGS_MODEL", "").strip()
        or "text-embedding-3-large"
    )
    return OpenAIEmbeddingConfig(api_key=api_key, model=model)


def load_azure_foundry_embedding_config_from_env() -> AzureFoundryEmbeddingConfig:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = (
        os.getenv("AZURE_OPENAI_EMBEDDINGS_MODEL", "").strip()
        or "text-embedding-3-large"
    )
    api_version = (
        os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
        or os.getenv("OPENAI_API_VERSION", "").strip()
        or "2024-12-01-preview"
    )
    api_key = _optional_env("AZURE_OPENAI_API_KEY")
    azure_ad_token = _optional_env("AZURE_OPENAI_AD_TOKEN")
    if not endpoint:
        raise ValueError(
            "AZURE_OPENAI_ENDPOINT is required when LLM_PROVIDER=azurefoundry for embeddings."
        )
    if not api_key and not azure_ad_token:
        raise ValueError(
            "AZURE_OPENAI_API_KEY or AZURE_OPENAI_AD_TOKEN is required "
            "when LLM_PROVIDER=azurefoundry for embeddings."
        )
    return AzureFoundryEmbeddingConfig(
        endpoint=endpoint,
        deployment=deployment,
        api_version=api_version,
        api_key=api_key,
        azure_ad_token=azure_ad_token,
    )


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        os.environ.pop(name, None)
        return None
    return normalized


def _clear_blank_azure_openai_auth_env() -> None:
    _optional_env("AZURE_OPENAI_API_KEY")
    _optional_env("AZURE_OPENAI_AD_TOKEN")


def _normalize_embedding_input(text: str) -> str:
    normalized = text.strip()
    return normalized or " "


def _build_mock_embedding(text: str, *, dimensions: int = 32) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        offset = (index * 4) % len(digest)
        chunk = digest[offset : offset + 4]
        if len(chunk) < 4:
            chunk = (chunk + digest)[:4]
        integer = int.from_bytes(chunk, "big", signed=False)
        values.append(round((integer / 2**32) * 2 - 1, 6))
    return values


def _request_embeddings_with_retry(
    request: Callable[[], object],
    *,
    max_attempts: int = 4,
) -> object:
    attempt = 0
    while True:
        attempt += 1
        try:
            return request()
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= max_attempts:
                raise
            time.sleep(_retry_delay_seconds(exc, attempt=attempt))


def _retry_delay_seconds(error: Exception, *, attempt: int) -> float:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass
        retry_after_ms = headers.get("x-ms-retry-after-ms")
        if retry_after_ms:
            try:
                return max(float(retry_after_ms) / 1000.0, 1.0)
            except ValueError:
                pass

    match = re.search(r"retry after (\d+) seconds", str(error), flags=re.IGNORECASE)
    if match:
        return float(match.group(1))

    return float(min(60, 5 * (2 ** (attempt - 1))))


def _is_rate_limit_error(error: Exception) -> bool:
    try:
        rate_limit_error_type = _load_rate_limit_error_type()
    except ImportError:
        return False
    return isinstance(error, rate_limit_error_type)


def _load_openai_client_type() -> type[Any]:
    from openai import OpenAI

    return OpenAI


def _load_azure_openai_client_type() -> type[Any]:
    from openai import AzureOpenAI

    return AzureOpenAI


def _load_rate_limit_error_type() -> type[Exception]:
    from openai import RateLimitError

    return RateLimitError
