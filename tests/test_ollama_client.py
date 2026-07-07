from __future__ import annotations

import json

import pytest

from aijurisdictionagents.llm.ollama_client import OllamaClient, OllamaConfig
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

    content = client.complete(
        "Lawyer",
        "System prompt",
        [Message(role="user", content="Chcem sudne rozhodnutie o prenajme", agent_name="User")],
        [],
    )

    assert content == "Odpoved pre pouzivatela."
    assert requests[0]["url"] == "http://ollama.local:11434/api/chat"
    assert requests[0]["timeout"] == 42
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
