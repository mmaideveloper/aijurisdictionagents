"""Minimal runnable verification for bounded profile case and document names.

Run:
    python examples/frontend_profile_long_text_minimal_demo.py
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
    profile = FRONTEND_ROOT / "src" / "pages" / "Profile.tsx"
    styles = FRONTEND_ROOT / "src" / "styles" / "app.css"
    tests = FRONTEND_ROOT / "src" / "__tests__" / "profilePage.test.tsx"

    _require_contains(profile, 'className="profile-text-toggle"', "Long text needs an explicit toggle.")
    _require_contains(profile, "aria-expanded={isExpanded}", "The toggle must expose its state.")
    _require_contains(
        styles,
        "grid-template-columns: minmax(0, 1fr) auto auto;",
        "Text and actions must remain bounded to the left panel.",
    )
    _require_contains(styles, "overflow-wrap: anywhere;", "Expanded text must wrap safely.")
    _require_contains(
        tests,
        "expands and collapses long case and document text",
        "The interaction must have regression coverage.",
    )

    print("Profile long-text layout minimal demo checks passed.")
