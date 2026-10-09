# Issue #864: real generic LangGraph audit acceptance

This test creates a synthetic case in the real web frontend, asks an explanatory legal question
that must take the generic route, and opens **Celkový audit**. Success requires an actual pinned
`primary_router@1` graph containing `route_generic`, completed Azure model calls, completed MCP
calls, and the expected synthetic citation in persisted chat history. No browser interception,
fabricated identity, mock model or production case data is accepted.

## Prerequisites and preparation

Use the task worktree and its activated `conda` runtime. Pull the verified `codex-agent` profile
with `scripts/sync_env_profile.ps1` before implementation/runtime configuration. Never print `.env`.
Docker Desktop must be healthy, with a local PostgreSQL instance on loopback port 5432 using the
repository's synthetic local `postgres` credentials. The two databases below are dedicated to this
task, not development or production customer databases. Runtime storage stays under
`runs/storage/api/postgres/data` using the repository PostgreSQL launcher.

```powershell
.\skills\start-postgres\scripts\start_postgres.ps1 -DatabaseName issue_864_e2e -DatabasePort 5432 -SkipSchemaUpdate
.\conda\python.exe scripts/prepare_issue_864_langgraph_audit_e2e.py --setup
```

Setup creates only `issue_864_e2e` and `laws_issue_864_e2e` and applies current API/laws migrations.
Before importing model credentials, set the existing `DB_OPTION`/`DB_CLOUD` process variables to
this loopback API database. Import the currently approved E2E credential only through
`scripts/import_e2e_model_credentials_from_server.ps1` when it is absent from the verified local
profile. Then run the mandatory encrypted bootstrap. Choose `--required-model` to match the
approved `E2E_AZURE_FOUNDRY_DEPLOYMENT` (`gpt-4o-mini` or `gpt-5-mini`); do not switch the deployment
merely to make the test pass. The bootstrap requires `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` and reads
only the existing `E2E_AZURE_FOUNDRY_*` credential settings from ignored `.env`.

```powershell
$env:DB_OPTION = 'postgres'
$env:DB_CLOUD = 'postgresql://postgres:postgres@127.0.0.1:5432/issue_864_e2e'
# Example only when gpt-5-mini is the approved E2E deployment:
.\conda\python.exe scripts/bootstrap_e2e_model_credentials.py --required-model gpt-5-mini --verify-model
.\conda\python.exe scripts/prepare_issue_864_langgraph_audit_e2e.py
```

Preparation seeds the deterministic synthetic law fixture from the existing #635 seed helper into
the task laws database, adds the identifier metadata required by MCP search and a source artifact,
and provisions synthetic accounts only. It validates the configured real
chat model route and writes a unique run ID and sanitized input manifest under ignored `runs/e2e/`.
It does not create a case: the browser must do that through the UI. No new environment variable
is introduced. Existing `JURISDIGTA_E2E_TEST_USER_PASSWORD` is used internally without printing it.
Preparation pins the synthetic paid plan's `default` and `chat_reply` route policies in the isolated
task database to the approved E2E deployment, requires EU routing and disables local fallback.
This avoids selecting an unconfigured catalog profile and does not change production policies.

## Start and run

In one terminal, start the branch-local services:

```powershell
.\conda\python.exe scripts/run_issue_864_e2e_services.py
```

The launcher uses API `127.0.0.1:8264`, MCP `127.0.0.1:8364`, the two task databases and the approved
real Azure Foundry deployment. It fails on occupied ports, missing model credentials or failed
service health.
The health deadline is ten minutes because first-start workflow assignment initialization can take
longer than three minutes even when PostgreSQL is healthy.
This scenario does not invoke document generation, email delivery or background ingestion, so their
workers are not acceptance prerequisites. Sign-in OTP is read only from the
synthetic local outbox; no real email is sent by this test.

In a second terminal:

```powershell
.\conda\python.exe scripts/prepare_issue_864_langgraph_audit_e2e.py --authenticate
cd frontend/aijurisdictionfronend
npm ci --prefer-offline --no-audit --no-fund
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8264'
$env:VITE_API_KEY = 'aijuris'
npx playwright test e2e/issue-864-generic-audit.spec.ts --project chromium
```

Authentication uses real API-issued device tokens for the synthetic user and administrator.
Private login material is stored separately in ignored `runs/e2e/issue864/private-auth.json`, never
in the sanitized evidence. Tracing/video are disabled because network traces can contain tokens.
The test checks direct API source retrieval, actual generic routing, pinned observed graph nodes,
completed real-model/MCP calls, persisted synthetic citations and authorized audit/export access.
It must fail rather than treat a dedicated route, model mismatch or missing citation as acceptance.
The question explains legal citation notation, avoiding keywords that select a document-generation
flow. The browser waits for initial case hydration before sending; case citations are read from the
history response's complete citation collection rather than its paginated message list.

## Evidence and cleanup

Successful evidence lives in the unique directory printed by preparation:

- `full-audit-langgraph.png`: stable full-page screenshot of the graph, ordered executions and
  service timeline in the same admin view. Protected detail panels stay collapsed.
- `result-manifest.json`: actual provider/model routes, local services, synthetic run/case/correlation
  IDs, topology digest, observed nodes and expected/observed source IDs. No prompt/token is saved.
- `input-manifest.json`: sanitized synthetic scenario metadata.

The test deletes its case and removes private login material in `finally`. After stopping the API
and MCP launcher with Ctrl+C, remove the two task-only databases to purge their synthetic accounts,
outbox, debug events, seeds and encrypted test credential. Connect to the local maintenance
`postgres` database and drop exactly `issue_864_e2e` and `laws_issue_864_e2e`; never use a production
connection or wildcard database cleanup. Delete transient evidence and service logs within seven
days per `docs/E2E_TEST_EVIDENCE_RULE.md`. A failed run without a case still requires removal of
task databases and any private authentication file. Keep no full protected diagnostic ZIP.

## Validation status for the implementation session

Real E2E **passed on 2026-10-09** after the user restarted Docker Desktop. PostgreSQL recovery
completed normally; no Docker repair/reset was needed. The Chromium test passed in 57.1 seconds
against branch-local frontend/API/MCP and migrated isolated PostgreSQL databases, using two real
Azure Foundry `gpt-5-mini` completions. The persisted source was `issue-635-civil-code`, matching
the synthetic seed. Observed nodes were `minimize_verified_context`, `classify_registered_flows`,
`route_generic` and `__end__` with pinned topology.

Ignored evidence directory:
`runs/e2e/issue-864-langgraph-audit/issue-864-langgraph-audit-20261009T061702Z-fbcfdb6c/`.
It contains the visually reviewed `full-audit-langgraph.png` and sanitized `result-manifest.json`.
Correlation: `130a06e3-7d6e-42c4-a5cf-b42d9e0f3597`. Retain evidence for at most seven days
(delete by 2026-10-16). This validates the local implementation; it is not production deployment
evidence and does not reconstruct snapshots absent from an older production run.

The browser deleted its case and private authentication file; branch-local API/MCP processes were
stopped. Final removal of the two isolated databases and their runtime files is pending: automatic
approval review rejected the cleanup command as blocked by policy, without a more specific reason.
No alternate deletion mechanism was used. Remove these exact task databases/files using the cleanup
procedure above; they contain synthetic accounts/outbox/debug data and the encrypted E2E credential.

Before merging, integration with the newer audit-search UI was reviewed and revalidated on
2026-10-09. The test now uses **Open exact correlation**; the searchable filters and default
Full audit are both retained. API lint/type checks, the full API unit suite, primary-router tests,
11 frontend regressions, frontend build/lint and runnable examples passed. Real E2E passed again
(Chromium, 1.5 minutes), with visually reviewed screenshot/manifest under
`runs/e2e/issue-864-langgraph-audit/issue-864-langgraph-audit-20261009T150947Z-4ff6c4c0/`.
Correlation: `6057850b-71d8-4bfd-a955-afe3e6fbc2d4`; real model and expected source matched again.
