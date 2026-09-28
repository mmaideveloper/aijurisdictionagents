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

## Case-09 content regression

The four supplied PDFs contain the same processing/download announcement, not
an employment contract. A nonempty stored payload is therefore insufficient.
The shared content guard rejects recognized status/boilerplate-only text before
persistence and when checking readiness. Legacy source/preview/PDF requests return
409 with a regeneration instruction for such content. Case history returns
`download_available=false` for invalid/missing generated content; the frontend
excludes these records from ready-document links. Missing stored generated
content returns 404; the renderer no longer borrows a different chat message under
an existing document ID. Export selection ignores status-only candidates while
preserving a substantive draft with an introductory status message.

This deterministic check recognizes known conversational placeholders; it is not
a legal completeness or correctness assessment. Real drafts still require human
review. Regression fixtures are synthetic and contain no supplied PDF files or
account details. The positive regression parses the exported PDF and verifies
employment terms, not just the PDF header. Historical HTTP outcomes remain unknown.

## Confirmed draft persistence follow-up

Employment contract headings (`Pracovná zmluva`, including plain text, bold and
Markdown headings, and `Employment contract`) are recognized without requiring
download-ready prose. Structured document content remains the first choice;
visible document sections are the fallback. Confirmation questions and recognized
closing download announcements are excluded from the stored document section.
A reply still asking the user to confirm document preparation remains a preview
and does not create a generated document yet.

A standalone `dobre` confirms only the current document-preparation question.
Affirmatives match words rather than substrings (for example, `dokument` is not
`ok`). Any intervening answer or unrelated assistant message consumes the old
question. Explicit save commands such as `ulož dokument vo formáte PDF` also work
without an unanswered question; refusals do not authorize generation.

For an unambiguous confirmation/save-only instruction, the direct reply path
saves the latest substantive assistant draft without asking the model to rewrite
it. It never searches past a user edit or an unrelated assistant response. A
failed write may leave consecutive save requests; these can retry the same draft.
Successful retries reuse the existing payload/ID, including partial package writes.
Requests that also change facts continue through normal drafting.

Persistence completes before the success message and generated IDs are published.
An explicit PDF/save attempt that produces no artifact returns the existing safe
failure notice; storage exceptions and missing IDs retain the 503 error contract.
Unverified created/saved-PDF claims are rejected as well as ready/download claims,
and a replaced false-success response drops its structured presentation.

Minimal offline example: `python examples/document_readiness_demo.py`.
Deterministic regression: `python -m pytest api/aijuristiction-api/tests/test_document_readiness.py`.
The API integration test confirms a synthetic contract through `/reply`, checks
the saved ID in case history, reads its source and PDF, and verifies employment
terms in the extracted PDF. These tests are not real-model browser acceptance;
that requires the local PostgreSQL/API/MCP/frontend environment and evidence
defined in `docs/E2E_TEST_EVIDENCE_RULE.md`. Production cases 08/09 remain a separate
post-deployment check; no historical links are repaired or fabricated.

Privacy and legal-risk scope: no new storage, permissions, retention period,
external recipient or consent purpose is introduced. Tests use synthetic facts;
operational errors retain only correlation IDs and reason/error types, not the
contract body. Saved legal drafts still require human review.

### Validation boundary for this follow-up

The deterministic suite covers the complete API draft/confirmation/save/PDF
sequence, streamed success and storage failures, retries, and rejection of
historical fake-link recovery. It uses a synthetic model response and local test
storage; it does not establish real-model browser acceptance.

On the implementation host, the approved `codex-agent` profile passes its strict
local audit, but the dedicated real-model E2E profile is incomplete. The missing
required settings are `E2E_AZURE_FOUNDRY_ENDPOINT`,
`E2E_AZURE_FOUNDRY_API_VERSION`, `E2E_AZURE_FOUNDRY_DEPLOYMENT`, and
`AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`. Restore authorized SSH access and use the
credential bootstrap documented in `docs/E2E_TEST_EVIDENCE_RULE.md` before the
final PostgreSQL/API/MCP/frontend run. Keep that acceptance pending until its
screenshots, PDF and result manifest are recorded. Transient test output belongs
under ignored `runs/validation/835-backend/` and should be removed after review.
