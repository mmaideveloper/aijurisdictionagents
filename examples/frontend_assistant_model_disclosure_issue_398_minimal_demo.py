"""Minimal runnable verification for issue #398 assistant model disclosure.

Run:
    python examples/frontend_assistant_model_disclosure_issue_398_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "aijurisdictionfronend"


def _require_contains(path: Path, token: str, message: str) -> None:
    content = path.read_text(encoding="utf-8")
    if token not in content:
        raise AssertionError(f"{message}\nMissing token: {token}\nChecked file: {path}")


if __name__ == "__main__":
    _require_contains(
        FRONTEND_ROOT / "src" / "api" / "chatClient.ts",
        "VITE_CHAT_MODEL_LABEL",
        "Frontend chat runtime config must expose a public model label.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "pages" / "AssistantWorkspace.tsx",
        "assistant-model-disclosure",
        "Assistant workspace must render the chat model disclosure.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "data" / "translations.ts",
        "assistantModelDisclosureLabel",
        "Assistant model disclosure copy must be translated.",
    )
    _require_contains(
        FRONTEND_ROOT / ".env.example",
        "VITE_CHAT_MODEL_LABEL=Azure Foundry model",
        "Frontend env example must document the public model label.",
    )

    print("Frontend assistant model disclosure issue #398 minimal demo checks passed.")
