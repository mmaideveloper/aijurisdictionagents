"""Minimal runnable verification for issue #369 case-create assistant layout.

Run:
    python examples/frontend_case_create_layout_issue_369_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "aijurisdictionfronend"
E2E_SPEC = (
    REPO_ROOT
    / "api"
    / "aijuristiction-api"
    / "e2e-playwright"
    / "tests"
    / "frontend-case-create-layout.spec.ts"
)


def _require_contains(path: Path, token: str, message: str) -> None:
    content = path.read_text(encoding="utf-8")
    if token not in content:
        raise AssertionError(f"{message}\nMissing token: {token}\nChecked file: {path}")


if __name__ == "__main__":
    _require_contains(
        FRONTEND_ROOT / "src" / "pages" / "CaseIntake.tsx",
        'navigate("/app/assistant", { replace: true })',
        "Case creation must open the assistant workspace instead of the legacy home workspace.",
    )
    _require_contains(
        FRONTEND_ROOT / "src" / "App.tsx",
        'path="/app/chat"',
        "/app/chat must remain a protected compatibility alias.",
    )
    _require_contains(
        E2E_SPEC,
        "case-created-assistant-layout",
        "Playwright layout test must capture screenshot evidence after case creation.",
    )
    _require_contains(
        E2E_SPEC,
        "metrics.rail.right",
        "Playwright layout test must assert the left rail does not overlap the center column.",
    )
    _require_contains(
        E2E_SPEC,
        "metrics.scrollWidth",
        "Playwright layout test must assert there is no horizontal page overflow.",
    )

    print("Issue #369 case-create assistant layout minimal demo checks passed.")
