from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import socket
import time
from typing import Any, Iterable, Sequence, cast
from urllib import error, request

from .base import (
    ModelProcessingTimeout,
    elapsed_seconds,
    execute_correlated_model_call,
    log_llm_request,
    log_llm_response,
)
from ..correlation import correlation_headers, record_debug_event
from ..model_parameters import ModelParameters
from ..schemas import Document, Message

import logging


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 256
    timeout_seconds: float = 600.0
    think: bool = False
    provider_label: str = "local_ollama"
    model_parameters: ModelParameters = field(default_factory=dict)


class OllamaClient:
    def __init__(self, config: OllamaConfig) -> None:
        self._config = config
        self._base_url = _ollama_base_url(config.base_url)

    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        if documents:
            messages.append({"role": "system", "content": _render_documents(documents)})
        for message in conversation:
            messages.append(
                {
                    "role": _to_ollama_role(message.role),
                    "content": f"{message.agent_name}: {message.content}",
                }
            )

        log_llm_request(
            logger,
            provider=self._config.provider_label,
            agent_name=agent_name,
            request_payload=messages,
        )
        options: dict[str, object] = {
            "temperature": self._config.temperature,
            "num_predict": self._config.max_tokens,
        }
        for name, value in self._config.model_parameters.items():
            options["num_predict" if name == "max_tokens" else name] = value
        logger.info(
            "llm_model_parameters provider=%s model=%s parameter_names=%s",
            self._config.provider_label,
            self._config.model,
            sorted(self._config.model_parameters),
        )
        payload = {
            "model": self._config.model,
            "messages": messages,
            "stream": False,
            "think": self._config.think,
            "options": options,
        }
        response_payload = execute_correlated_model_call(
            provider=self._config.provider_label,
            model=self._config.model,
            agent_name=agent_name,
            request_payload=messages,
            invoke=lambda: self._post_json("/api/chat", payload),
        )
        message_payload = response_payload.get("message")
        response_message = cast(dict[str, object], message_payload if isinstance(message_payload, dict) else {})
        content = str(response_message.get("content") or "").strip()
        if not content:
            reason = str(response_message.get("reasoning") or "").strip()
            if reason:
                record_debug_event(
                    "model",
                    "response_validation",
                    "failed",
                    {
                        "provider": self._config.provider_label,
                        "model": self._config.model,
                        "error_type": "reasoning_only_response",
                    },
                )
                raise RuntimeError(
                    "Ollama returned reasoning without a final answer. "
                    "Disable model thinking or increase the local output limit."
                )
        log_llm_response(
            logger,
            provider=self._config.provider_label,
            agent_name=agent_name,
            raw_response=content,
        )
        return content

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self._base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json", **correlation_headers()},
            method="POST",
        )
        started_at = time.monotonic()
        try:
            with request.urlopen(req, timeout=self._config.timeout_seconds) as response:  # noqa: S310
                loaded = json.loads(response.read().decode("utf-8"))
                return cast(dict[str, Any], loaded)
        except (TimeoutError, socket.timeout) as exc:
            raise ModelProcessingTimeout(
                provider_class="local",
                provider=self._config.provider_label,
                model=self._config.model,
                timeout_seconds=self._config.timeout_seconds,
                elapsed_seconds=elapsed_seconds(started_at),
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ModelProcessingTimeout(
                    provider_class="local",
                    provider=self._config.provider_label,
                    model=self._config.model,
                    timeout_seconds=self._config.timeout_seconds,
                    elapsed_seconds=elapsed_seconds(started_at),
                ) from exc
            raise RuntimeError(f"Ollama request failed: {exc}") from exc


def _ollama_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3].rstrip("/")
    if not normalized:
        raise ValueError("Ollama base URL is required.")
    return normalized


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


def _to_ollama_role(role: str) -> str:
    if role in {"user", "assistant", "system"}:
        return role
    return "user"
