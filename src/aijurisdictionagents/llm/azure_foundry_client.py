from __future__ import annotations

import os
from dataclasses import dataclass
import logging
import ssl
import time
from typing import Iterable, Sequence

import httpx
from openai import APITimeoutError, AzureOpenAI
import truststore

from .base import ModelProcessingTimeout, elapsed_seconds, log_llm_request, log_llm_response
from ..schemas import Document, Message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AzureFoundryConfig:
    endpoint: str
    deployment: str
    api_version: str
    temperature: float
    api_key: str | None
    azure_ad_token: str | None


class AzureFoundryClient:
    def __init__(self, config: AzureFoundryConfig) -> None:
        self._config = config
        _clear_blank_azure_openai_auth_env()
        http_client = _build_system_trust_http_client()
        client_kwargs = _build_azure_client_kwargs(config)
        if config.azure_ad_token:
            self._client = AzureOpenAI(
                **client_kwargs,
                azure_ad_token=config.azure_ad_token,
                http_client=http_client,
            )
        else:
            self._client = AzureOpenAI(
                **client_kwargs,
                api_key=config.api_key,
                http_client=http_client,
            )

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
                    "role": _to_openai_role(message.role),
                    "content": f"{message.agent_name}: {message.content}",
                }
            )

        log_llm_request(
            logger,
            provider="azurefoundry",
            agent_name=agent_name,
            request_payload=messages,
        )
        started_at = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=self._config.deployment,
                temperature=self._config.temperature,
                messages=messages,
            )
        except APITimeoutError as exc:
            raise ModelProcessingTimeout(
                provider_class="external",
                provider="azurefoundry",
                model=self._config.deployment,
                timeout_seconds=_client_timeout_seconds(self._client),
                elapsed_seconds=elapsed_seconds(started_at),
            ) from exc
        content = response.choices[0].message.content if response.choices else ""
        normalized = (content or "").strip()
        log_llm_response(
            logger,
            provider="azurefoundry",
            agent_name=agent_name,
            raw_response=normalized,
        )
        return normalized


def load_azure_foundry_config_from_env() -> AzureFoundryConfig:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = (
        os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
        or os.getenv("OPENAI_API_VERSION", "").strip()
        or "2023-09-01-preview"
    )
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    api_key = _optional_env("AZURE_OPENAI_API_KEY")
    azure_ad_token = _optional_env("AZURE_OPENAI_AD_TOKEN")

    if not endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT is required for LLM_PROVIDER=azurefoundry.")
    if not deployment:
        raise ValueError("AZURE_OPENAI_DEPLOYMENT is required for LLM_PROVIDER=azurefoundry.")
    if not api_key and not azure_ad_token:
        raise ValueError(
            "AZURE_OPENAI_API_KEY or AZURE_OPENAI_AD_TOKEN is required for LLM_PROVIDER=azurefoundry."
        )
    
    auth_method = "azure_ad_token" if azure_ad_token else "api_key"
    logger.info(
        "Azure Foundry config: auth_method=%s endpoint=%s deployment=%s api_version=%s temperature=%s",
        auth_method,
        endpoint,
        deployment,
        api_version,
        temperature,
    )

    return AzureFoundryConfig(
        endpoint=endpoint,
        deployment=deployment,
        api_version=api_version,
        temperature=temperature,
        api_key=api_key,
        azure_ad_token=azure_ad_token,
    )


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        # Remove empty values so downstream SDK env fallbacks do not treat them as credentials.
        os.environ.pop(name, None)
        return None
    return normalized


def _clear_blank_azure_openai_auth_env() -> None:
    _optional_env("AZURE_OPENAI_API_KEY")
    _optional_env("AZURE_OPENAI_AD_TOKEN")


def _build_azure_client_kwargs(config: AzureFoundryConfig) -> dict[str, str]:
    api_version = config.api_version.strip()
    if api_version.lower() in {"v1", "preview"}:
        return {
            "base_url": f"{config.endpoint.rstrip('/')}/openai/v1",
            "api_version": "preview",
        }
    return {
        "azure_endpoint": config.endpoint,
        "api_version": api_version,
    }


def _build_system_trust_http_client() -> httpx.Client:
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return httpx.Client(verify=context)


def _client_timeout_seconds(client: AzureOpenAI) -> float | None:
    timeout = getattr(client, "timeout", None)
    read_timeout = getattr(timeout, "read", None)
    return float(read_timeout) if isinstance(read_timeout, (int, float)) else None


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
