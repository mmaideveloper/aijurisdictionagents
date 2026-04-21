from __future__ import annotations

from typing import Any

from ..address_validation import AIAddressValidatorAgent
from .base import ToolDefinition, ToolResult


class RegisterAdriesAddressValidatorTool:
    """Map Slovak address-like text into registeradries.sk lookup fields."""

    def __init__(self, *, agent: AIAddressValidatorAgent | None = None) -> None:
        self._agent = agent or AIAddressValidatorAgent()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="registeradries_address_validate",
            purpose=(
                "Validate Slovak address candidates for registeradries.sk and map fields "
                "(kraj, okres, city, street, house_number, postal code)."
            ),
            input_fields=("address_text",),
            requires_explicit_user_confirmation=True,
        )

    def run(self, **kwargs: Any) -> ToolResult:
        address_text = str(kwargs.get("address_text") or "").strip()
        if not address_text:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message="address_text is required.",
            )

        result = self._agent.validate_from_text(address_text)
        if not result["ok"]:
            return ToolResult(
                tool_name=self.definition.name,
                ok=False,
                records=(),
                message=str(result.get("message") or "Address validation failed."),
            )

        return ToolResult(
            tool_name=self.definition.name,
            ok=True,
            records=(
                {
                    "address_text": address_text,
                    "mapping": result.get("mapping", {}),
                    "lookup_url": result.get("lookup_url", self._agent.base_lookup_url),
                },
            ),
            message=str(result.get("message") or "Address mapped."),
        )
