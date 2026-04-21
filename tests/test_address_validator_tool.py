from __future__ import annotations

from aijurisdictionagents.tools.address_validator import RegisterAdriesAddressValidatorTool


def test_registeradries_address_validator_tool_maps_address() -> None:
    tool = RegisterAdriesAddressValidatorTool()

    result = tool.run(address_text="Námestie slobody 1, 811 06 Bratislava")

    assert result.ok is True
    assert result.records
    record = result.records[0]
    mapping = record["mapping"]
    assert mapping["city"] == "Bratislava"
    assert mapping["kraj"] == "Bratislavský kraj"
    assert mapping["okres"] == "Bratislava"
    assert "registeradries.sk" in record["lookup_url"]


def test_registeradries_address_validator_tool_requires_input() -> None:
    tool = RegisterAdriesAddressValidatorTool()

    result = tool.run(address_text="")

    assert result.ok is False
    assert "required" in result.message
