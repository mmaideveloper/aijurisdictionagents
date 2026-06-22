"""Minimal demo for internal MCP law context injection."""

from __future__ import annotations

from app.chat.mcp_law_context import build_mcp_law_context


def main() -> None:
    context = build_mcp_law_context(
        query="Co hovori zakon 40/1964 o kupnej zmluve?",
        country="SK",
        language="sk-SK",
    )
    if context is None:
        print("No MCP law context required.")
        return
    print(context.prompt_note[:1200])


if __name__ == "__main__":
    main()
