# Combined audit acceptance (#206)

This integration checkout assembles the separate #856–#861 task commits for
testing. It is not a production deployment or an instruction to merge draft PRs.
#855 was already merged. The scoring specification remains a disabled proposal.

## Real browser scenario

Prerequisites: local Docker/PostgreSQL on port 5432, approved synthetic E2E Azure
settings obtained through the repository profile/import scripts, Node and the
branch-local Python runtime. Never print `.env` or copy production data.

```powershell
.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent
.\conda\python.exe scripts/audit_e2e_206.py --setup
# Use the approved import script with the loopback juris_audit_e2e_206 target:
# scripts/import_e2e_model_credentials_from_server.ps1
# -RequiredModel gpt-5-mini -UseExistingPostgres -VerifyModel
.\conda\python.exe scripts/audit_e2e_206.py --prepare
# Separate terminal:
.\conda\python.exe scripts/audit_e2e_206.py --services
# Once services are ready, original terminal:
.\conda\python.exe scripts/audit_e2e_206.py --authenticate
cd frontend/aijurisdictionfronend
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8264'
$env:CI = 'true'
npx playwright test e2e/issue-206-audit-live.spec.ts --project=chromium
```

The wrapper reuses #864 fixture/auth file names inside this checkout but uses
isolated databases `juris_audit_e2e_206` and `juris_audit_laws_e2e_206`. It requires
the real configured Azure provider and does not intercept browser routes or
fabricate authentication, database responses or visible UI state.

The runnable scenario creates a synthetic case, retrieves a seeded legal source,
submits two browser turns, inspects real admin evidence, verifies distinct HTTP
and worker IDs, validates recorded parent edges and actual model-policy snapshots,
and checks missing hallucination-assessment evidence. It checks the actual model
route, source citation and admin-only access, requests an export, captures a stable
Flow screenshot and saves an allowlisted manifest. It deletes the case and private
authentication file even on failure.

The current frontend may create a fresh session after its history refresh. The
test follows the actual browser correlation headers, finds both sessions through
the case search, and verifies each causal trace independently. It does not merge
their paths or claim that two UI turns necessarily reuse one backend session.
It waits for history hydration before filling the second prompt. Repeated turns
inside one preserved session remain a separate acceptance scenario.

## Executed evidence (2026-10-10)

The real combined scenario passed in 1.9 minutes against Azure `gpt-5-mini`,
local API/MCP and migrated PostgreSQL. Both actual browser correlations were
found through the same synthetic case; each HTTP request linked to its distinct
worker and recorded children. Admin lookup with all four identifiers succeeded;
the unrelated-user filter returned no records and non-admin access was denied.
The returned citation source matched `issue-635-civil-code`. The trace recorded
the selected model profile and policy digest, showed the executed output cleanup
check, and explicitly showed absent security/grounding/hallucination evidence.
The final-state screenshot and sanitized manifest were inspected. Case deletion
and private-authentication cleanup passed.

Evidence run ID: `issue-864-langgraph-audit-20261010T192302Z-f8a515d8` (the reused
fixture retains its #864 naming). Files are under the same named directory in
ignored `runs/e2e/issue-864-langgraph-audit/`: `issue-206-real-causal-flow.png`
and `result-manifest.json`. Retain no longer than seven days.

Combined API lint/types and full API tests passed (five environment-dependent
skips); 16 focused UI tests, 35 focused core/provider tests and the frontend build
passed. The earlier #856 single-turn real scenario also passed. Initial combined
attempts exposed test assumptions about history hydration/session reuse; those
assumptions were corrected before the successful run. None of these results
closes the outstanding matrix cells below or approves a scoring rubric.

## Acceptance matrix

| Scenario | Runnable coverage | Remaining work |
| --- | --- | --- |
| User/case/session/correlation search | #855 existing tests, real trace lookup | Combined search-filter matrix |
| Actual HTTP/worker/model/MCP parent links | #856 live and #206 two-turn test | Persisted browser receipt |
| Parallel/retry/cycle/missing ancestry | #856 unit and browser regression | Real retry/cancellation/resume |
| Frozen model policy/provider identity | #857 unit and #206 live snapshot checks | Live policy edit/history check, template versions |
| Actual validator dispositions | #858 core/API tests | Full real dedicated-workflow matrix and revision linkage |
| Explicit missing validation coverage | #859 component and #206 live UI | Real paging/expired-evidence matrix |
| LangGraph pinned topology and safe codes | #861 API/UI and #856 live graph evidence | Per-node model/validator joins and real loop/resume |
| Final response score | #860 runnable synthetic proposal | Owner approval, actual assessors and production contract |
| Retention/deletion/export | Existing APIs; synthetic case cleanup | Full combined seven-day expiry/export parity matrix |

Unit/browser regressions are preliminary evidence. Only successfully executed
real local scenarios count as real E2E. A skip due to missing fixture, credential
or service means pending, never passed. The matrix must retain outstanding cells
until their scenarios execute successfully.

Evidence belongs only under ignored `runs/` or `artifacts/`, with screenshots and
sanitized result manifests retained for at most seven days. Do not retain raw
protected exports, prompts containing personal data, credentials or authentication
files. Stop only this run's API/MCP processes, remove its two dedicated databases
and transient synthetic storage after investigation. Preserve existing human
oversight, provider consent/routing and authorization during all scenarios.
