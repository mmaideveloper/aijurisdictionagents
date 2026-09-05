# Session correlation debugging

Every web chat session owns one opaque `correlation_id`. The browser creates it before the
session request, sends it in the JSON body and `x-correlation-id` header, and displays a copy
control above the conversation. A fresh `x-request-id` identifies each HTTP or downstream
operation while `x-parent-request-id` links child calls.

The same correlation context is restored in streaming worker threads and propagated through:

- API requests and correlated error responses;
- legacy orchestration and the primary LangGraph router;
- local case-document pre/post retrieval filters and JurisDigta MCP tool calls;
- Azure Foundry, OpenAI, and Ollama model calls, including effective messages and final output;
- structured workflow decisions and the final chat result.

## Administrator workflow

Open **Admin → Debug**, paste the exact correlation ID supplied by the user, and select Search.
The timeline shows timestamp, component, stage, status, and protected details. Flow view gives a
compact API → retrieval → model/orchestration → response path. Export creates a ZIP containing a
manifest plus session, messages, timeline, flow, decision, and available Application Insights
JSON files for offline Codex review.

Search and export require the existing API key, an authenticated administrator identity, and an
enabled server-side `admin` role. Both actions create admin audit events. Lookup is exact; the
endpoint does not offer broad browsing of user sessions.

## Privacy, security, and retention

Troubleshooting records intentionally contain the session content needed to reproduce failures,
including prompts, model output, retrieval candidates/results, and deterministic routing
decisions. They are therefore protected personal-data records, not ordinary operational logs.
Authorization headers, credentials, tokens, connection strings, environment secrets, and hidden
model chain-of-thought are always excluded or redacted.

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

## Verification

```powershell
.\conda\python.exe -m pytest api/aijuristiction-api/tests/test_debug_api.py tests/test_correlation.py -q
cd frontend\aijurisdictionfronend
npm test -- --run src/__tests__/assistantWorkspace.test.tsx
```

The repository-wide runnable overview remains:

```powershell
.\conda\python.exe examples\minimal_demo.py
```
