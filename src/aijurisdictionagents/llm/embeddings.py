from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Protocol, Sequence


@dataclass(frozen=True)
class EmbeddingBatchResult:
    model_name: str
    vectors: list[list[float]]


@dataclass(frozen=True)
class EmbeddingRuntimeSummary:
    option: str
    model: str
    device: str = ""


_LOGGER = logging.getLogger(__name__)


class EmbeddingClient(Protocol):
    @property
    def model_name(self) -> str:
        ...

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        ...


class LocalEmbeddingBackend(Protocol):
    def encode_texts(self, texts: Sequence[str]) -> list[list[float]]:
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


@dataclass(frozen=True)
class LocalEmbeddingConfig:
    model: str
    model_directory: Path
    device: str = "auto"


class SentenceTransformerEmbeddingBackend:
    def __init__(self, model: Any, *, requested_device: str, selected_device: str) -> None:
        self._model = model
        self.requested_device = requested_device
        self.selected_device = selected_device

    def encode_texts(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            encoded = self._model.encode(
                list(texts),
                convert_to_numpy=False,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            if self.selected_device == "cpu":
                raise
            _LOGGER.warning(
                "Local embedding encode failed on device '%s'; falling back to CPU. Error: %s",
                self.selected_device,
                exc,
            )
            self._move_model_to_cpu()
            self.selected_device = "cpu"
            encoded = self._model.encode(
                list(texts),
                convert_to_numpy=False,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return _coerce_local_vectors(encoded)

    def _move_model_to_cpu(self) -> None:
        to_method = getattr(self._model, "to", None)
        if callable(to_method):
            to_method("cpu")


class LocalEmbeddingClient:
    def __init__(
        self,
        config: LocalEmbeddingConfig,
        backend: LocalEmbeddingBackend | None = None,
    ) -> None:
        self._config = config
        self._backend = backend or _load_local_embedding_backend(config)

    @property
    def model_name(self) -> str:
        return self._config.model

    @property
    def selected_device(self) -> str:
        return getattr(self._backend, "selected_device", "")

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        normalized_inputs = [_normalize_embedding_input(text) for text in texts]
        vectors = self._backend.encode_texts(normalized_inputs)
        return EmbeddingBatchResult(model_name=self.model_name, vectors=vectors)


class MockEmbeddingClient:
    @property
    def model_name(self) -> str:
        return "mock-embedding-32d"

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        vectors = [_build_mock_embedding(_normalize_embedding_input(text)) for text in texts]
        return EmbeddingBatchResult(model_name=self.model_name, vectors=vectors)


def get_embedding_client() -> EmbeddingClient:
    model_option = load_embedding_model_option_from_env()
    if model_option == "local":
        return LocalEmbeddingClient(load_local_embedding_config_from_env())
    provider = os.getenv("LLM_PROVIDER", "azurefoundry").strip().lower()
    if provider == "mock":
        return MockEmbeddingClient()
    if provider == "openai":
        return OpenAIEmbeddingClient(load_openai_embedding_config_from_env())
    if provider in {"azurefoundry", "azure"}:
        return AzureFoundryEmbeddingClient(load_azure_foundry_embedding_config_from_env())
    raise ValueError(f"Unsupported embedding provider '{provider}'.")


def load_embedding_runtime_summary_from_env() -> EmbeddingRuntimeSummary:
    option = load_embedding_model_option_from_env()
    if option == "local":
        config = load_local_embedding_config_from_env()
        return EmbeddingRuntimeSummary(
            option=option,
            model=config.model,
            device=_resolve_local_embedding_device(config.device),
        )

    provider = os.getenv("LLM_PROVIDER", "azurefoundry").strip().lower()
    if provider == "mock":
        model = MockEmbeddingClient().model_name
    elif provider == "openai":
        model = load_openai_embedding_config_from_env().model
    elif provider in {"azurefoundry", "azure"}:
        model = load_azure_foundry_embedding_config_from_env().deployment
    else:
        raise ValueError(f"Unsupported embedding provider '{provider}'.")

    return EmbeddingRuntimeSummary(option=option, model=model)


def load_embedding_model_option_from_env() -> str:
    option = os.getenv("SYSTEM_EMBEDDING_MODEL_OPTION", "").strip().lower() or "local"
    if option not in {"cloud", "local"}:
        raise ValueError("SYSTEM_EMBEDDING_MODEL_OPTION must be one of: cloud, local")
    return option


def load_local_embedding_config_from_env() -> LocalEmbeddingConfig:
    model = os.getenv("SYSTEM_EMBEDDING_MODEL", "").strip() or "all-MiniLM-L6-v2"
    device = os.getenv("SYSTEM_EMBEDDING_DEVICE", "").strip().lower() or "auto"
    if device not in {"auto", "cpu", "cuda", "mps"}:
        _LOGGER.warning("Unsupported SYSTEM_EMBEDDING_DEVICE='%s'; falling back to auto.", device)
        device = "auto"
    return LocalEmbeddingConfig(
        model=model,
        model_directory=_default_local_embedding_root() / _sanitize_model_directory_name(model),
        device=device,
    )


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


def _default_local_embedding_root() -> Path:
    root = _resolve_local_embedding_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_local_embedding_root() -> Path:
    candidates = _iter_local_embedding_root_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def _iter_local_embedding_root_candidates() -> list[Path]:
    candidates = [
        Path.cwd() / "aimodels",
        Path("/app/aimodels"),
        Path(__file__).resolve().parents[3] / "aimodels",
    ]
    deduplicated: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate.resolve(strict=False))
        if normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(candidate)
    return deduplicated


def _sanitize_model_directory_name(model_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", model_name.strip())
    return sanitized.strip("-") or "embedding-model"


def _resolve_local_embedding_source_name(model_name: str) -> str:
    if "/" in model_name:
        return model_name
    return f"sentence-transformers/{model_name}"


def _load_local_embedding_backend(config: LocalEmbeddingConfig) -> LocalEmbeddingBackend:
    return _cached_local_embedding_backend(
        model_name=config.model,
        model_directory=str(config.model_directory),
        requested_device=config.device,
    )


@lru_cache(maxsize=8)
def _cached_local_embedding_backend(
    *,
    model_name: str,
    model_directory: str,
    requested_device: str,
) -> LocalEmbeddingBackend:
    model_path = Path(model_directory)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    sentence_transformer_type = _load_sentence_transformer_type()
    selected_device = _resolve_local_embedding_device(requested_device)
    if (model_path / "modules.json").exists():
        try:
            model = sentence_transformer_type(str(model_path), device=selected_device)
        except Exception as exc:
            _LOGGER.warning(
                "Local embedding model load failed on device '%s'; falling back to CPU. Error: %s",
                selected_device,
                exc,
            )
            selected_device = "cpu"
            model = sentence_transformer_type(str(model_path), device=selected_device)
        return SentenceTransformerEmbeddingBackend(
            model,
            requested_device=requested_device,
            selected_device=selected_device,
        )

    source_name = _resolve_local_embedding_source_name(model_name)
    try:
        model = sentence_transformer_type(source_name, device=selected_device)
    except Exception as exc:
        _LOGGER.warning(
            "Local embedding model load failed on device '%s'; falling back to CPU. Error: %s",
            selected_device,
            exc,
        )
        selected_device = "cpu"
        model = sentence_transformer_type(source_name, device=selected_device)
    model.save(str(model_path))
    return SentenceTransformerEmbeddingBackend(
        model,
        requested_device=requested_device,
        selected_device=selected_device,
    )


def _resolve_local_embedding_device(requested_device: str) -> str:
    requested = (requested_device or "auto").strip().lower()
    if requested == "cpu":
        return "cpu"
    try:
        import torch
    except Exception as exc:
        _LOGGER.warning(
            "PyTorch is unavailable for embedding device detection; falling back to CPU. Error: %s",
            exc,
        )
        return "cpu"

    if requested in {"auto", "cuda"}:
        try:
            if torch.cuda.is_available():
                return "cuda"
            if requested == "cuda":
                _LOGGER.warning("SYSTEM_EMBEDDING_DEVICE=cuda requested but CUDA is unavailable; falling back to CPU.")
        except Exception as exc:
            _LOGGER.warning("CUDA detection failed; falling back to CPU. Error: %s", exc)
        if requested == "cuda":
            return "cpu"

    if requested in {"auto", "mps"}:
        try:
            mps_backend = getattr(torch.backends, "mps", None)
            if mps_backend is not None and mps_backend.is_available():
                return "mps"
            if requested == "mps":
                _LOGGER.warning("SYSTEM_EMBEDDING_DEVICE=mps requested but MPS is unavailable; falling back to CPU.")
        except Exception as exc:
            _LOGGER.warning("MPS detection failed; falling back to CPU. Error: %s", exc)

    return "cpu"


def _coerce_local_vectors(raw_vectors: Any) -> list[list[float]]:
    if hasattr(raw_vectors, "tolist"):
        raw_vectors = raw_vectors.tolist()
    if isinstance(raw_vectors, list):
        if not raw_vectors:
            return []
        first = raw_vectors[0]
        if isinstance(first, list) or hasattr(first, "tolist"):
            return [_coerce_float_vector(vector) for vector in raw_vectors]
        return [_coerce_float_vector(raw_vectors)]
    raise TypeError("Local embedding backend returned an unsupported vector payload.")


def _coerce_float_vector(raw_vector: Any) -> list[float]:
    if hasattr(raw_vector, "tolist"):
        raw_vector = raw_vector.tolist()
    if isinstance(raw_vector, list):
        return [float(value) for value in raw_vector]
    raise TypeError("Local embedding backend returned an unsupported vector payload.")


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


def _load_sentence_transformer_type() -> type[Any]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required when SYSTEM_EMBEDDING_MODEL_OPTION=local."
        ) from exc
    return SentenceTransformer
