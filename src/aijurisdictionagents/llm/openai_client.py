from __future__ import annotations

import os
from dataclasses import dataclass, field
import logging
import time
from typing import Iterable, Sequence

from openai import APITimeoutError, OpenAI

from .base import ModelProcessingTimeout, elapsed_seconds, log_llm_request, log_llm_response
from ..model_parameters import ModelParameters
from ..schemas import Document, Message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str = "gpt-4o-mini"
    temperature: float | None = 0.2
    base_url: str | None = None
    provider_label: str = "openai"
    max_tokens: int | None = None
    model_parameters: ModelParameters = field(default_factory=dict)


class OpenAIClient:
    def __init__(self, config: OpenAIConfig) -> None:
        self._config = config
        if config.base_url:
            self._client = OpenAI(api_key=config.api_key, base_url=config.base_url.rstrip("/"))
        else:
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
            provider=self._config.provider_label,
            agent_name=agent_name,
            request_payload=messages,
        )
        request_kwargs: dict[str, object] = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "messages": messages,
        }
        if self._config.max_tokens is not None:
            request_kwargs["max_tokens"] = self._config.max_tokens
        if self._config.temperature is None:
            request_kwargs.pop("temperature", None)
        request_kwargs.update(self._config.model_parameters)
        logger.info(
            "llm_model_parameters provider=%s model=%s parameter_names=%s",
            self._config.provider_label,
            self._config.model,
            sorted(self._config.model_parameters),
        )
        started_at = time.monotonic()
        try:
            response = self._client.chat.completions.create(**request_kwargs)
        except APITimeoutError as exc:
            raise ModelProcessingTimeout(
                provider_class="external",
                provider=self._config.provider_label,
                model=self._config.model,
                timeout_seconds=_client_timeout_seconds(self._client),
                elapsed_seconds=elapsed_seconds(started_at),
            ) from exc
        content = response.choices[0].message.content if response.choices else ""
        normalized = (content or "").strip()
        log_llm_response(
            logger,
            provider=self._config.provider_label,
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


def _client_timeout_seconds(client: OpenAI) -> float | None:
    timeout = getattr(client, "timeout", None)
    read_timeout = getattr(timeout, "read", None)
    return float(read_timeout) if isinstance(read_timeout, (int, float)) else None
