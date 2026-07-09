"""Minimal guardrail for issue #503 live document preview behavior.

This fast check verifies that the frontend keeps the live assistant response
aligned with the hydrated case-history path and that the browser E2E fixture is
present. It does not replace the Playwright regression test.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSISTANT_WORKSPACE = REPO_ROOT / "frontend" / "aijurisdictionfronend" / "src" / "pages" / "AssistantWorkspace.tsx"
E2E_SPEC = (
    REPO_ROOT
    / "frontend"
    / "aijurisdictionfronend"
    / "e2e"
    / "assistant-live-document-preview.spec.ts"
)


def main() -> None:
    workspace_source = ASSISTANT_WORKSPACE.read_text(encoding="utf-8")
    e2e_source = E2E_SPEC.read_text(encoding="utf-8")
    required_workspace_markers = [
        "shouldPreferHydratedAssistantMessage",
        "progressOnlyAssistantPattern",
        "findLatestAssistantInteraction",
        "appendGeneratedDocumentsResponseBlock",
    ]
    required_e2e_markers = [
        "Teraz vytvorim PDF dokument. Chvilu prosim.",
        "assistant live response keeps formatted document preview",
        "splnomocnenie_issue_503.pdf",
        "JurisDigta MCP searchLaws",
    ]

    missing = [
        marker for marker in required_workspace_markers if marker not in workspace_source
    ] + [marker for marker in required_e2e_markers if marker not in e2e_source]

    if missing:
        raise SystemExit(f"Issue #503 live document preview guardrails are incomplete: {missing}")

    print("Issue #503 live document preview guardrails are present.")
    print(f"Frontend: {ASSISTANT_WORKSPACE.relative_to(REPO_ROOT)}")
    print(f"E2E: {E2E_SPEC.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
