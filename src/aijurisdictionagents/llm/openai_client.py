from __future__ import annotations

import os
from dataclasses import dataclass
import logging
from typing import Iterable, Sequence

from openai import OpenAI

from .base import log_llm_request, log_llm_response
from ..schemas import Document, Message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.2


class OpenAIClient:
    def __init__(self, config: OpenAIConfig) -> None:
        self._config = config
        self._client = OpenAI(api_key=config.api_key)

    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if documents:
            messages.append(
                {
                    "role": "system",
                    "content": _render_documents(documents),
                }
            )

        for message in conversation:
            messages.append(
                {
                    "role": _to_openai_role(message.role),
                    "content": f"{message.agent_name}: {message.content}",
                }
            )

        log_llm_request(
            logger,
            provider="openai",
            agent_name=agent_name,
            request_payload=messages,
            message_count=len(conversation),
            document_count=len(documents),
        )
        response = self._client.chat.completions.create(
            model=self._config.model,
            temperature=self._config.temperature,
            messages=messages,
        )
        content = response.choices[0].message.content if response.choices else ""
        normalized = (content or "").strip()
        log_llm_response(
            logger,
            provider="openai",
            agent_name=agent_name,
            raw_response=normalized,
        )
        return normalized


def load_openai_config_from_env() -> OpenAIConfig:
    api_key = os.getenv("OPENAI_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_KEY is required when LLM_PROVIDER=openai.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    return OpenAIConfig(api_key=api_key, model=model, temperature=temperature)


def _render_documents(documents: Iterable[Document], max_chars: int = 4000) -> str:
    chunks = ["Context documents:"]
    total = 0
    for doc in documents:
        header = f"[{os.path.basename(doc.path)}]"
        body = doc.content.strip().replace("\n", " ")
        snippet = body[:800]
        entry = f"{header} {snippet}"
        total += len(entry)
        if total > max_chars:
            break
        chunks.append(entry)
    return "\n".join(chunks)


def _to_openai_role(role: str) -> str:
    if role in {"user", "assistant", "system"}:
        return role
    return "user"
