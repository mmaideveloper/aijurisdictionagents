# Consent, subject rights and AI transparency (#389)

## Runtime controls

`aijurisdictionagents.privacy` holds the versioned consent ledger, restriction/hold state,
strict metadata-only compliance event vocabulary, and AI output metadata. PostgreSQL
migration `389_privacy_controls.sql` and the SQLite offline schema initialize these tables.
Consent decisions are append-only and ordered by a database sequence, so withdrawal wins
even if timestamps coincide. Unknown scopes and stale versions are rejected. Existing
registration acknowledgement is not retroactively treated as external-model, tool, sensitive
processing or marketing consent. Scope notices are localized in the frontend profile.

External model selection requires current `external_models` consent. Reused clients recheck
restriction, enabled-account state and consent before each completion; sensitive model I/O
is excluded from diagnostic body capture. Cloud document embeddings are checked before each
batch. Chat requests in real-provider mode authenticate the device and session owner before
processing. The web client forwards its existing device token. Anonymous real-provider chat
must sign in; there is no implicit external processing permission. Explicit deterministic mock
mode is an offline fixture path, never final E2E evidence.

Default registry tools and external web screening require authenticated privacy context and
`external_checks` consent. Workflow execution also requires its existing exact per-run purpose,
tool and notice-version ledger entry. Worker threads copy that context. Withdrawing central
consent blocks a later invocation even if a per-run grant remains. Already transmitted requests
cannot be recalled; subsequent calls are blocked. Marketing is optional and separate from
registration, invoice and other service messages. New marketing senders must call
`require_processing(user_id, "marketing")` immediately before delivery; no marketing sender
was found in the current application.

An operator can mark `sensitive_consent_required` only after the privacy owner determines
consent is an applicable lawful condition. That flag enforces current `sensitive_processing`
consent for processing. A checkbox does not establish an Article 9 or Article 10 condition,
and model inference cannot decide that legal question. Other lawful bases and prohibited
processing require owner assessment; this implementation is not a legal compliance certification.

## Subject-right endpoints

All subject endpoints require the existing API key **and** a valid device token bound to the
path subject (`x-jurisdigta-device-id`, `x-jurisdigta-device-token`). A shared API key is insufficient.

| Endpoint | Effect |
| --- | --- |
| `GET /v1/privacy/subjects/{user_id}` | Current notice, decisions, restriction and request status |
| `POST .../consents` | Record `scope`, `text_version`, `granted`; false withdraws |
| `PUT .../restriction` | Restrict/resume; pending erasure cannot be released by the user |
| `GET .../export` | No-store ZIP: personal JSON, owned documents/transcripts and manifest |
| `POST .../requests` | `delete` or `anonymize`; immediately restrict and await operator review |
| `GET /v1/privacy/operator/requests` | Admin-key-protected work queue |
| `POST /v1/privacy/operator/requests/{request_id}/review` | Approve/reject; hold blocks approval |
| `PUT /v1/privacy/operator/subjects/{user_id}/policy` | Admin-managed hold and sensitive-consent condition |

Export includes owned API rows, derived case records in that database, and live sessions on
the serving process. It excludes passwords, tokens, credential stores, hashes and internal
storage paths. Nested JSON credential fields are removed. Missing files are explicitly listed
for follow-up. Email, separately stored workflow state, observability, other API replicas,
backups and external processor data require the operator inventory; the archive says so and
does not claim to export those systems. Sensitive exports must never enter ordinary logs.

## Operator erasure / anonymization workflow

1. Verify identity through the device-authenticated request. Review scope, identity confidence,
   third-party rights, accounting obligations and legal holds. The operator API requires a
   separately configured admin key. Store the owner decision in the controlled support system;
   do not put names, prompts, document bodies or secrets into compliance events.
2. Approve or reject. Approval produces `approved_pending_execution`, not `completed`.
   Rejection leaves processing restricted until the subject explicitly resumes it.
3. Pause relevant workers and stop/restart API replicas to prevent stale cache/checkpoint use.
   From the approved runtime execute:

   ```powershell
   .\conda\python.exe scripts/execute_privacy_request.py --request-id REVIEWED_REQUEST_ID
   .\conda\python.exe scripts/execute_privacy_request.py --request-id REVIEWED_REQUEST_ID --execute
   ```

   The dry run reports status only. Execution refuses unapproved requests or holds, removes
   owned cases and workflow diagnostics/checkpoints, queues/retries file cleanup, strips linked
   content from retained usage totals, clears authentication records, removes consent links,
   deidentifies and disables the account. It leaves `pending_external_cleanup`. A retained
   tombstone is pseudonymized operational data, not a claim of irreversible anonymization.
4. Inventory separately stored email outbox, delivered emails, shares, registration/pending
   signup records, standalone workflow SQLite stores, reporting databases, logs/telemetry,
   cloud blobs, every live replica and external processors. Export or erase/restrict each
   applicable surface using that system's authorized interface. Preserve only a documented
   lawful exception, with its purpose, expiry and access restriction. The workflow does not
   override billing/accounting retention or promise erasure of a recipient's delivered copy.
5. Verify all queued files are removed or an authorized exception is recorded. Verify database
   records and cached case/session state cannot be retrieved. Record backup expiry and restore
   suppression evidence. Resolve subscription/accounting retention with the privacy/accounting
   owner. Tell the subject what was erased, what is lawfully retained, why and for how long.
   Complete the controlled support ticket only after these steps; no automated completion
   endpoint can falsely certify external cleanup.

## Transparency and logging

Assistant messages contain `ai_transparency`: AI flag, actual route provider/model when known,
generation timestamp, limitations, human-review recommendation and available source references.
Generated-document metadata is persisted separately by artifact identity. Historical outputs
without reliable route evidence use null provider/model and `provenance_status=unavailable`;
the current configured route is never invented as historical provenance. The assistant UI
always displays the localized AI draft/human-review notice. Citations remain visible through
the existing citation contract. Deterministic statuses and unavailable provenance must not
be represented as evidence of an actual external-model call.

Compliance events accept fixed event/outcome codes and counts only, with no user ID, prompt,
document text, filename, email, token or arbitrary metadata. DB triggers reject updates and
deletes. This is append-only at the ordinary SQL interface, not protection against a database
superuser. Production roles/privileges and evidence retention need the manual setup review.

## Validation and examples

`python examples/minimal_demo.py` remains the default example. The focused synthetic example
is `python examples/privacy_controls_demo.py`; it exercises denial, grant, withdrawal,
transparency and operator review without any model/network call. Runtime databases/files live
under ignored `runs/storage/privacy-demo/`. Tests cover revocation on reused clients, no cross-user
exports, secret exclusion, immutable events, restriction, review states and retryable purge.

Final acceptance requires real local PostgreSQL, API/frontend, relevant MCP/workers, approved
Azure Foundry credentials, synthetic seeds, a final screenshot and sanitized route manifest.
No mock/intercepted response is real E2E acceptance. See `E2E_TEST_EVIDENCE_RULE.md`.

### Validation evidence, 2026-10-14

API Ruff/type checks, all eight privacy regression tests, the frontend production build,
frontend lint and all 203 frontend unit tests passed. The API suite passed with 735 tests
and five skips before the final two privacy regressions were added. Those regressions verify restricted real-provider
chat is rejected before processing, pending erasure cannot be resumed, and approved erasure
removes owned cases/files and authentication while keeping external cleanup pending.

The synthetic real local run `privacy-389-20261013T070549Z` used PostgreSQL, API 8389,
MCP 8489, frontend 5389 and Azure Foundry `gpt-4o-mini`. Its sanitized manifest records
authenticated export with four files, shared-key-only rejection, consent withdrawal blocking
another completion, actual provider/model metadata and source `issue-635-civil-code` through
MCP and the frontend. Final screenshots are `privacy-controls-final.png` and
`ai-transparency-final.png` under ignored `runs/e2e/<run-id>/`, retained at most seven days.
These checks establish privacy behavior and provenance, not legal-answer correctness.

Overall real E2E acceptance remains **pending**: the final restriction HTTP assertion needs
to target chat rather than the earlier subscription case-limit gate. A rerun on 2026-10-14
was blocked because Docker Desktop could not start and loopback PostgreSQL timed out.
The browser adapter also timed out waiting for a download event; the authenticated API ZIP
was independently verified, so browser download completion is not claimed. Cleanup of this
isolated synthetic database remains pending until PostgreSQL is available again. Engineering
merge does not approve production retention periods or certify external DSAR completion.

Regulatory references: [GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
(Articles 5, 7, 9, 10, 15, 17, 18, 20, 25, 32) and
[EU AI Act](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (transparency and applicable oversight duties).
