# Post-deployment tests

Run these tests only after all required build, lint, type-check, unit/integration, E2E,
and image checks have passed for the exact production commit. A post-deployment result never
overrides the production build gate. The self-managed production workflow runs the required
issue #646 and #647 Azure Foundry checks automatically after deployment and fails closed when
either one fails.

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

### MCP court decisions through Azure Foundry gpt-5-mini (#647)

The fixed Slovak question is:

> Zobraz 5 posledných súdnych rozhodnutí.

Run the opt-in check against the exact successfully deployed production SHA:

```powershell
.\scripts\run_issue_647_prod_mcp_court_decisions_e2e.ps1 `
  -DeployedCommitSha <40-character-production-commit-sha>
```

For PR evidence, add `-FinalScreenshotPath docs/screenshots/issue-647/issue-647-gpt-5-mini.png`.
The screenshot is still a failure artifact unless the manifest records `status=passed`; never infer
acceptance from the image alone.

The tracked pre-acceptance evidence
[`issue-647-gpt-5-mini-production-failed.png`](screenshots/issue-647/issue-647-gpt-5-mini-production-failed.png)
shows the superseded 2026-08-24 purchase-contract run selecting `azureFoundryEU / gpt-5-mini` but
returning no MCP citations and asking for clarification. It remains a failure artifact and must not
be presented as passing evidence for the simplified latest-five scenario.

The simplified run is captured in
[`issue-647-gpt-5-mini-latest-five-failed.png`](screenshots/issue-647/issue-647-gpt-5-mini-latest-five-failed.png).
Its direct OAuth MCP check returned exactly five metadata records, while the production chat route
reported that its internal MCP lookup was unavailable and rendered no citations. This screenshot is
also failure evidence, not final acceptance evidence. Keep the pull request in draft until the
frontend -> API -> MCP path renders the same five sources and the manifest records `status=passed`.

This scenario uses only the paid synthetic account pinned to Azure Foundry EU `gpt-5-mini`.
Qwen and mock routes are excluded, and any fallback fails the test. Direct authenticated MCP calls
must return exactly five `sort=latest` results with explicit date-quality metadata. For every
result, metadata-only `getCourtDecision` must return court, date, source link, and ECLI or file number
without text, snippet, or summary. The external route must reject `outputMode=internal_raw`.

The frontend answer must expose the same five MCP decision identities and citation metadata, treat
case law as supporting rather than binding statutory authority, disclose corpus coverage limits,
and retain the human-review safeguard. Generic web/`AIWebSearchAgent` fallback cannot satisfy the
contract. The test uses a disposable synthetic case and deletes it after the run where supported.
When any returned source date is invalid or missing, the answer must avoid an unqualified “latest”
claim and visibly disclose the date-ordering limitation.

Evidence is stored under ignored
`runs/e2e/issue-647-prod-mcp-court-decisions/<UTC timestamp>/` and retained for no more than seven
days. It includes one stable final-state screenshot and a sanitized manifest containing the deployed
SHA, requested/observed real-model route, direct MCP decision identifiers, observed citation
identifiers, latency, and pass/fail outcome. Decision bodies, credentials, prompts with personal
data, tokens, passwords, OTPs, connection strings, and customer records are prohibited.

## Minimal runnable example

The repository-wide minimal example remains:

```powershell
.\conda\python.exe examples\minimal_demo.py
```
