from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from aijurisdictionagents.tools.base import ToolDefinition


class ToolPolicyError(ValueError):
    """Raised when an immutable flow tool policy is unsafe or malformed."""


@dataclass(frozen=True)
class FlowToolPolicy:
    name: str
    purpose: str
    provider: str
    consent_scope: str
    consent_text_version: str
    required_fact_keys: tuple[str, ...]
    input_mapping: dict[str, str]
    permitted_data_fields: tuple[str, ...]
    jurisdictions: tuple[str, ...]
    timeout_seconds: float

    def public_definition(self, definition: ToolDefinition) -> dict[str, Any]:
        """Return only the definition the selector is permitted to see."""

        return {
            "name": self.name,
            "purpose": self.purpose,
            "provider": self.provider,
            "input_fields": list(definition.input_fields),
            "required_fact_keys": list(self.required_fact_keys),
        }


def validate_tool_policy(
    raw_policy: Any,
    *,
    registry_definitions: Sequence[ToolDefinition],
    jurisdiction: str,
    strict: bool,
) -> tuple[FlowToolPolicy, ...]:
    if raw_policy is None and not strict:
        return ()
    if not isinstance(raw_policy, Mapping):
        raise ToolPolicyError("invalid_tool_policy_schema")
    if raw_policy.get("schema_version") != 1:
        raise ToolPolicyError("unsupported_tool_policy_schema_version")
    raw_tools = raw_policy.get("tools")
    if not isinstance(raw_tools, list):
        raise ToolPolicyError("invalid_tool_policy_tools")

    definitions = {item.name: item for item in registry_definitions}
    result: list[FlowToolPolicy] = []
    seen: set[str] = set()
    normalized_jurisdiction = jurisdiction.strip().upper()
    for raw_tool in raw_tools:
        if not isinstance(raw_tool, Mapping):
            raise ToolPolicyError("invalid_tool_policy_entry")
        name = _required_text(raw_tool, "name")
        if name in seen:
            raise ToolPolicyError("duplicate_tool_policy_entry")
        definition = definitions.get(name)
        if definition is None:
            raise ToolPolicyError("unregistered_tool_in_policy")
        purpose = _required_text(raw_tool, "purpose")
        provider = _required_text(raw_tool, "provider")
        consent_scope = _required_text(raw_tool, "consent_scope")
        consent_text_version = _required_text(raw_tool, "consent_text_version")
        required_fact_keys = _string_tuple(raw_tool, "required_fact_keys", allow_empty=False)
        permitted_data_fields = _string_tuple(
            raw_tool, "permitted_data_fields", allow_empty=False
        )
        jurisdictions = tuple(value.upper() for value in _string_tuple(
            raw_tool, "jurisdictions", allow_empty=False
        ))
        if normalized_jurisdiction not in jurisdictions:
            raise ToolPolicyError("tool_policy_jurisdiction_mismatch")
        raw_mapping = raw_tool.get("input_mapping")
        if not isinstance(raw_mapping, Mapping) or not raw_mapping:
            raise ToolPolicyError("invalid_tool_input_mapping")
        input_mapping = {
            str(input_name).strip(): str(fact_key).strip()
            for input_name, fact_key in raw_mapping.items()
            if str(input_name).strip() and str(fact_key).strip()
        }
        if set(input_mapping) - set(definition.input_fields):
            raise ToolPolicyError("tool_policy_maps_unknown_input")
        if set(input_mapping.values()) - set(required_fact_keys):
            raise ToolPolicyError("tool_policy_maps_unapproved_fact")
        if set(input_mapping.values()) - set(permitted_data_fields):
            raise ToolPolicyError("tool_policy_maps_unpermitted_data")
        try:
            timeout_seconds = float(raw_tool.get("timeout_seconds", 0))
        except (TypeError, ValueError) as exc:
            raise ToolPolicyError("invalid_tool_timeout") from exc
        if not 0 < timeout_seconds <= 30:
            raise ToolPolicyError("invalid_tool_timeout")
        result.append(
            FlowToolPolicy(
                name=name,
                purpose=purpose,
                provider=provider,
                consent_scope=consent_scope,
                consent_text_version=consent_text_version,
                required_fact_keys=required_fact_keys,
                input_mapping=input_mapping,
                permitted_data_fields=permitted_data_fields,
                jurisdictions=jurisdictions,
                timeout_seconds=timeout_seconds,
            )
        )
        seen.add(name)
    return tuple(result)


def eligible_tool_definitions(
    policies: Sequence[FlowToolPolicy],
    *,
    registry_definitions: Sequence[ToolDefinition],
    verified_facts: Mapping[str, str],
) -> tuple[dict[str, Any], ...]:
    definitions = {item.name: item for item in registry_definitions}
    return tuple(
        policy.public_definition(definitions[policy.name])
        for policy in policies
        if all(str(verified_facts.get(key, "")).strip() for key in policy.required_fact_keys)
    )


def get_tool_policy(
    policies: Sequence[FlowToolPolicy], tool_name: str
) -> FlowToolPolicy | None:
    return next((policy for policy in policies if policy.name == tool_name), None)


def build_tool_inputs(
    policy: FlowToolPolicy, verified_facts: Mapping[str, str]
) -> dict[str, str]:
    values = {
        input_name: str(verified_facts.get(fact_key, "")).strip()
        for input_name, fact_key in policy.input_mapping.items()
    }
    if any(not value for value in values.values()):
        raise ToolPolicyError("required_tool_input_missing")
    return values


def _required_text(value: Mapping[str, Any], key: str) -> str:
    result = str(value.get(key, "")).strip()
    if not result:
        raise ToolPolicyError(f"missing_tool_policy_{key}")
    return result


def _string_tuple(
    value: Mapping[str, Any], key: str, *, allow_empty: bool
) -> tuple[str, ...]:
    raw = value.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise ToolPolicyError(f"invalid_tool_policy_{key}")
    result = tuple(item.strip() for item in raw)
    if not allow_empty and not result:
        raise ToolPolicyError(f"invalid_tool_policy_{key}")
    return result
