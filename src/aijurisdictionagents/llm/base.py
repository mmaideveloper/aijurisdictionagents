from __future__ import annotations

import hashlib
import json
import logging
import os
import re
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


def should_log_raw_llm_io() -> bool:
    value = os.getenv("LOCAL_LLM_IO_LOGGING_RAW", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _payload_hash(request_payload: Sequence[dict[str, Any]]) -> str:
    serialized = json.dumps(list(request_payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _redact_preview(text: str) -> str:
    redacted = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[REDACTED_EMAIL]", text)
    redacted = re.sub(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", "[REDACTED_IBAN]", redacted)
    redacted = re.sub(r"\b\d{6}/?\d{3,4}\b", "[REDACTED_BIRTH_ID]", redacted)
    redacted = re.sub(
        r"\b(?:meno|name|klient|client|address|adresa)\s*:\s*[^,\n]+",
        lambda match: match.group(0).split(":", maxsplit=1)[0] + ": [REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"\b(?:ul\.|ulica|street|st\.|avenue|ave\.|road|cesta|trieda|namestie|námestie)\b[^\n,;]{0,80}",
        "[REDACTED_ADDRESS]",
        redacted,
        flags=re.IGNORECASE,
    )
    compact = " ".join(redacted.split())
    return compact[:120]


def log_llm_request(
    logger: logging.Logger,
    *,
    provider: str,
    agent_name: str,
    request_payload: Sequence[dict[str, Any]],
    message_count: int,
    document_count: int,
) -> None:
    if not should_log_llm_io():
        return
    payload_json = json.dumps(list(request_payload), ensure_ascii=False)
    logger.info(
        (
            "LLM request | provider=%s | agent=%s | prompt_hash=%s | "
            "message_count=%s | document_count=%s | preview=%s"
        ),
        provider,
        agent_name,
        _payload_hash(request_payload),
        message_count,
        document_count,
        _redact_preview(payload_json),
    )
    if should_log_raw_llm_io():
        logger.info(
            "LLM raw request | provider=%s | agent=%s | payload=%s",
            provider,
            agent_name,
            payload_json,
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
        "LLM response | provider=%s | agent=%s | response_length=%s | preview=%s",
        provider,
        agent_name,
        len(raw_response),
        _redact_preview(raw_response),
    )
    if should_log_raw_llm_io():
        logger.info(
            "LLM raw response | provider=%s | agent=%s | content=%s",
            provider,
            agent_name,
            raw_response,
        )
