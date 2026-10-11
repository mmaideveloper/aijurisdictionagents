# Frontend transport observations (#856)

Authenticated web chat reports content-free transport observations for its exact
stream request: dispatch (reported retrospectively after headers arrive), receipt
of response headers, stream completion, interruption, cancellation or network
failure. Server timestamps record ingestion; bounded client durations are claims.
These are explicitly labeled `client_reported_unverified` in the causal viewer.
They do not prove backend execution, screen rendering, or that a person read an
answer. Only separately recorded backend/model/MCP events prove their execution.

The endpoint requires a valid enabled-user device session, ownership of the chat
session and case, and a retained backend HTTP record for that exact session's
stream path and request ID. Unknown, expired, deleted or foreign targets cannot
be used to create an execution root. Client correlation IDs are not accepted in
the body. Schema validation rejects content and extra fields. Duplicate phases
are suppressed on a best-effort basis and each retained trace is limited to 200
client observations. The original seven-day ledger retention and deletion hooks
apply; no new storage, processor, consent purpose or secret configuration is added.

Delivery is best-effort and never delays, retries or blocks chat. Missing device
credentials, network loss, browser shutdown, unavailable/expired target evidence
or the observation cap may leave no client record. Absence must not be treated as
proof of failed or successful receipt. A network request that never reached the
server cannot be represented as a verified backend operation.

Minimal runnable verification:
`python examples/client_observation_demo.py` validates a synthetic report offline.
`python -m pytest api/aijuristiction-api/tests/test_client_audit.py` and, from the
frontend directory, `npm test -- --run src/__tests__/clientAuditObservations.test.ts`.
The general example remains `python examples/minimal_demo.py`.
Real #206 acceptance must submit a browser turn with its real device session,
assert retained dispatch/header/completion observations reference the stream
request ID, verify the untrusted-source label in the admin UI and capture a
sanitized screenshot. Use synthetic accounts and migrated local PostgreSQL,
API/MCP and the approved Azure model; delete transient evidence within seven days.

Real acceptance passed on 2026-10-11 in 2.1 minutes using run
`issue-864-langgraph-audit-20261011T064936Z-3c74ecb4`: two browser turns, three
observations per request, cross-user rejection, actual Azure `gpt-5-mini`, seeded
MCP citation, exact protected export parity and incomplete/null score gates.
The final `issue-206-real-causal-flow.png` was visually reviewed; the sanitized
`result-manifest.json` records the route, source IDs and observations. Both remain
under ignored run storage for at most seven days. This proves normal completion;
real cancellation, network-failure and browser-shutdown scenarios remain pending.
