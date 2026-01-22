from __future__ import annotations

import os
from dataclasses import dataclass
import logging
from typing import Iterable, Sequence

from openai import AzureOpenAI

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
        if config.azure_ad_token:
            self._client = AzureOpenAI(
                azure_endpoint=config.endpoint,
                api_version=config.api_version,
                azure_ad_token=config.azure_ad_token,
            )
        else:
            self._client = AzureOpenAI(
                azure_endpoint=config.endpoint,
                api_version=config.api_version,
                api_key=config.api_key,
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

        response = self._client.chat.completions.create(
            model=self._config.deployment,
            temperature=self._config.temperature,
            messages=messages,
        )
        content = response.choices[0].message.content if response.choices else ""
        return (content or "").strip()


def load_azure_foundry_config_from_env() -> AzureFoundryConfig:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = (
        os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
        or os.getenv("OPENAI_API_VERSION", "").strip()
        or "2023-09-01-preview"
    )
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip() or None
    azure_ad_token = os.getenv("AZURE_OPENAI_AD_TOKEN", "").strip() or None

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
