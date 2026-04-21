from __future__ import annotations

from typing import Any

from ..property_validation import AIPropertyValidatorAgent
from .base import ToolDefinition, ToolResult


class SlovakiaPropertyLVTool:
    """Build Slovak list-vlastnictva lookup and download plans."""

    def __init__(self, *, agent: AIPropertyValidatorAgent | None = None) -> None:
        self._agent = agent or AIPropertyValidatorAgent()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="slovakia_property_lv_lookup",
            purpose=(
                "Prepare the best LV retrieval workflow for Slovakia (by person name or LV number), "
                "including all-cadastral-unit search fallback and download guidance."
            ),
            input_fields=("person_name", "lv_number", "cadastral_unit", "municipality"),
            requires_explicit_user_confirmation=True,
        )

    def run(self, **kwargs: Any) -> ToolResult:
        result = self._agent.build_lv_lookup_plan(
            person_name=str(kwargs.get("person_name") or ""),
            lv_number=str(kwargs.get("lv_number") or ""),
            cadastral_unit=str(kwargs.get("cadastral_unit") or ""),
            municipality=str(kwargs.get("municipality") or ""),
        )
        if not result.get("ok"):
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=str(result.get("message") or "LV lookup planning failed."),
            )
        return ToolResult(
            tool_name=self.definition.name,
            ok=True,
            records=(result,),
            message=str(result.get("message") or "LV lookup plan prepared."),
        )
