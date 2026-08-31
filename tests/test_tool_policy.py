from __future__ import annotations

import pytest

from aijurisdictionagents.orchestration.tool_policy import (
    ToolPolicyError,
    eligible_tool_definitions,
    validate_tool_policy,
)
from aijurisdictionagents.tools import build_default_tool_registry


@pytest.mark.parametrize(
    "tool_name",
    [
        "obchodny_register_company_check",
        "registeradries_address_validate",
        "slovakia_property_lv_lookup",
        "slovakia_car_validate",
        "dovera_debtor_check",
    ],
)
def test_registered_tools_can_be_constrained_by_an_immutable_flow_policy(
    tool_name: str,
) -> None:
    definitions = build_default_tool_registry().list_definitions()
    definition = next(item for item in definitions if item.name == tool_name)
    raw = {
        "schema_version": 1,
        "policy_id": "test.relevant-case.tools.v1",
        "tools": [
            {
                "name": tool_name,
                "purpose": "Synthetic relevant-case verification",
                "provider": "synthetic-public-provider",
                "consent_scope": f"synthetic.{tool_name}",
                "consent_text_version": "workflow-tool-consent-v1",
                "required_fact_keys": ["subject"],
                "input_mapping": {definition.input_fields[0]: "subject"},
                "permitted_data_fields": ["subject"],
                "jurisdictions": ["SK"],
                "timeout_seconds": 5,
            }
        ],
    }

    policies = validate_tool_policy(
        raw,
        registry_definitions=definitions,
        jurisdiction="SK",
        strict=True,
    )
    exposed = eligible_tool_definitions(
        policies,
        registry_definitions=definitions,
        verified_facts={"subject": "synthetic-value"},
    )

    assert [item["name"] for item in exposed] == [tool_name]
    assert "consent_scope" not in exposed[0]
    assert "synthetic-value" not in str(exposed)


def test_unregistered_tool_is_rejected_before_model_selection() -> None:
    with pytest.raises(ToolPolicyError, match="unregistered_tool_in_policy"):
        validate_tool_policy(
            {
                "schema_version": 1,
                "tools": [
                    {
                        "name": "unrestricted_shell",
                        "purpose": "unsafe",
                        "provider": "unknown",
                        "consent_scope": "unsafe",
                        "consent_text_version": "v1",
                        "required_fact_keys": ["subject"],
                        "input_mapping": {"command": "subject"},
                        "permitted_data_fields": ["subject"],
                        "jurisdictions": ["SK"],
                        "timeout_seconds": 5,
                    }
                ],
            },
            registry_definitions=build_default_tool_registry().list_definitions(),
            jurisdiction="SK",
            strict=True,
        )
