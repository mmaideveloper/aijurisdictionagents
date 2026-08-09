# Issue 608 E2E evidence

`issue-608-mcp-case-citation-final.png` is the final-state screenshot produced by:

```powershell
cd frontend/aijurisdictionfronend
.\node_modules\.bin\playwright.cmd test e2e/issue-608-mcp-case-citations.spec.ts
```

The scenario uses only synthetic `.example.test` identity, case, prompt, answer, and citation data. It verifies that a structured source returned through the JurisDigta MCP citation contract is visible both beneath the assistant answer and in the case-level Citations panel. The committed screenshot is retained as issue/PR acceptance evidence; transient traces and local results under `runs/` follow the retention rules in `docs/E2E_TEST_EVIDENCE_RULE.md`.
