from __future__ import annotations

from typing import Sequence

from ..tools.base import ToolDefinition


def render_tooling_prompt(
    *,
    tool_definitions: Sequence[ToolDefinition],
    jurisdiction_hint: str,
) -> str:
    if not tool_definitions:
        return (
            "TOOLING\n"
            "- No external verification tools are currently available.\n"
            "- Continue with manual intake and ask for missing evidence from the user."
        )

    lines: list[str] = [
        "TOOLING (dynamic checks)",
        f"- Jurisdiction hint: {jurisdiction_hint}",
        "- Before drafting contracts or formal filings, detect whether available tools can verify critical facts.",
        "- Never execute any verification automatically. First ask the user for explicit consent.",
        "- If a tool returns invalid/missing data, show the mismatch and ask the user to correct or update details.",
        "- If additional tools are added later (car verification, person address, sanctions/person screening), choose the most relevant checks based on the user request.",
        "- Available tools:",
    ]
    for tool in tool_definitions:
        fields = ", ".join(tool.input_fields)
        consent = "yes" if tool.requires_explicit_user_confirmation else "no"
        lines.append(
            f"  - {tool.name}: {tool.purpose} | required_input=[{fields}] | explicit_user_confirmation_required={consent}"
        )
    return "\n".join(lines)
