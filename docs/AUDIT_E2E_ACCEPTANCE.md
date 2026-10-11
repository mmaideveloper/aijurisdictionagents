# Combined audit acceptance (#206)

## Accepted scope

On 2026-10-11 the owner chose to finish auditing existing execution and clearly
expose missing quality evidence. The implementation connects user, case, session,
correlation, HTTP/worker ancestry, LangGraph run/node occurrences, actual model
routes and executed validation results in the protected admin viewer and export.
Candidate checks link to the persisted answer revision; later changes are marked
`changed_after_check`, so an earlier check does not certify a rewritten answer.
Resumed workflows retain node evidence across distinct request correlations.

The approved #860 score contract uses grounding 40%, factual consistency 30%,
coverage 20%, clarity 10%, and review threshold 85. Missing required assessments
produce an incomplete state, null score and mandatory review for ordinary chat.
Dedicated-workflow score aggregation and new dimension,
grounding and hallucination assessors remain deferred under #860. Existing narrow
checks are never represented as comprehensive security or hallucination checks.
Unknown provider revisions, prompt-template versions and injected-validator
versions remain unknown. Model explanations use supported bounded decision codes;
hidden reasoning, checkpoint bodies and retrospective rationales are not collected.
No new cancellation control or provider-supplied reasoning summary is introduced.

Metadata-only additions preserve enabled-admin authorization, audited access,
seven-day diagnostic expiry, owning-case deletion, existing consent/routing and
human review for legal-risk output. This is an engineering traceability change,
not a legal compliance certification or production deployment.

## Run the real local scenarios

Prerequisites: Docker/PostgreSQL on port 5432, approved synthetic Azure E2E
credentials, Node, and this worktree's Python runtime. Never print `.env`.

```powershell
.\scripts\sync_env_profile.ps1 -Mode Pull -Profile codex-agent
.\conda\python.exe scripts/audit_e2e_206.py --setup
# Import the approved credential with scripts/import_e2e_model_credentials_from_server.ps1
# targeting loopback database juris_audit_e2e_206, with
# -RequiredModel gpt-5-mini -UseExistingPostgres -VerifyModel.
.\conda\python.exe scripts/audit_e2e_206.py --prepare
# Separate terminal:
.\conda\python.exe scripts/audit_e2e_206.py --services
# Original terminal, once services are ready:
.\conda\python.exe scripts/audit_e2e_206.py --authenticate
cd frontend/aijurisdictionfronend
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8264'
$env:CI = 'true'
npx --no-install playwright test e2e/issue-206-audit-live.spec.ts --project=chromium
# Re-authenticate from the repository root before EACH following scenario:
# .\conda\python.exe scripts/audit_e2e_206.py --authenticate
npx --no-install playwright test e2e/issue-206-workflow-audit-live.spec.ts --project=chromium
npx --no-install playwright test e2e/issue-206-lifecycle-audit-live.spec.ts --project=chromium
npx --no-install playwright test e2e/issue-206-complete-workflow-audit-live.spec.ts --project=chromium
```

The fixture reuses #864 filenames but isolates data in `juris_audit_e2e_206` and
`juris_audit_laws_e2e_206`. Tests use the real frontend (5189), API (8264), MCP
(8364), migrated local PostgreSQL and approved Azure `gpt-5-mini`. Synthetic users,
cases and seeded legal source `issue-635-civil-code` are used. No mocked provider,
intercepted response or fabricated UI state counts as acceptance. Missing services
or credentials mean pending; a skipped test is not a pass.

The frontend can create a fresh session after history hydration. Tests follow
actual request headers and discover all correlations through the case index.
Durable workflow continuity is asserted through the pinned workflow run ID.
Browser history restoration does not claim that every UI turn reuses one session.

The lifecycle test runs two browser sessions concurrently against one synthetic
case, respecting the account's one-active-case limit. It closes one browser context
after recorded stream headers, checks backend termination separately from client
receipt, and reloads retained history in the surviving browser. Closing the client
does not prove cancellation of the provider's in-flight computation.

`scripts/audit_e2e_206_metadata.py` only changes the fixed loopback acceptance DB
after validating the exact synthetic case/user from the fixture. It edits two
fixture policies to prove old provenance remains frozen, then ages that case's
audit metadata eight days to exercise real expiry queries and UI. It does not
fabricate API responses or change ordinary case-history retention.

## Acceptance matrix and limits

| Area | Executed real coverage | Explicit limit |
| --- | --- | --- |
| Search and authorization | Individual/combined user, case, session and correlation filters; unrelated-user isolation; non-admin denial | Admin viewer only; no new mobile audit viewer |
| Causal flow | Actual HTTP/worker/model/MCP links; two turns; parallel requests; browser disconnect and restored history | Client receipt and backend completion are independent |
| Historical provenance | Actual real provider/model and policy digest; policy edit leaves history unchanged | Unreported template/provider revisions remain unknown |
| LangGraph | Pinned topology, repeated input nodes, interruption/resume, exact model/validator occurrence links across correlations | Provider-internal retries and unsupported summaries are not inferred |
| Validation | Existing checks, candidate/final revision linkage and visible changed-after-check state | No new comprehensive security/grounding/hallucination assessor |
| Missing/expired evidence | Visible missing categories, pagination, expired ledger/search/graph/score projections | Ordinary retained case content has separate retention |
| Response quality | Persisted answer-linked incomplete assessments, null scores, mandatory review | Actual dimension assessors remain #860 follow-up |
| Export/deletion | Four-projection ZIP parity; synthetic case and private-auth deletion | Export read into memory, not retained as a protected archive |
| Complete document workflow | Runnable real output/security node checks, pinned flow, citation IDs, PDF structure/text/render and UI screenshots | Count as passed only with the passing manifest and reviewed render |

Unit/regression evidence also covers malformed/missing ancestry, retry/cycle
projection, unsupported/failed validator states, retention and secret exclusion.
These tests do not prove execution of every provider-internal retry or model route.

## Executed evidence, 2026-10-11

- Run `issue-864-langgraph-audit-20261011T130557Z-78fa0b92`: node-link two-turn
  scenario passed (2.7 minutes); resumed workflow passed (1.7 minutes). The resume
  test found a cross-correlation evidence gap, fixed in PR #890 and verified again.
- Combined run `issue-864-langgraph-audit-20261011T132538Z-b6766445`: extended
  two-turn/search/paging/policy/revision/export/expiry scenario passed (3.0 minutes).
  `issue-206-real-causal-flow.png`, `issue-206-expired-evidence.png`,
  `result-manifest.json` and `expiry-result-manifest.json` record the result.
- The same combined run passed parallel requests/browser close/restored history
  (2.0 minutes). `issue-206-reloaded-history.png` and
  `lifecycle-result-manifest.json` retain final evidence.
- Complete document workflow writes `complete-workflow-result-manifest.json`,
  `issue-206-complete-workflow.pdf`, its first-page render and final user/admin
  screenshots. Require the passing manifest and visual review before acceptance;
  test discovery alone is not a passed result.

Earlier failed test attempts assumed a generic route for a follow-up, allowed two
active cases on a one-case subscription, or assumed browser offline emulation
would close an existing stream. Passing tests follow actual routes, use two browser
sessions on one case and explicitly close the browser context. These changes do
not replace the required real provider, source, isolation or receipt assertions.

API lint/types and full API tests passed for the implementation changes (five
environment-dependent skips); focused core/UI regressions and frontend builds
passed. All applicable PR checks passed before implementation merges #890/#892.

## Evidence and cleanup

Evidence is ignored under `runs/e2e/issue-864-langgraph-audit/<run-id>/` and retained
for at most seven days. Screenshots and manifests contain synthetic identities and
allowlisted metadata. Document acceptance retains the PDF and first-page render,
validates PDF structure/extracted expected text and visually reviews the render.
No credentials, private-auth files, raw protected exports or personal prompts are
retained as acceptance evidence. Each scenario deletes its case and private auth
file in cleanup. At the end stop only owned API/MCP processes, drop the two isolated
acceptance databases and remove transient synthetic file storage; preserve the
sanitized screenshots/manifests/PDF until the retention deadline.

Minimal offline examples remain runnable:
`python examples/minimal_demo.py`, `python examples/node_execution_audit_demo.py`
and `python examples/validation_audit_demo.py`.
