# Audit evidence completeness (#859)

Admin Debug now keeps a localized evidence summary visible across timeline and
graph tabs. Missing historical validator metadata stays unknown. A recorded
category describes coverage, not success: each check separately shows its actual
outcome, validator version and answer-revision linkage. Explicit expired,
unsupported and not-applicable values are rendered only when returned by the API.
An absent graph does not imply that LangGraph was not used.

Unavailable remote telemetry displays a warning without hiding local records.
Graph evidence has keyboard-accessible next/previous page controls. Late page
responses cannot replace a different selected correlation. Paging changes graph
evidence only; it does not discard the trace's timeline. Labels use React text
rendering, including unknown or malicious validator identifiers.

This frontend-only change consumes optional #858 validation metadata and works
with older API responses. It adds no personal-data persistence, telemetry,
permission, consent change or retention extension. Existing server-side admin
authorization still applies. Unknown checks and source presence must not be
interpreted as legal-risk clearance or a hallucination guarantee.

Minimal runnable regression from `frontend/aijurisdictionfronend`:

```powershell
npm ci
npm test -- --run src/__tests__/auditEvidenceSummary.test.tsx
npm run build
```

The repository overview remains `python examples/minimal_demo.py` (no Python
changes are required for this UI task). For real acceptance use #856's live
PostgreSQL/API/MCP/Azure fixture with the combined audit branches, open its actual
trace, assert the missing grounding/hallucination rows and capture a final-state
screenshot. Verify pagination against real retained records and authorization
with a non-admin account. Store sanitized evidence only in ignored `runs/`,
remove synthetic records and delete evidence within seven days. Combined real
acceptance remains pending; component tests are preliminary regression evidence.
