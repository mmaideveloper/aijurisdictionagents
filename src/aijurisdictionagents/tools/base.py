from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    purpose: str
    input_fields: tuple[str, ...]
    requires_explicit_user_confirmation: bool = True


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    ok: bool
    records: tuple[dict[str, Any], ...]
    message: str = ""


class Tool(Protocol):
    @property
    def definition(self) -> ToolDefinition:
        ...

    def run(self, **kwargs: Any) -> ToolResult:
        ...
