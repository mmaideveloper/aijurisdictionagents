"""Minimal runnable verification for frontend task #242 mock case creation.

Run:
    python examples/frontend_case_creation_task_242_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SIDEBAR_PATH = (
    REPO_ROOT
    / "frontend"
    / "aijurisdictionfronend"
    / "src"
    / "components"
    / "Sidebar.tsx"
)
CASE_INTAKE_PATH = (
    REPO_ROOT
    / "frontend"
    / "aijurisdictionfronend"
    / "src"
    / "pages"
    / "CaseIntake.tsx"
)
PROFILE_PATH = (
    REPO_ROOT
    / "frontend"
    / "aijurisdictionfronend"
    / "src"
    / "pages"
    / "Profile.tsx"
)
CASE_PROVIDER_PATH = (
    REPO_ROOT
    / "frontend"
    / "aijurisdictionfronend"
    / "src"
    / "state"
    / "CaseProvider.tsx"
)


def _require_contains(path: Path, token: str, message: str) -> None:
    content = path.read_text(encoding="utf-8")
    if token not in content:
        raise AssertionError(f"{message}\nMissing token: {token}\nChecked file: {path}")


if __name__ == "__main__":
    _require_contains(
        SIDEBAR_PATH,
        'navigate("/app/case")',
        "Sidebar new-case action must route to the intake form.",
    )
    _require_contains(
        CASE_INTAKE_PATH,
        "createCase({",
        "Case intake form must create a mock case through provider state.",
    )
    _require_contains(
        CASE_INTAKE_PATH,
        'navigate("/app/assistant", { replace: true })',
        "Successful intake submission must open the assistant workspace.",
    )
    _require_contains(
        CASE_INTAKE_PATH,
        'const DEFAULT_CASE_JURISDICTION = "Slovensko";',
        "Case intake form must prepopulate the Slovak jurisdiction default.",
    )
    _require_contains(
        CASE_INTAKE_PATH,
        'const DEFAULT_OPPOSING_PARTY = "ziadna";',
        "Case intake form must prepopulate the requested opposing-party default.",
    )
    _require_contains(
        PROFILE_PATH,
        't("profileDocumentsTitle")',
        "Profile page must render the My Documents section.",
    )
    _require_contains(
        CASE_PROVIDER_PATH,
        'const CASE_STORAGE_KEY = "aijurisdictionfrontend.mock.cases.v1";',
        "Case provider must persist mock cases locally for task #242.",
    )

    print("Frontend task #242 minimal demo checks passed.")
