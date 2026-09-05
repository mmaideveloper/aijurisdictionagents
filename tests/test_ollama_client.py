from __future__ import annotations

import json

import pytest

from aijurisdictionagents.llm.base import ModelProcessingTimeout, read_positive_finite_env_seconds
from aijurisdictionagents.llm.ollama_client import OllamaClient, OllamaConfig
from aijurisdictionagents.correlation import correlation_scope
from aijurisdictionagents.schemas import Message


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_ollama_client_uses_native_chat_without_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(req, timeout: float):  # type: ignore[no-untyped-def]
        requests.append(
            {
                "url": req.full_url,
                "payload": json.loads(req.data.decode("utf-8")),
                "timeout": timeout,
                "headers": dict(req.header_items()),
            }
        )
        return _FakeResponse({"message": {"role": "assistant", "content": "Odpoved pre pouzivatela."}})

    monkeypatch.setattr("aijurisdictionagents.llm.ollama_client.request.urlopen", fake_urlopen)

    client = OllamaClient(
        OllamaConfig(
            base_url="http://ollama.local:11434/v1",
            model="qwen3:1.7b",
            timeout_seconds=42,
        )
    )

    with correlation_scope(
        correlation_id="corr-ollama-303",
        session_id="session-303",
        request_id="request-parent",
    ):
        content = client.complete(
            "Lawyer",
            "System prompt",
            [Message(role="user", content="Chcem sudne rozhodnutie o prenajme", agent_name="User")],
            [],
        )

    assert content == "Odpoved pre pouzivatela."
    assert requests[0]["url"] == "http://ollama.local:11434/api/chat"
    assert requests[0]["timeout"] == 42
    assert requests[0]["headers"]["X-correlation-id"] == "corr-ollama-303"
    assert requests[0]["headers"]["X-parent-request-id"] == "request-parent"
    payload = requests[0]["payload"]
    assert payload["model"] == "qwen3:1.7b"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["options"]["num_predict"] == 256


def test_ollama_client_rejects_reasoning_only_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_req, timeout: float):  # type: ignore[no-untyped-def]
        return _FakeResponse({"message": {"role": "assistant", "content": "", "reasoning": "internal thoughts"}})

    monkeypatch.setattr("aijurisdictionagents.llm.ollama_client.request.urlopen", fake_urlopen)
    client = OllamaClient(OllamaConfig(base_url="http://ollama.local:11434", model="qwen3:1.7b"))

    with pytest.raises(RuntimeError, match="reasoning without a final answer"):
        client.complete("Lawyer", "System prompt", [Message(role="user", content="Test", agent_name="User")], [])


def test_ollama_client_raises_typed_local_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_req, timeout: float):  # type: ignore[no-untyped-def]
        raise TimeoutError("timed out")

    monkeypatch.setattr("aijurisdictionagents.llm.ollama_client.request.urlopen", fake_urlopen)
    client = OllamaClient(
        OllamaConfig(
            base_url="http://ollama.local:11434",
            model="qwen3:4b",
            timeout_seconds=0.25,
        )
    )

    with pytest.raises(ModelProcessingTimeout) as raised:
        client.complete("Lawyer", "System prompt", [Message(role="user", content="Test", agent_name="User")], [])

    assert raised.value.code == "local_model_timeout"
    assert raised.value.provider_class == "local"
    assert raised.value.provider == "local_ollama"
    assert raised.value.model == "qwen3:4b"
    assert raised.value.timeout_seconds == 0.25


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "not-a-number"])
def test_positive_finite_timeout_config_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("LOCAL_LLM_REQUEST_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError, match="finite number greater than zero"):
        read_positive_finite_env_seconds("LOCAL_LLM_REQUEST_TIMEOUT_SECONDS", 600)
