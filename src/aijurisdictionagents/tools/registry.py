from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import Tool, ToolDefinition, ToolResult
from .address_validator import RegisterAdriesAddressValidatorTool
from .obchodnyregister import ObchodnyRegisterTool
from .property_validator import SlovakiaPropertyLVTool


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool]

    def list_definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition for tool in self._tools.values())

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def run(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                ok=False,
                records=(),
                message=f"Tool '{name}' is not registered.",
            )
        return tool.run(**kwargs)


def build_default_tool_registry() -> ToolRegistry:
    tools: dict[str, Tool] = {
        "obchodny_register_company_check": ObchodnyRegisterTool(),
        "registeradries_address_validate": RegisterAdriesAddressValidatorTool(),
        "slovakia_property_lv_lookup": SlovakiaPropertyLVTool(),
    }
    return ToolRegistry(_tools=tools)
