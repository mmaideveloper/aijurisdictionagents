"""Bounded, execution-time model selection provenance without prompt content."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

from . import __version__
from .correlation import record_debug_event

if TYPE_CHECKING:
    from .api_db import AIModelRouteSelection

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,199}$")
_REASONS = {
    "Route policy selected external model routing.": "policy_external",
    "Route policy selected local model routing.": "policy_local",
    "Local model was requested for this task.": "local_requested",
    "User selected this assistant model profile for the current workflow.": "user_selected_profile",
    "No enabled route policy matched this task and plan.": "no_matching_policy",
    "External paid model routing requires user acknowledgement before use.": "external_ack_required",
    "External model is not marked EU data zone capable.": "eu_zone_required",
    "Selected model profile is not enabled or does not exist.": "selected_profile_unavailable",
    "User is not allowed to select assistant model profiles.": "selected_profile_forbidden",
    "Selected model profile id is required.": "selected_profile_missing",
    "Explicit speech route; no implicit fallback.": "explicit_speech_route",
    "Route policy requires local model routing but no enabled local model is configured.": "local_unavailable",
    "External routing is allowed but no enabled external model is configured.": "external_unavailable",
    "External model budget cap reached for this route policy; using configured local fallback.": "budget_local_fallback",
    "External model budget cap reached for this route policy and local budget fallback is disabled or unavailable.": "budget_exhausted",
}


def bounded_identifier(value: object) -> str | None:
    """Never accept narrative, unbounded objects or provider response bodies."""
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


def route_provenance(route: AIModelRouteSelection, requested_profile: str = "") -> dict[str, object]:
    policy, profile, provider = route.policy, route.model_profile, route.provider
    policy_snapshot = None if policy is None else {
        "policy_id": bounded_identifier(policy.policy_id),
        "task_type": bounded_identifier(policy.task_type),
        "plan_code": bounded_identifier(policy.plan_code),
        "external_profile": bounded_identifier(policy.preferred_external_model_profile_id),
        "local_profile": bounded_identifier(policy.preferred_local_model_profile_id),
        "allow_external": policy.allow_external,
        "require_external_ack": policy.require_external_ack,
        "require_eu_data_zone": policy.require_eu_data_zone,
        "fallback_local_on_error": policy.fallback_local_on_error,
        "fallback_local_on_budget": policy.fallback_local_on_budget,
        "max_cost_eur": policy.max_cost_eur,
        "priority": policy.priority,
        "updated_at": policy.updated_at,
    }
    reason = _REASONS.get(route.reason, "selection_reason_unavailable")
    if route.reason.startswith("Admin per-user model override ") and route.reason.endswith(" selected this model."):
        reason = "admin_user_override"
    return {
        "schema_version": 1, "core_version": __version__,
        "task_type": bounded_identifier(route.task_type),
        "route_type": bounded_identifier(route.route_type), "reason_code": reason,
        "requested_model_profile_id": bounded_identifier(requested_profile),
        "provider_id": bounded_identifier(provider.provider_id) if provider else None,
        "provider_api_version": bounded_identifier(provider.api_version) if provider else None,
        "model_profile_id": bounded_identifier(profile.model_profile_id) if profile else None,
        "model_alias": bounded_identifier(profile.model_code) if profile else None,
        "deployment_name": bounded_identifier(profile.deployment_name) if profile else None,
        "policy_id": bounded_identifier(policy.policy_id) if policy else None,
        "policy_snapshot": policy_snapshot,
        "policy_digest": hashlib.sha256(json.dumps(policy_snapshot, sort_keys=True).encode()).hexdigest()
        if policy_snapshot else None,
        "model_revision_status": "awaiting_provider_response",
        "prompt_template_status": "not_recorded",
    }


def record_route_provenance(route: AIModelRouteSelection, requested_profile: str = "") -> None:
    record_debug_event("model_router", "route_selected", "observed", route_provenance(route, requested_profile))
