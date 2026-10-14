from __future__ import annotations

import pytest

from aijurisdictionagents.privacy import CONSENT_VERSION, PrivacyDenied

from aijurisdictionagents.property_validation import AIPropertyValidatorAgent
from aijurisdictionagents.tools.registry import build_default_tool_registry


def test_property_validator_person_name_defaults_to_all_cadastral_units() -> None:
    result = AIPropertyValidatorAgent().build_lv_lookup_plan(person_name="Ján Novák")

    assert result["ok"] is True
    plan = result["plan"]
    assert plan["mode"] == "person_name"
    assert plan["search_scope"] == "all_cadastral_units_slovakia"


def test_property_validator_lv_number_mode() -> None:
    result = AIPropertyValidatorAgent().build_lv_lookup_plan(
        lv_number="001234",
        cadastral_unit="Ružinov",
    )

    assert result["ok"] is True
    plan = result["plan"]
    assert plan["mode"] == "lv_number"
    assert plan["search_scope"] == "specified_cadastral_unit"


def test_property_validator_requires_person_or_lv() -> None:
    result = AIPropertyValidatorAgent().build_lv_lookup_plan()

    assert result["ok"] is False


def test_registry_exposes_slovakia_property_lv_lookup_tool(external_check_subject) -> None:
    registry = build_default_tool_registry()

    assert registry.has_tool("slovakia_property_lv_lookup")
    result = registry.run("slovakia_property_lv_lookup", person_name="Ján Novák")

    assert result.ok is True
    assert result.records


def test_default_registry_refuses_anonymous_external_checks() -> None:
    with pytest.raises(PrivacyDenied, match="authenticated_subject"):
        build_default_tool_registry().run("slovakia_property_lv_lookup", person_name="Synthetic Person")


def test_default_registry_rechecks_withdrawn_consent(external_check_subject) -> None:
    controls, user = external_check_subject
    registry = build_default_tool_registry()
    controls.consent(user.user_id, "external_checks", False, version=CONSENT_VERSION)
    with pytest.raises(PrivacyDenied, match="consent_required"):
        registry.run("slovakia_property_lv_lookup", person_name="Synthetic Person")
