from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.security import require_api_key
from aijurisdictionagents.api_db import ApiDatabaseStore


router = APIRouter(
    prefix="/v1/model-routing",
    tags=["model-routing"],
    dependencies=[Depends(require_api_key)],
)


class EffectiveModelRouteResponse(BaseModel):
    plan_code: str
    route_type: str
    provider: str
    provider_display_name: str
    model: str
    model_profile_id: str
    is_local: bool
    is_external: bool
    label: str


def get_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


@router.get("/effective", response_model=EffectiveModelRouteResponse)
def get_effective_model_route(
    user_id: str | None = None,
    task_type: str = "chat_reply",
    store: ApiDatabaseStore = Depends(get_store),
) -> EffectiveModelRouteResponse:
    normalized_user_id = (user_id or "").strip()
    plan = (
        store.get_effective_subscription_plan(user_id=normalized_user_id)
        if normalized_user_id
        else store.get_subscription_plan(plan_code="free")
    )
    route = store.resolve_ai_model_route(
        user_id=normalized_user_id,
        plan_code=plan.plan_code,
        task_type=task_type.strip() or "chat_reply",
    )
    provider = route.provider
    profile = route.model_profile
    provider_code = provider.provider_code if provider is not None else ""
    model_code = profile.model_code if profile is not None else ""
    provider_name = provider.display_name if provider is not None else provider_code
    return EffectiveModelRouteResponse(
        plan_code=plan.plan_code,
        route_type=route.route_type,
        provider=provider_code,
        provider_display_name=provider_name,
        model=model_code,
        model_profile_id=profile.model_profile_id if profile is not None else "",
        is_local=bool(provider.is_local) if provider is not None else False,
        is_external=bool(provider.is_external) if provider is not None else False,
        label=_public_route_label(provider_name=provider_name, model_code=model_code, route_type=route.route_type),
    )


def _public_route_label(*, provider_name: str, model_code: str, route_type: str) -> str:
    if not provider_name and not model_code:
        return route_type or "Model routing"
    if not provider_name:
        return model_code
    if not model_code:
        return provider_name
    return f"{provider_name} - {model_code}"
