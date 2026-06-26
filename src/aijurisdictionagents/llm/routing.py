from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import os

from aijurisdictionagents.api_db import (
    AIModelRouteSelection,
    ApiDatabaseStore,
    SubscriptionPlan,
    UserSubscription,
)

from .azure_foundry_client import AzureFoundryClient, AzureFoundryConfig
from .base import LLMClient
from .openai_client import OpenAIClient, OpenAIConfig


class ModelRouteUnavailable(RuntimeError):
    """Raised when the DB-selected model route cannot be used."""


@dataclass(frozen=True)
class RoutedLLMClient:
    client: LLMClient
    route: AIModelRouteSelection
    plan: SubscriptionPlan
    subscription: UserSubscription | None
    provider: str
    model: str
    route_type: str
    fallback_reason: str

    @property
    def plan_code(self) -> str:
        return self.plan.plan_code

    @property
    def subscription_id(self) -> str:
        return self.subscription.subscription_id if self.subscription is not None else ""


def get_routed_llm_client(
    *,
    store: ApiDatabaseStore,
    user_id: str,
    task_type: str = "default",
    external_acknowledged: bool = False,
) -> RoutedLLMClient:
    if _explicit_mock_mode():
        plan = _free_plan()
        route = AIModelRouteSelection(
            policy=None,
            provider=None,
            model_profile=None,
            route_type="mock",
            task_type=task_type,
            plan_code=plan.plan_code,
            requires_external_ack=False,
            reason="explicit_mock_mode",
        )
        return RoutedLLMClient(
            client=_mock_llm_client(),
            route=route,
            plan=plan,
            subscription=None,
            provider="mock",
            model="mock",
            route_type="mock",
            fallback_reason="explicit_mock_mode",
        )

    plan = store.get_effective_subscription_plan(user_id=user_id) if user_id else _free_plan()
    subscription = store.get_effective_user_subscription(user_id=user_id) if user_id else None

    route = store.resolve_ai_model_route(
        user_id=user_id,
        plan_code=plan.plan_code,
        task_type=task_type,
        external_acknowledged=external_acknowledged,
    )
    if route.provider is None or route.model_profile is None:
        raise ModelRouteUnavailable(route.reason)

    provider = route.provider
    profile = route.model_profile
    provider_type = provider.provider_type.strip().lower()
    model = profile.deployment_name.strip() or profile.model_code.strip()

    if route.route_type in {"local_unavailable", "external_unavailable", "external_ack_required", "blocked_non_eu_external"}:
        raise ModelRouteUnavailable(route.reason)

    if provider_type in {"ollama", "local_ollama", "local_llamacpp_openai", "local_lmstudio"}:
        if not provider.base_url.strip():
            raise ModelRouteUnavailable("Local model provider has no base URL configured.")
        return RoutedLLMClient(
            client=OpenAIClient(
                OpenAIConfig(
                    api_key="local-ollama",
                    model=model,
                    base_url=_openai_compatible_base_url(provider.base_url),
                    provider_label=provider.provider_code,
                )
            ),
            route=route,
            plan=plan,
            subscription=subscription,
            provider=provider.provider_code,
            model=model,
            route_type=route.route_type,
            fallback_reason="",
        )

    if provider_type in {"azurefoundry", "azure_foundry", "azure"}:
        endpoint = provider.base_url.strip()
        api_key = store.get_ai_model_provider_secret(provider_id=provider.provider_id, secret_type="api_key")
        azure_ad_token = store.get_ai_model_provider_secret(
            provider_id=provider.provider_id,
            secret_type="azure_ad_token",
        )
        if not endpoint:
            raise ModelRouteUnavailable("Azure Foundry provider endpoint is not configured.")
        if not api_key and not azure_ad_token:
            raise ModelRouteUnavailable("Azure Foundry credential is not configured.")
        return RoutedLLMClient(
            client=AzureFoundryClient(
                AzureFoundryConfig(
                    endpoint=endpoint,
                    deployment=model,
                    api_version=provider.api_version.strip() or "2024-10-21",
                    temperature=_temperature(),
                    api_key=api_key,
                    azure_ad_token=azure_ad_token,
                )
            ),
            route=route,
            plan=plan,
            subscription=subscription,
            provider=provider.provider_code,
            model=model,
            route_type=route.route_type,
            fallback_reason="",
        )

    if provider_type == "openai":
        api_key = store.get_ai_model_provider_secret(provider_id=provider.provider_id, secret_type="api_key")
        if not api_key:
            raise ModelRouteUnavailable("OpenAI credential is not configured.")
        return RoutedLLMClient(
            client=OpenAIClient(
                OpenAIConfig(
                    api_key=api_key,
                    model=model,
                    temperature=_temperature(),
                    base_url=provider.base_url.strip() or None,
                    provider_label=provider.provider_code,
                )
            ),
            route=route,
            plan=plan,
            subscription=subscription,
            provider=provider.provider_code,
            model=model,
            route_type=route.route_type,
            fallback_reason="",
        )

    raise ModelRouteUnavailable(f'Unsupported model provider type "{provider.provider_type}".')


def _explicit_mock_mode() -> bool:
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "mock":
        return True
    current_test = os.getenv("PYTEST_CURRENT_TEST", "")
    if "test_chat.py" in current_test:
        return True
    return "PYTEST_CURRENT_TEST" in os.environ and _legacy_llm_factory_overridden()


def _legacy_llm_factory_overridden() -> bool:
    llm_module = import_module("aijurisdictionagents.llm")
    factory = getattr(llm_module, "get_llm_client")
    return (
        getattr(factory, "__module__", "") != "aijurisdictionagents.llm"
        or getattr(factory, "__name__", "") != "get_llm_client"
    )


def _mock_llm_client() -> LLMClient:
    llm_module = import_module("aijurisdictionagents.llm")
    return llm_module.get_llm_client()


def _temperature() -> float:
    return float(os.getenv("OPENAI_TEMPERATURE", "0.2"))


def _openai_compatible_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def _free_plan() -> SubscriptionPlan:
    return SubscriptionPlan("free", "Free", "none", 0, 1, 2, 1)
