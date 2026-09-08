# Session correlation debugging

Every web chat session owns one opaque `correlation_id`. The browser creates it before the
session request and sends it in the JSON body and `x-correlation-id` header. After the first
message creates a session, the user can open **Diagnostics** beside **Configurations** to view
and copy the ID. A fresh `x-request-id` identifies each HTTP or downstream operation while
`x-parent-request-id` links child calls.

The same correlation context is restored in streaming worker threads and propagated through:

- API requests and correlated error responses;
- the primary LangGraph router and dedicated case workflows;
- local case-document pre/post retrieval filters and JurisDigta MCP tool calls;
- Azure Foundry, OpenAI, and Ollama model calls, including effective messages and final output;
- structured workflow decisions and the final chat result.

## Administrator workflow

Open **Admin → Debug**, paste the exact correlation ID supplied by the user, and select Search.
The timeline shows timestamp, component, stage, status, and protected details. **Flow** remains the
derived cross-service API → retrieval → model/orchestration → response path. **LangGraph audit** is
separate: it shows the executable, version-pinned graph definition and overlays only node/edge
executions explicitly recorded by the workflow runtime. Select a run when one correlation ID has
multiple runs. Selecting a node shows its repeated occurrences and durable workflow-event IDs; the
ordered list below the canvas is the keyboard-accessible equivalent of the visual overlay.

The graph badges identify `graph_key@version`, `flow_key@version`, run status, and evidence
completeness. The displayed SHA-256 digest identifies the minimized topology snapshot; it is not a
signature or a claim of tamper-proof evidence. Dashed edges are executable conditional branches.
Green nodes/edges have recorded evidence. An unhighlighted branch means only “no recorded
execution”; it is not reported as skipped or failed. Historical runs created before graph
instrumentation clearly report missing snapshots/events instead of displaying today's graph.

`GET /v1/admin/debug/{correlation_id}` returns additive `langgraph_evidence` schema v1, grouped by
workflow run. `limit` and `offset` bound workflow-event evidence and `page.has_more`,
`next_offset`, per-run `evidence_gaps`, and `completeness` prevent a truncated trace from appearing
complete. Export adds the same `langgraph_evidence.json` and a schema-v2 manifest alongside the
existing diagnostic JSON files.

Search and export require the existing API key, an authenticated administrator identity, and an
enabled server-side `admin` role. Both actions create admin audit events. Lookup is exact; the
endpoint does not offer broad browsing of user sessions.

For Codex-assisted incident investigation, provide the copied correlation ID, the approximate
event time, and whether the problem occurred locally or on `jurisdigta-server`. Start with an
exact-ID lookup and the smallest relevant log window. Remote log access still requires explicit
permission and must exclude prompts, case facts, documents, credentials, and other secrets.

## Privacy, security, and retention

Troubleshooting records intentionally contain the session content needed to reproduce failures,
including prompts, model output, retrieval candidates/results, and deterministic routing
decisions. They are therefore protected personal-data records, not ordinary operational logs.
Authorization headers, credentials, tokens, connection strings, environment secrets, and hidden
model chain-of-thought are always excluded or redacted.

New graph snapshots contain only reviewed graph/node/edge identifiers, safe conditional labels,
versions, and a digest. Execution occurrences contain bounded statuses, timing, attempts, reason
codes, and references to existing durable event IDs. They never copy graph checkpoint state,
prompts, case facts, documents, raw tool payloads, or hidden reasoning. The snapshot lives inside
the owning workflow run state, so the existing case deletion cascade removes it with that run.

`session_debug_events` assigns `expires_at = created_at + 7 days`. Expired rows are deleted hourly,
at API startup, and on every debug write and lookup; they are never returned after expiry. In-memory session lookup and
correlation-based decision lookup apply the same seven-day cutoff. Azure deployment config sets
the queried Application Insights tables (`AppDependencies`, `AppExceptions`, `AppRequests`, and
`AppTraces`) to seven days for both interactive and total retention. Loki already defaults to
seven days.

Downloaded ZIP files leave server retention control. Administrators must keep an export only for
the active incident and delete it no later than seven days after the underlying event. Never
attach it to a public issue or use production personal data in tests.

This design supports GDPR storage limitation, access control, and accountability, and provides
EU AI Act traceability and human oversight without exposing hidden reasoning. A production owner
must still document the lawful basis, restrict the admin group, review audit events, and handle
data-subject deletion across the parent case/session lifecycle.

The user-facing dialog contains only the opaque ID and a privacy warning. It does not send email,
upload a support report, or disclose chat/case content.

## Verification

```powershell
.\conda\python.exe -m pytest api/aijuristiction-api/tests/test_debug_api.py tests/test_correlation.py -q
cd frontend\aijurisdictionfronend
npm test -- --run src/__tests__/aiModelAdminCases.test.tsx
```

The repository-wide runnable overview remains:

```powershell
.\conda\python.exe examples\minimal_demo.py
```

For the real issue-788 browser proof, start the local API with loopback PostgreSQL, the JurisDigta
MCP law store, and a verified Azure Foundry paid-user route. Prepare only synthetic records, then
pass the printed paths to Playwright:

```powershell
.\conda\python.exe scripts\prepare_issue_788_langgraph_audit_e2e.py
$env:ISSUE_788_API_BASE_URL = "http://127.0.0.1:8080"
$env:VITE_API_BASE_URL = $env:ISSUE_788_API_BASE_URL
$env:ISSUE_788_E2E_MANIFEST = "<printed input-manifest.json path>"
$env:ISSUE_788_E2E_EVIDENCE = "<printed evidence directory>"
Set-Location frontend\aijurisdictionfronend
npx playwright test e2e\issue-788-langgraph-audit.spec.ts --project=chromium
```

The test rejects mock routing, drives the real API → LangGraph → MCP/PostgreSQL → Azure Foundry
path, opens Admin → Debug, verifies both the SVG and ordered accessible evidence, writes ignored
evidence under `runs/e2e/issue-788-langgraph-audit`, and deletes the synthetic case. Remove retained
evidence within seven days.
