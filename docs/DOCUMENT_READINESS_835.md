# Saved-document readiness

Chat completion and confirmation of a draft do not mean that a downloadable
document exists. The API publishes generated-document IDs only after storage
returns them. Readiness checks validate the last assistant message's generated
references against the same case and a nonempty stored payload. A missing,
deleted, empty, or unverifiable artifact is not ready, even when cached result
metadata or assistant prose previously said otherwise.

A processing placeholder after confirmation is an incomplete export, not a
success. Persistence errors produce HTTP 503 (or SSE
`document_generation_failed`) with a safe error and retry instruction. Identical
payloads already saved in the case are reused on retry, including after a partial
package write. This handles sequential retries; concurrent generation still uses
the existing session-worker coordination and is not a new distributed lock.

The web UI accepts viewer links only when their case/document IDs match generated
documents returned by case history. An unverified ready claim is replaced with
an explicit incomplete-export notice and a retry button. The viewer enables
download after a successful preview fetch; 403/404 remain visible failures. The
shared API policy applies to chat simulator and mobile consumers as well.

## Validation

```powershell
.\scripts\validate_api.ps1
.\conda\python.exe -m pytest api/aijuristiction-api/tests
python examples/document_readiness_demo.py
cd frontend/aijurisdictionfronend
npm test -- --run src/__tests__/assistantWorkspace.test.tsx src/__tests__/caseClient.test.ts src/__tests__/caseProvider.test.tsx
npx playwright test e2e/generated-document-download.spec.ts
```

API regression coverage includes storage exceptions, no returned ID, empty body,
stale ready metadata, deleted artifacts, successful source/PDF access, and retry
after a partial package write. Browser tests cover an unpersisted confirmed draft,
invented link suppression, a working viewer/download, and 403/404 failures.

Tests and the example use synthetic facts. No account email, case facts, raw
production logs, or document content is added to operational error logs. Existing
access checks and retention/deletion remain unchanged. Export readiness is a
technical state; generated legal drafts still require human review.

## Production verification after deployment

The reported `case-test-template-09` execution was around 2026-09-24 11:00
Europe/Budapest (09:00 UTC). The exact time of `case-test-template-08` is not yet
confirmed. SSH connectivity prevented inspection of the production logs; the
original HTTP outcome is unknown.

After deployment and restored authorized access, regenerate both cases from their
original facts, check the saved IDs, viewer, and PDF downloads, and record only
sanitized outcomes in issue #835. Do not invent historical links or mark the old
executions successful. Production regeneration is a remaining rollout check,
not evidence supplied by synthetic local tests.
