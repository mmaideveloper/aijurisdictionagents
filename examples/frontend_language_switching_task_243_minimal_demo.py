"""Minimal runnable verification for frontend task #243 language switching.

Run:
    python examples/frontend_language_switching_task_243_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "aijurisdictionfronend" / "src"

LANGUAGE_PROVIDER_PATH = FRONTEND_ROOT / "components" / "LanguageProvider.tsx"
HOME_PATH = FRONTEND_ROOT / "pages" / "Home.tsx"
SIDEBAR_PATH = FRONTEND_ROOT / "components" / "Sidebar.tsx"
CASE_PROVIDER_PATH = FRONTEND_ROOT / "state" / "CaseProvider.tsx"


def _require_contains(path: Path, token: str, message: str) -> None:
    content = path.read_text(encoding="utf-8")
    if token not in content:
        raise AssertionError(f"{message}\nMissing token: {token}\nChecked file: {path}")


if __name__ == "__main__":
    _require_contains(
        LANGUAGE_PROVIDER_PATH,
        'const storageKey = "aj_frontend_lang";',
        "Language provider must persist the selected language in localStorage.",
    )
    _require_contains(
        HOME_PATH,
        't("workspaceWelcomeBack"',
        "Signed-in workspace header must use translated language-aware copy.",
    )
    _require_contains(
        SIDEBAR_PATH,
        't("sidebarCasesTitle")',
        "Sidebar labels must be translated through the language provider.",
    )
    _require_contains(
        CASE_PROVIDER_PATH,
        "localizeCaseRecord",
        "Case provider must re-localize mock workspace content when language changes.",
    )
    _require_contains(
        CASE_PROVIDER_PATH,
        "createChatSession({ language })",
        "New chat sessions must inherit the selected frontend language.",
    )

    print("Frontend task #243 language switching minimal demo checks passed.")
