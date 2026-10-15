# Reflection and durable resume (#753)

Graph `legal_document_workflow@5` adds the reflection node. Versions 1–4 keep their graph edges
for pinned runs. New system payment-confirmation assignments use v5; other assignments move to
v5 through the existing reviewed flow promotion process. Running assignments remain pinned.

The v5 path is draft → output validation → safety/privacy validation → structured critique →
revision → output validation. Only `empty_document_draft`, `unresolved_placeholder`, and
`verified_fact_missing_from_output` are recoverable. All other failures require human review.
Safety/privacy failures finalize immediately. Mandatory case-review failures never request revision.
Every revision receives the previous response and a fixed actionable instruction, while verified
facts and legal sources remain authoritative. This is structured quality feedback, not hidden reasoning.
V5 validates missing facts/placeholders before silent quality repair; legacy normalization is retained
for older graphs. Markdown source links and numeric citation markers remain valid evidence.
Completed chat replies disclose the number of revisions in the user's language.

The flow's existing `termination_policy.quality_revision_limit` is the maximum number of redrafts
(default 3). State persists its alias `max_revision_attempts`, the actual redraft `retry_count`,
quality-failure count, and the existing unchanged-output/no-progress fingerprint. A successful
redraft may use the last permitted attempt. Repeated unchanged failures stop earlier. Deadlines,
session expiry and the recursion backstop still apply. Unknown validator messages are not included
in critique instructions. Audit events contain fixed categories/instructions, revision numbers,
provider/model route and parent artifact identifiers; no extra draft bodies or hidden reasoning are
copied into the event log. Case state and checkpoint history retain draft content under existing case
access, retention and deletion controls. AI disclosure and human review remain mandatory.

## Supported persistence

The production service factory requires PostgreSQL plus `PostgresSaver`. SQLite application
projections paired with `InMemorySaver` are rejected with a configuration error. Memory savers
are available only through explicit dependency injection for offline examples/unit tests.
Replicas must share the same checkpoint database and workflow projection database. Lifecycle
start/resume/cancel operations use a PostgreSQL advisory lock scoped to the workflow identifier.
Locks release when the connection closes, including after process failure.

`POST /v1/case-workflows/runs/{id}/resume` now requires `resume_token` copied unchanged from
the current run's `pending_action.resume_token`, in addition to `user_id` and `value`. Treat it
as an optimistic concurrency identifier; do not log it in UI screenshots. A duplicate/stale
request receives HTTP 409 and must reload the run. It cannot answer the next pending question.
Terminal runs return their existing result without re-executing lifecycle nodes.

Checkpoint and projection commits are not one transaction. Before resuming, the API rebuilds and
persists the projection from the checkpoint under the same workflow lock. If a checkpoint advanced
but saving the projection failed, retrying repairs the projection and rejects the old token instead
of re-executing that step. Run metadata is saved before initial graph execution, so failed initial
projection writes still leave a discoverable run. Missing checkpoints and non-interrupted incomplete
execution raise recoverable operational errors (`workflow_checkpoint_missing` or
`workflow_execution_incomplete`). Operators should investigate these states; never reconstruct a
checkpoint from untrusted user input or replay external side effects blindly. Terminal external
controls such as cancellation remain authoritative in the projection. This does not promise
exactly-once external tool delivery across a crash inside a tool call; such tools still require
their own idempotency contract.

## Runnable visible example

From the task worktree, using its Python 3.13 conda runtime:

```powershell
.\conda\python.exe examples/reflection_resume_demo.py
# With DB_OPTION/DB_CLOUD explicitly targeting a synthetic loopback test database:
.\conda\python.exe examples/reflection_resume_demo.py --postgres
.\conda\python.exe examples/minimal_demo.py
.\conda\python.exe -m pytest tests/test_case_workflow.py -q
.\scripts\validate_api.ps1
.\conda\python.exe -m pytest api/aijuristiction-api/tests -q
```

The example deliberately omits the amount from a synthetic first response. It prints:

```text
PREVIOUS RESPONSE: ... Synthetic A paid Synthetic B. ...
CRITIQUE: Include every verified fact verbatim, with its original spelling, dates and units. Do not translate or reformat verified values.
REVISED RESPONSE: ... Synthetic A paid Synthetic B 100 EUR. ...
PASS: one revision; provider=deterministic; model=synthetic-demo; status=completed
```

It interrupts for the amount, reconstructs the runtime, resumes, and asserts both the successful
revision and persisted counters. `--postgres` closes/reopens the checkpointer connection before
resuming and deletes the example checkpoint afterward. The default offline example is deterministic
and explicitly does not claim durable persistence or real-model UI E2E acceptance.

## Final user-facing E2E acceptance

Prepare the dedicated loopback databases and browser dependencies once, then run the real example:

```powershell
.\scripts\import_e2e_model_credentials_from_server.ps1 -UseExistingPostgres -VerifyModel -DatabaseUrl "postgresql://postgres:postgres@127.0.0.1:5432/aij_e2e_753_reflection_durable_resume"
.\skills\start-postgres\scripts\start_postgres.ps1 -ProjectName laws-collector -DatabaseName laws_e2e_753_reflection
npm --prefix frontend/aijurisdictionfronend ci --no-audit --no-fund
npm --prefix api/aijuristiction-api/e2e-playwright ci --no-audit --no-fund
.\conda\python.exe scripts/run_issue_753_e2e.py
```

The credential import explicitly creates `aij_e2e_753_reflection_durable_resume`, regardless of branch name.
The runner intentionally uses that synthetic API database and `laws_e2e_753_reflection` on the
existing local PostgreSQL containers. It starts MCP on 8073, API on 8083 and frontend on 5173,
with the authentication email outbox also stored in the dedicated API PostgreSQL database,
fails if those ports are occupied, seeds a labeled synthetic law with the existing reference fixture,
and verifies the source directly through MCP. It grants the current external-model and
external-check account consent through the real profile UI; per-run optional checks are declined.
Only the isolated authentication fixture uses `LOCAL_AUTH_ACCEPT_ANY_CODE=1`; it does
not change the repository dotenv file, model route, database responses or application UI state.
The local synthetic-account password is generated per run, passed only to child processes and
the local account provisioner, and redacted from retained text artifacts.
The real model is asked to include a synthetic bracketed first-draft marker, then remove it after
critique. The test must observe an actual revision; a first-pass answer is not accepted as proof.

The browser test is `api/aijuristiction-api/e2e-playwright/tests/issue-753-reflection.spec.ts`.
It creates a synthetic case through the frontend, confirms authorized persistence, checks the v5
run, source identifiers, provider/model events and visible revision disclosure, and retains the
generated PDF. The runner validates PDF structure/text and renders page 1. Cases are deleted in
test cleanup, services stop afterward, and text failure snapshots are redacted. The deterministic
source fixture and synthetic test accounts remain in the dedicated local test databases for reruns;
remove those test databases after finishing manual inspection. No production data is imported.
Use `--serve` to keep services running for manual inspection instead of running Playwright.
The test prefills four synthetic verified facts through the workflow API, then submits the missing
amount through the frontend. This avoids relying on repeated composer hydration while still
exercising the complete frontend-triggered retrieval, drafting, critique, revision and response path.

For cross-process and fault-injection regression checks, explicitly configure `DB_OPTION=postgres`
and a loopback synthetic `DB_CLOUD`, then run:

```powershell
.\conda\python.exe -m pytest tests/test_case_workflow_postgres.py -q
```

These tests use separate connections/runtime instances, concurrent duplicate resumes, a failed
projection write, and a separate Python interpreter. They delete their own run/checkpoint records.

Follow `docs/E2E_TEST_EVIDENCE_RULE.md`: run the branch frontend, API, MCP and PostgreSQL migrations,
seed synthetic legal sources, verify them directly through MCP, then create a synthetic case in
the frontend. Exercise the v5 assignment, observe failed quality review and a revision preserving
the same source identifiers, and verify the visible response. Restart the API while interrupted,
resume using the pending token, and submit the same token concurrently to verify no repeated step.
Retain a stable screenshot, sanitized route/source/run manifest and, for generated documents,
the PDF, rendered first page and text/structure assertions. Store evidence only under ignored
`runs/` or `artifacts/`, delete synthetic records after the run, and delete transient evidence within
seven days. Deterministic graph tests and the console example are preliminary regression evidence;
they cannot substitute for the real frontend → API → MCP → PostgreSQL path with Azure Foundry.
