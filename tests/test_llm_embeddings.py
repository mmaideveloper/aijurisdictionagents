import sys
from types import SimpleNamespace

import httpx
from openai import RateLimitError

from aijurisdictionagents.llm import embeddings


def _rate_limit_response(*, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://example.test/embeddings")
    return httpx.Response(429, headers=headers, request=request)


def test_request_embeddings_with_retry_retries_rate_limits(monkeypatch) -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def flaky_request() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RateLimitError(
                "retry after 1 seconds",
                response=_rate_limit_response(headers={"retry-after": "1"}),
                body={},
            )
        return "ok"

    monkeypatch.setattr(embeddings.time, "sleep", fake_sleep)

    result = embeddings._request_embeddings_with_retry(flaky_request, max_attempts=4)

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 1.0]


def test_retry_delay_seconds_parses_rate_limit_message_without_headers() -> None:
    error = RateLimitError(
        "Please retry after 42 seconds.",
        response=_rate_limit_response(),
        body={},
    )

    delay = embeddings._retry_delay_seconds(error, attempt=2)

    assert delay == 42.0


def test_local_embedding_defaults_apply_when_env_vars_are_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SYSTEM_EMBEDDING_MODEL_OPTION", raising=False)
    monkeypatch.delenv("SYSTEM_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("SYSTEM_EMBEDDING_DEVICE", raising=False)
    monkeypatch.setattr(embeddings, "_default_local_embedding_root", lambda: tmp_path / "aimodels")
    monkeypatch.setattr(embeddings, "_resolve_local_embedding_device", lambda _device: "cpu")

    config = embeddings.load_local_embedding_config_from_env()
    option = embeddings.load_embedding_model_option_from_env()
    summary = embeddings.load_embedding_runtime_summary_from_env()

    assert option == "local"
    assert config.model == "all-MiniLM-L6-v2"
    assert config.model_directory == tmp_path / "aimodels" / "all-MiniLM-L6-v2"
    assert config.device == "auto"
    assert summary.option == "local"
    assert summary.model == "all-MiniLM-L6-v2"
    assert summary.device == "cpu"


def test_local_embedding_device_can_be_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SYSTEM_EMBEDDING_DEVICE", "cuda")
    monkeypatch.setattr(embeddings, "_default_local_embedding_root", lambda: tmp_path / "aimodels")

    config = embeddings.load_local_embedding_config_from_env()

    assert config.device == "cuda"


def test_invalid_local_embedding_device_falls_back_to_auto(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SYSTEM_EMBEDDING_DEVICE", "tpu")
    monkeypatch.setattr(embeddings, "_default_local_embedding_root", lambda: tmp_path / "aimodels")

    config = embeddings.load_local_embedding_config_from_env()

    assert config.device == "auto"


def test_resolve_local_embedding_device_uses_cuda_when_available(monkeypatch) -> None:
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    device = embeddings._resolve_local_embedding_device("auto")

    assert device == "cuda"


def test_resolve_local_embedding_device_falls_back_when_cuda_unavailable(monkeypatch) -> None:
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    device = embeddings._resolve_local_embedding_device("cuda")

    assert device == "cpu"


def test_sentence_transformer_backend_falls_back_to_cpu_after_gpu_encode_error() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.device = "cuda"
            self.encode_calls = 0

        def encode(self, texts: list[str], **_kwargs: object) -> list[list[float]]:
            self.encode_calls += 1
            if self.device == "cuda":
                raise RuntimeError("CUDA out of memory")
            return [[1, 2, 3] for _text in texts]

        def to(self, device: str) -> None:
            self.device = device

    fake_model = FakeModel()
    backend = embeddings.SentenceTransformerEmbeddingBackend(
        fake_model,
        requested_device="auto",
        selected_device="cuda",
    )

    vectors = backend.encode_texts(["first", "second"])

    assert vectors == [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    assert fake_model.encode_calls == 2
    assert backend.selected_device == "cpu"


def test_embedding_runtime_summary_uses_cloud_model_when_requested(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL_OPTION", "cloud")
    monkeypatch.setenv("LLM_PROVIDER", "azurefoundry")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-large")

    summary = embeddings.load_embedding_runtime_summary_from_env()

    assert summary.option == "cloud"
    assert summary.model == "text-embedding-3-large"


def test_get_embedding_client_uses_local_embedding_mode(monkeypatch, tmp_path) -> None:
    class FakeLocalBackend:
        def encode_texts(self, texts: list[str]) -> list[list[float]]:
            assert texts == ["lease termination clause"]
            return [[0.1, 0.2, 0.3]]

    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL_OPTION", "local")
    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setattr(embeddings, "_default_local_embedding_root", lambda: tmp_path / "aimodels")
    monkeypatch.setattr(embeddings, "_load_local_embedding_backend", lambda _config: FakeLocalBackend())

    config = embeddings.load_local_embedding_config_from_env()
    client = embeddings.get_embedding_client()
    result = client.embed_texts(["lease termination clause"])

    assert config.model == "all-MiniLM-L6-v2"
    assert config.model_directory == tmp_path / "aimodels" / "all-MiniLM-L6-v2"
    assert client.model_name == "all-MiniLM-L6-v2"
    assert result.model_name == "all-MiniLM-L6-v2"
    assert result.vectors == [[0.1, 0.2, 0.3]]


def test_default_local_embedding_root_prefers_current_working_directory(monkeypatch, tmp_path) -> None:
    working_directory = tmp_path / "workspace"
    expected_root = working_directory / "aimodels"
    expected_root.mkdir(parents=True)
    monkeypatch.chdir(working_directory)

    resolved = embeddings._default_local_embedding_root()

    assert resolved == expected_root
