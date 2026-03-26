"""Minimal runnable verification for frontend task #211 navbar/profile changes.

Run:
    python examples/frontend_navbar_task_211_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NAVIGATION_PATH = (
    REPO_ROOT
    / "frontend"
    / "aijurisdictionfronend"
    / "src"
    / "components"
    / "Navigation.tsx"
)
PAGE_LAYOUT_PATH = (
    REPO_ROOT
    / "frontend"
    / "aijurisdictionfronend"
    / "src"
    / "components"
    / "PageLayout.tsx"
)


def _require_contains(path: Path, token: str, message: str) -> None:
    content = path.read_text(encoding="utf-8")
    if token not in content:
        raise AssertionError(f"{message}\nMissing token: {token}\nChecked file: {path}")


if __name__ == "__main__":
    _require_contains(
        NAVIGATION_PATH,
        'navigate("/")',
        "My Cases action must route to homepage.",
    )
    _require_contains(
        NAVIGATION_PATH,
        "const showBrand = !isAuthenticated || pathname !== \"/\" || isSidebarCollapsed;",
        "Navbar branding logic must include signed-in non-home and collapsed-sidebar homepage cases.",
    )
    _require_contains(
        PAGE_LAYOUT_PATH,
        "<Navigation isSidebarCollapsed={!sidebarOpen} />",
        "PageLayout must pass sidebar collapse state into Navigation for homepage behavior.",
    )

    print("Frontend task #211 minimal demo checks passed.")
