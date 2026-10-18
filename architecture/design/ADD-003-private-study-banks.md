# ADD-003: Private study banks with reviewed PDF/image processing

## Record
- Status: In Review
- State: Target / implementation under #924
- Date: 2026-10-18
- Owner: Product owner / maintainer
- Upstream: [UC-004](../use-cases/UC-004-private-study-banks.md), [ADR-004](../decisions/ADR-004-explicit-bank-grants.md).
- BDR: Not required for this bounded owner-directed feature; no sourcing/investment decision is asserted.

## Evidence and boundaries
Confirmed current sources: `laws-tests/api/laws_tests/{app,identity,db,evaluation}.py`, `laws-tests/web/src/main.tsx`, migrations 001–004 and #840. Existing shared identity and isolated PostgreSQL tests service remain. Target responsibilities: responsive tests portal, tests-only admin router, durable jobs worker, shared volume for uploads, central identity adapter and Azure Foundry. No new autonomous agent, vector DB or agent-admin feature is introduced.

## Interfaces and storage
HTTP/HttpOnly same-origin sessions, existing one-use central sign-in exchange and exact-origin/CSRF checks remain. `/api/admin/*` requires current central admin authority. Learner content endpoints recheck bank grants. Public endpoints return bank metadata or public law sources only. SQL migration 005 adds user approvals, explicit grants, tags, revision snapshots, private selections, fenced jobs and minimized audits; LF UK biology/chemistry definitions start as empty drafts.

Import receives bounded multipart PDF/PNG/JPEG files (100 MB, 500 pages), ignores client paths, stores generated filenames under `runs/storage/laws-tests/imports/<uuid>`, and records ordering/checksums. Worker renders/extracts one page at a time, passes only source context to the configured real model, checkpoints results and uses expiring token-fenced leases. Cancel/retry cannot let an old worker overwrite newer progress. Uncertain/duplicate/continuation records require correction. Application validates direct/grouped structure and installs imports inactive. Tags use per-question source revisions, explicit rubric, proposals and conflict-safe apply/undo. Workers do not receive student identity/progress as model input.

## Security, operations and deployment
Threats: ID guessing, stale sessions, CSRF, concurrent edits, malicious source instructions, oversized/malformed files and uncertain AI output. Controls: fail-closed grants/roles, private ownership, exact origin/CSRF, optimistic revisions, untrusted-data prompts, source bounds, no automatic publication and admin review. Source viewing is admin-only. Persistent operational logs omit source text/prompts, answers, tokens and credentials; jobs retain private review data for 30 days. Audit metadata expires after 12 months; nonapproved requests after 90 days. Worker performs hourly cleanup; deleted central users are purged through CLI identity cleanup.

Use the existing API image for a separate worker and a shared tests storage mount. Production runtime requires scoped table-write grants and central `role,email` read grants, persistent volume owned by UID 10840, and upload proxy limits. No production deployment is authorized here. Queue/provider errors are visible and retryable, never mock fallback. Rollback: stop imports/worker, retain access-control API or serve maintenance mode; never roll back to the public reader over private data. Preserve existing attempt snapshots and database backups/deletion rules.

## Validation and risks
Measure denial on the next request after grant/role revocation; test crossed bank/user IDs, disabled questions, concurrent updates, expiry, malformed uploads, cancelled worker fencing, uncertain extraction, tags and undo. Real E2E requires migrated local PostgreSQL, synthetic seeds, real configured model, actual frontend/API/worker and sanitized screenshot/manifest evidence. MCP/collector are required only where legal-source retrieval is exercised, not for medical extraction/tagging.

Unknowns: exact purchased-book structure/scoring, rights and curriculum. Mitigation: use synthetic/authorized documents, retain options/images/provenance, open-text practice only, explicit administrator rubric and publication rights gate. Provider vision capability and latency must be verified with real synthetic sources. No claim of legal/AI compliance approval follows from this design.

Readiness: implementation explicitly authorized by owner; source-data rollout and production release remain pending evidence and rights review. Architecture approval has not been inferred.
