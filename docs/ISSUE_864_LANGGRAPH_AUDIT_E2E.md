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
the task laws database and provisions synthetic accounts only. It validates the configured real
chat model route and writes a unique run ID and sanitized input manifest under ignored `runs/e2e/`.
It does not create a case: the browser must do that through the UI. No new environment variable
is introduced. Existing `JURISDIGTA_E2E_TEST_USER_PASSWORD` is used internally without printing it.

## Start and run

In one terminal, start the branch-local services:

```powershell
.\conda\python.exe scripts/run_issue_864_e2e_services.py
```

The launcher uses API `127.0.0.1:8264`, MCP `127.0.0.1:8364`, the two task databases and the approved
real Azure Foundry deployment. It fails on occupied ports, missing model credentials or failed
service health. This scenario does not invoke document generation, email delivery or background
ingestion, so their workers are not acceptance prerequisites. Sign-in OTP is read only from the
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

Real E2E is **pending**, not passed: Docker Desktop failed during startup on its local
`dockerInference` socket, so local PostgreSQL/API/MCP real-service acceptance and the final
screenshot could not yet be produced. Automatic approval rejected socket removal; no factory
reset or bypass was performed. Rerun the commands above after Docker is restored. Unit tests and
the production frontend build do not replace this acceptance gate.
