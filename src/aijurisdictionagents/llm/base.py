from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Protocol, Sequence

from ..schemas import Document, Message


class LLMClient(Protocol):
    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        conversation: Sequence[Message],
        documents: Sequence[Document],
    ) -> str:
        ...


class ModelProcessingTimeout(TimeoutError):
    """Typed, privacy-safe timeout raised by an LLM provider adapter."""

    def __init__(
        self,
        *,
        provider_class: str,
        provider: str,
        model: str,
        timeout_seconds: float | None,
        elapsed_seconds: float,
    ) -> None:
        normalized_class = provider_class.strip().lower()
        if normalized_class not in {"local", "external"}:
            raise ValueError("provider_class must be 'local' or 'external'.")
        self.provider_class = normalized_class
        self.provider = provider.strip() or "unknown"
        self.model = model.strip() or "unknown"
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = max(0.0, elapsed_seconds)
        self.code = f"{normalized_class}_model_timeout"
        super().__init__(f"Timeout on {normalized_class} model.")


def read_positive_finite_env_seconds(name: str, default: float) -> float:
    """Read a positive finite seconds value or fail with a clear configuration error."""

    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a finite number greater than zero; got {raw_value!r}.") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number greater than zero; got {raw_value!r}.")
    return value


def elapsed_seconds(started_at: float) -> float:
    return max(0.0, time.monotonic() - started_at)


def should_log_llm_io() -> bool:
    value = os.getenv("LOCAL_LLM_IO_LOGGING", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def log_llm_request(
    logger: logging.Logger,
    *,
    provider: str,
    agent_name: str,
    request_payload: Sequence[dict[str, Any]],
) -> None:
    if not should_log_llm_io():
        return
    logger.info(
        "LLM request | provider=%s | agent=%s | payload=%s",
        provider,
        agent_name,
        json.dumps(list(request_payload), ensure_ascii=False),
    )


def log_llm_response(
    logger: logging.Logger,
    *,
    provider: str,
    agent_name: str,
    raw_response: str,
) -> None:
    if not should_log_llm_io():
        return
    logger.info(
        "LLM raw response | provider=%s | agent=%s | content=%s",
        provider,
        agent_name,
        raw_response,
    )
