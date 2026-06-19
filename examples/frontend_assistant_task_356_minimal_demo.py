"""Minimal runnable verification for issue #356 assistant workspace.

Run:
    python examples/frontend_assistant_task_356_minimal_demo.py
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
        FRONTEND_ROOT / "package.json",
        '"@assistant-ui/react"',
        "Frontend must declare assistant-ui as the selected assistant UI foundation.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "App.tsx",
        'path="/app/assistant"',
        "Protected assistant route must be registered.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "pages" / "AssistantWorkspace.tsx",
        "AssistantRuntimeProvider",
        "Assistant workspace must use assistant-ui runtime primitives.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "pages" / "AssistantWorkspace.tsx",
        "assistantMandatoryMcpTitle",
        "Assistant UI must show mandatory JurisDigta MCP controls.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "data" / "translations.ts",
        "assistantApiAuthAccess",
        "Assistant deployment/access copy must be translated through language keys.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "auth" / "webAuth.tsx",
        "/v1/users/sign-in",
        "Web auth must use the existing API user sign-in endpoint.",
    )

    print("Frontend assistant issue #356 minimal demo checks passed.")
