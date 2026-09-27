# Acceptance evidence for #840

The real local browser acceptance uses a synthetic account, branch-local identity PostgreSQL
database, the separate `laws-tests` database, the existing account frontend/API, the laws-tests
frontend/API, and the local MCP service. MCP is running for environment parity; grading uses
the fixed reference answer through the existing model adapter and does not perform legal RAG.

Scenarios:

1. Signed-out desktop A-20 with all original answer sections expanded and login visible.
2. Signed-out 390px mobile A-20, no horizontal overflow, readable expanded answers and login.
3. Real account sign-in including the generated synthetic email OTP and one-use authorization
   handoff; no injected cookies, fabricated UI state or route interception.
4. E-1 complete answer through Azure Foundry `gpt-5-mini`: pass, 100%, no missing points.
5. E-1 incorrect answer through the same route: fail, 0%, missing reference points listed.
6. Persisted history after reload, followed by user-directed history deletion.

The actual observed scores and route are asserted and written to
`runs/issue840/evidence/result-manifest.json`. Screenshots 01–06 are stored beside it.
The manifest includes the run ID, services, source IDs, attempt IDs and cleanup status; it
omits submitted credentials, OTPs, connection strings and production user data. Retain for
14 days. Authentication traces/video are deliberately disabled. Browser snapshots on failure
are not suitable for publication until checked for sensitive information.

Earlier PostgreSQL unit/integration checks cover public/private boundaries, schema structure,
repeat migration, expiry and CSRF. These use stubs only at specified unit boundaries and do
not replace the real-model acceptance above. A future model/run can score differently; any
failed asserted outcome must remain a failure rather than editing UI evidence.
