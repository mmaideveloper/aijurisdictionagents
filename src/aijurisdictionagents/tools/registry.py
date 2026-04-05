from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import Tool, ToolDefinition, ToolResult
from .obchodnyregister import ObchodnyRegisterTool


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
    }
    return ToolRegistry(_tools=tools)
