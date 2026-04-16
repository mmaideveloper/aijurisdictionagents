"""Minimal runnable verification for frontend task #245 chat window visuals.

Run:
    python examples/frontend_chat_window_visuals_task_245_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOME_PATH = REPO_ROOT / "frontend" / "aijurisdictionfronend" / "src" / "pages" / "Home.tsx"
CASE_PROVIDER_PATH = (
    REPO_ROOT / "frontend" / "aijurisdictionfronend" / "src" / "state" / "CaseProvider.tsx"
)


def _require_contains(path: Path, token: str, message: str) -> None:
    content = path.read_text(encoding="utf-8")
    if token not in content:
        raise AssertionError(f"{message}\nMissing token: {token}\nChecked file: {path}")


def _require_not_contains(path: Path, token: str, message: str) -> None:
    content = path.read_text(encoding="utf-8")
    if token in content:
        raise AssertionError(f"{message}\nUnexpected token: {token}\nChecked file: {path}")


if __name__ == "__main__":
    _require_contains(
        CASE_PROVIDER_PATH,
        "stripSeededAssistantIntro",
        "Case provider must strip the seeded assistant intro after the first user message.",
    )
    _require_contains(
        CASE_PROVIDER_PATH,
        "isUserInteractionActor(actor)",
        "First-message cleanup must be gated to real user-authored interactions.",
    )
    _require_not_contains(
        HOME_PATH,
        "workspace-callout",
        "Home workspace should no longer render the bottom recommendation card.",
    )
    _require_not_contains(
        HOME_PATH,
        't("workspaceNextRecommendedAction")',
        "Home workspace should no longer render the next recommended action label.",
    )

    print("Frontend task #245 chat window visuals minimal demo checks passed.")
