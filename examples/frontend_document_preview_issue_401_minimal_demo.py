"""Minimal sanity check for issue #401 document preview formatting coverage.

This does not replace the Playwright E2E test. It gives a fast local check that
the frontend parser and E2E fixture keep the JurisDigta document-preview
contract for assistant drafts that contain internal audience labels.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSISTANT_WORKSPACE = REPO_ROOT / "frontend" / "aijurisdictionfronend" / "src" / "pages" / "AssistantWorkspace.tsx"
E2E_SPEC = (
    REPO_ROOT
    / "api"
    / "aijuristiction-api"
    / "e2e-playwright"
    / "tests"
    / "frontend-document-preview-formatting.spec.ts"
)


def main() -> None:
    workspace_source = ASSISTANT_WORKSPACE.read_text(encoding="utf-8")
    e2e_source = E2E_SPEC.read_text(encoding="utf-8")
    required_workspace_markers = [
        "internalAudienceLabelPattern",
        "assistantAgentPrefixPattern",
        "documentTitlePattern",
        "JurisDigta",
    ]
    required_e2e_markers = [
        "USERT-FACING",
        "LawyerSlovakia",
        "assistant legal draft renders as formatted JurisDigta document preview",
        "assistant-document-preview__sheet",
    ]

    missing = [
        marker
        for marker in required_workspace_markers
        if marker not in workspace_source
    ] + [marker for marker in required_e2e_markers if marker not in e2e_source]

    if missing:
        raise SystemExit(f"Document preview issue #401 guardrails are incomplete: {missing}")

    print("Issue #401 document preview guardrails are present.")
    print(f"Parser: {ASSISTANT_WORKSPACE.relative_to(REPO_ROOT)}")
    print(f"E2E: {E2E_SPEC.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
