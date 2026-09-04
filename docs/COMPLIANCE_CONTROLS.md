# Consent, DSAR, retention, and AI-transparency controls

Issue #389 introduces a central compliance boundary shared by API database backends.

## Consent

`consent_events` is a versioned decision ledger. Supported scopes are `data_processing`,
`external_model`, `external_check`, `marketing`, and `sensitive_processing`. Revocation appends a new
negative decision linked to the previous event; it never rewrites history. Active consent is the latest
decision for the scope, with optional notice-version and expiry checks.

External model routing now fails with HTTP 403 unless the user has active `external_model` consent.
Processing restriction fails with HTTP 423 before any model client is selected. Optional workflow tools
retain their run-bound policy consent and also require a matching central `external_check` decision.

## Data minimization and traceability

`compliance_events` contains a one-way subject reference, event/action/outcome, correlation ID, bounded
allowlisted metadata, and a hash link to the previous event. SQLite and PostgreSQL reject update/delete
operations on the table. Metadata keys associated with prompts, document text, content, names, contact
details, credentials, or tokens are discarded before persistence.

This ledger is evidence of system actions, not a copy of the user's legal matter. Detailed personal data
is returned only in the subject's DSAR export and is not written into operational logs.

## AI transparency

Every completed chat result includes `metadata.ai_transparency` with:

- `ai_generated`, `model_provider`, `model_name`, and `generated_at`;
- a limitations notice and `human_review_recommended=true`;
- source and tool provenance arrays when available.

Direct chat reply responses expose the same object in message metadata. Generated single-document PDF
responses include CORS-visible `X-AI-*` and human-review headers; the PDF's existing disclaimer and
human-review presentation remain in place. These fields describe the effective route, including
deterministic JurisDigta logic, rather than a user-requested but unused model.

## Human oversight

The controls do not make legal decisions or certify documents. Legal-risk output remains a draft,
requires human review, and preserves source provenance. Destructive DSAR and retention operations require
explicit confirmation. Production deployment remains blocked until privacy/legal owner approval and the
real local PostgreSQL E2E evidence required by `docs/E2E_TEST_EVIDENCE_RULE.md` are complete.
