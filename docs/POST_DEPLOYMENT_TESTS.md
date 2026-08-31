# Post-deployment tests

## Release-gate test isolation

Focused API tests must patch attributes through pytest's `monkeypatch` fixture. They must not
replace application or third-party packages in `sys.modules`, because those process-wide
replacements can corrupt tests collected or executed later in the same CI process. The API
release gate always runs the complete suite in one process and remains fail-closed for the exact
deployment commit.

Run these tests only after all required build, lint, type-check, unit/integration, E2E,
and image checks have passed for the exact production commit. A post-deployment result never
overrides the production build gate. The self-managed production workflow runs the required
issue #646 Azure Foundry check automatically after deployment and fails closed when it fails.

## Required production checks

### MCP laws through Azure Foundry gpt-5-mini (#646)

The fixed question is:

> Podľa aktuálnych údajov z JurisDigta MCP stručne vysvetli, čo je obsahom právneho predpisu č. 192/2026 Z. z. Uveď jeho presný názov a odkaz na oficiálny zdroj. Výsledok je podklad na ľudskú právnu kontrolu.

Run from the repository root after the deployment workflow reports the successful production SHA:

```powershell
.\scripts\run_issue_646_prod_mcp_laws_e2e.ps1 `
  -DeployedCommitSha <40-character-production-commit-sha>
```

The runner reads `JURISDIGTA_E2E_TEST_USER_PASSWORD` from the process or ignored `.env` without
printing it. It refuses `unknown-variable` and never falls back to a mock. Production must have the
controlled MCP OAuth MFA bypass enabled for the approved paid synthetic account during the
explicit test window. Disable the bypass after testing according to `docs/MCP_SERVER.md`.

In `.github/workflows/self_managed_prod_deploy.yml`, the production self-hosted runner reads the
same password only from `/srv/jurisdigta/secrets/jurisdigta.env`, provisions the approved synthetic
accounts, pins the paid account to the enabled EU `gpt-5-mini` profile, and opens a 45-minute MCP
OAuth bypass window restricted to that paid account. An exit trap closes the window and recreates a healthy MCP container whether
the test passes, fails, is interrupted, or times out. Evidence is uploaded for seven days. A failed
post-deployment test marks the deployment workflow failed; it does not perform an automatic rollback.
Chromium runs in the pinned official `mcr.microsoft.com/playwright:v1.58.2-noble` container, so the
browser runtime stays deterministic even when the self-hosted runner OS is newer than Playwright's
directly supported host distributions.

The question is sent only through the paid synthetic account using Azure Foundry EU /
`gpt-5-mini`. Qwen is not part of the automatic post-deployment gate and is not invoked by this
scenario. It may be evaluated separately only through an explicitly requested manual test.

Questions that explicitly request the content of a legal act or statute are treated as legal
research and bypass document case-type detection. This prevents a law lookup from being diverted
into a document-template clarification workflow before the MCP law tools can run.
MCP citations are persisted before a streamed answer pauses for an optional follow-up reply, so a
model ending an otherwise complete legal answer with a question cannot discard source provenance.

The Azure assertion waits for the final assistant message and MCP citation for the configured
300-second timeout. It must not match the law identifier echoed in the user's own question.

The test does not require byte-identical prose. Real generative models can choose different wording.
The deterministic pass contract is instead:

- direct authenticated MCP `searchLaws` returns law `192/2026`;
- bounded `getLawText(offset=0, max_chars=4000)` returns non-empty source text;
- the frontend answer contains `192/2026`;
- the persisted case citation has the same MCP document/source identity or exact law identifier;
- `retrieval_tool` identifies JurisDigta MCP;
- no `web` citation or `AIWebSearchAgent` fallback is accepted;
- the model audit records the requested provider/model with no fallback route.

This makes the result repeatable while allowing harmless language variation. The legal answer should
remain materially stable until the official text/version of the fixed legal instrument changes. If it changes,
review the new MCP source/version and deliberately update the expected fixture; do not accept a drift
silently.

The API `/version` knowledge-cutoff fields are recorded in the manifest. When production has a
verified cutoff date, the 2026 law date also demonstrates that the answer needs post-cutoff retrieval.
When the cutoff is unavailable, the stronger operational proof is the matching direct MCP source,
persisted MCP citation, and explicit rejection of AIWebSearchAgent/web fallback.

Evidence is stored under ignored `runs/e2e/issue-646-prod-mcp-laws/<UTC timestamp>/` and includes:

- one screenshot for the Azure Foundry route showing the final answer and citation panel;
- one sanitized manifest containing the deployed SHA, API/MCP versions, question, requested and
  observed routes, MCP source identity, citation identity, answer hash/short preview, audit route,
  latency, and pass/fail result for the required route.

Delete the evidence within seven days. It must not contain credentials, tokens, OTP values,
connection strings, real customer data, or raw full law text.

## Minimal runnable example

The repository-wide minimal example remains:

```powershell
.\conda\python.exe examples\minimal_demo.py
```
