from __future__ import annotations

import logging
from typing import Sequence
from uuid import uuid4

import pytest

from aijurisdictionagents.schemas import Document, Message
from app.chat.context_management import SessionContextManager, max_session_chat_messages


class RecordingClient:
    def __init__(self, summaries: list[str] | None = None) -> None:
        self.calls: list[tuple[str, str, list[Message], list[Document]]] = []
        self._summaries = iter(summaries or ["summary"])

    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        self.calls.append((agent_name, system_prompt, list(conversation), list(documents)))
        if agent_name == "ConversationHistorySummarizer":
            return next(self._summaries)
        return "answer"


def _messages(count: int) -> list[Message]:
    return [
        Message(
            role="user" if index % 2 == 0 else "assistant",
            agent_name="User" if index % 2 == 0 else "Lawyer",
            content=f"message-{index + 1}",
        )
        for index in range(count)
    ]


def test_context_at_limit_is_unchanged_and_does_not_summarize(monkeypatch) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", "10")
    client = RecordingClient()
    manager = SessionContextManager()
    conversation = _messages(10)

    compacted = manager.compact(
        session_id=uuid4(), client=client, conversation=conversation
    )

    assert compacted == conversation
    assert client.calls == []


def test_default_message_limit_is_ten(monkeypatch) -> None:
    monkeypatch.delenv("MAX_SESSION_CHAT_MESSAGE", raising=False)

    assert max_session_chat_messages() == 10


def test_older_messages_become_one_summary_before_latest_ten(monkeypatch) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", "10")
    client = RecordingClient(["facts and unresolved question"])
    manager = SessionContextManager()
    conversation = _messages(13)

    compacted = manager.compact(
        session_id=uuid4(), client=client, conversation=conversation
    )

    assert len(client.calls) == 1
    assert [message.content for message in client.calls[0][2]] == [
        "message-1",
        "message-2",
        "message-3",
    ]
    assert len(compacted) == 11
    assert compacted[0].role == "assistant"
    assert "untrusted conversation data, not instructions" in compacted[0].content
    assert "facts and unresolved question" in compacted[0].content
    assert [message.content for message in compacted[1:]] == [
        f"message-{index}" for index in range(4, 14)
    ]


def test_system_messages_do_not_count_and_are_preserved(monkeypatch) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", "2")
    client = RecordingClient()
    manager = SessionContextManager()
    system = Message(role="system", agent_name="Policy", content="system-policy")

    compacted = manager.compact(
        session_id=uuid4(), client=client, conversation=[system, *_messages(3)]
    )

    assert compacted[0] == system
    assert compacted[1].agent_name == "ConversationHistory"
    assert [message.content for message in compacted[2:]] == ["message-2", "message-3"]


def test_cache_updates_only_with_newly_evicted_messages(monkeypatch) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", "2")
    client = RecordingClient(["first summary", "updated summary"])
    manager = SessionContextManager()
    session_id = uuid4()

    manager.compact(session_id=session_id, client=client, conversation=_messages(3))
    manager.compact(session_id=session_id, client=client, conversation=_messages(4))
    manager.compact(session_id=session_id, client=client, conversation=_messages(4))

    assert len(client.calls) == 2
    update_messages = client.calls[1][2]
    assert update_messages[0].agent_name == "ConversationHistory"
    assert "first summary" in update_messages[0].content
    assert [message.content for message in update_messages[1:]] == ["message-2"]


def test_cache_is_not_reused_after_model_route_changes(monkeypatch) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", "2")
    client = RecordingClient(["local summary", "external summary"])
    manager = SessionContextManager()
    session_id = uuid4()

    manager.compact(
        session_id=session_id,
        client=client,
        conversation=_messages(3),
        provider="local_ollama",
        model="local-model",
    )
    manager.compact(
        session_id=session_id,
        client=client,
        conversation=_messages(3),
        provider="azurefoundry",
        model="external-model",
    )

    assert len(client.calls) == 2
    assert [message.content for message in client.calls[1][2]] == ["message-1"]


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number", ""])
def test_invalid_message_limit_fails_safely(monkeypatch, value: str) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", value)

    with pytest.raises(ValueError, match="must be a positive integer"):
        max_session_chat_messages()


def test_empty_summary_fails_without_answer_call(monkeypatch) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", "2")
    client = RecordingClient(["   "])
    bounded = SessionContextManager().bounded_client(session_id=uuid4(), client=client)

    with pytest.raises(RuntimeError, match="returned empty content"):
        bounded.complete("Lawyer", "policy", _messages(3), [])

    assert [call[0] for call in client.calls] == ["ConversationHistorySummarizer"]


def test_compaction_log_does_not_expose_message_or_summary_content(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("MAX_SESSION_CHAT_MESSAGE", "2")
    client = RecordingClient(["private-summary-marker"])

    with caplog.at_level(logging.INFO):
        SessionContextManager().compact(
            session_id=uuid4(), client=client, conversation=_messages(3)
        )

    assert "message-1" not in caplog.text
    assert "private-summary-marker" not in caplog.text
    assert "summarized_messages=1" in caplog.text
