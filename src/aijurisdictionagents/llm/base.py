from __future__ import annotations

import json
import logging
import os
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
