from __future__ import annotations

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


def test_registry_exposes_slovakia_property_lv_lookup_tool() -> None:
    registry = build_default_tool_registry()

    assert registry.has_tool("slovakia_property_lv_lookup")
    result = registry.run("slovakia_property_lv_lookup", person_name="Ján Novák")

    assert result.ok is True
    assert result.records
