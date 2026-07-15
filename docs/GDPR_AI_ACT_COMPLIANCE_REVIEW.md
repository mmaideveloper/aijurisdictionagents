# GDPR + EU AI Act compliance review for Jurisdicta

Date: 2026-05-06
Scope reviewed: API (`api/aijuristiction-api`), core orchestrator (`src/aijurisdictionagents`), frontend legal pages (`frontend/aijurisdictionfronend`), infra/docs.

## What already exists (good baseline)

- API access is guarded through `x-api-key` for chat and template endpoints, reducing open exposure risk.
- There are explicit consent prompts for some sensitive external checks (entity screening, address/property lookups).
- Frontend includes privacy/legal pages and legal disclaimers.
- Observability exists and can be centrally configured, which supports auditability.

## Frontend terms-page wording review (issue #547)

The Slovak `/terms` copy was reviewed on 2026-07-15 for language quality, product naming, GDPR data-minimization guidance, and EU AI Act transparency/human-oversight messaging.

- The terms use the current `Jurisdigta AI právnik` brand and correct Slovak grammar and diacritics.
- The personal-data section directs users to the privacy page and asks them to submit only necessary data that they are authorized to provide.
- The AI-output section warns that generated content may be inaccurate, incomplete, or outdated and calls for verification and appropriate human review before legally consequential actions.
- The update deliberately does not state unverified controller identities, processors, lawful bases, transfer mechanisms, or retention periods.

This content review improves user transparency but does not close the broader technical and governance gaps documented below. The terms page is not a substitute for a complete GDPR privacy notice, and substantive legal claims still require verified owner input and legal review.

## Main compliance gaps and suggested updates

## 1) GDPR lawful basis + consent records are not centrally auditable

**Risk:** The system asks for consent in prompts, but there is no explicit, versioned, queryable consent ledger with timestamp, policy text version, and scope per tool.

**Suggested updates:**
- Add a consent ledger table (e.g., `consent_events`) with fields:
  - `user_id/session_id`, `consent_scope`, `consent_text_version`, `granted` (bool), `captured_at`, `source` (ui/api), `country`.
- Block consent-gated tools unless a valid consent record exists.
- Add revocation endpoint and runtime revocation checks.

## 2) GDPR data subject rights (access/export/delete/restrict) are incomplete for case/session artifacts

**Risk:** User profile endpoints exist, but subject-right workflows for all case artifacts, messages, generated documents, and logs are not clearly end-to-end.

**Suggested updates:**
- Add DSAR endpoints + service layer:
  - Export all personal data by user/session (machine-readable JSON + docs manifest).
  - Delete/anonymize user-associated chat/case content and generated artifacts.
  - Restrict processing flag checked by orchestration before model/tool calls.
- Add admin audit trail for DSAR actions.

## 3) GDPR storage limitation and retention enforcement need executable policy

**Risk:** Retention is mentioned in content/docs but no repository-wide retention enforcement matrix for DB rows, uploads, logs, telemetry, and generated PDFs.

**Suggested updates:**
- Create `docs/DATA_RETENTION_POLICY.md` with concrete TTLs per data class.
- Implement retention jobs (API DB + blob storage) and test coverage.
- Add per-record `expires_at` where feasible and hard-delete worker.

## 4) AI Act transparency duties for AI interaction should be explicit at API response level

**Risk:** UI legal content exists, but machine-level response metadata does not consistently include transparency fields.

**Suggested updates:**
- Add mandatory response metadata fields:
  - `ai_generated=true`
  - `model_provider`, `model_name`, `generated_at`
  - `limitations_notice`, `human_review_recommended`
- Return this for every assistant response (chat + document outputs).

## 5) AI Act risk management + human oversight controls need formalization

**Risk:** Human-review disclaimers exist, but there is no structured risk classing and escalation gates for high-risk legal actions.

**Suggested updates:**
- Introduce policy engine with risk tiers (low/medium/high) for intents.
- For high-risk intents (filings, hard legal recommendations):
  - require explicit user confirmation,
  - enforce human-review gate before "final" documents,
  - store decision rationale in audit log.

## 6) AI Act logging/traceability should include prompt+tool provenance controls

**Risk:** Current telemetry is operational, but compliance traceability (input-output provenance, tool call basis, law-source versioning) is not consistently structured.

**Suggested updates:**
- Add immutable compliance event log for each response:
  - normalized prompt category,
  - tool calls + consent basis,
  - legal sources + `law_last_verified_at`,
  - output risk level,
  - final action flags.
- Add redaction of direct personal identifiers in observability exports.

## 7) Security of processing (GDPR Art. 32) should enforce least data in logs and encryption posture docs

**Risk:** Sensitive content may flow into logs/telemetry without documented minimization standard.

**Suggested updates:**
- Add a log redaction middleware for emails/phones/IDs/names where possible.
- Document encryption in transit/at rest and key management in one place (`docs/SECURITY_PROCESSING.md`).
- Add regression tests that assert PII redaction in logs.

## 8) Governance/docs package for audits is missing

**Risk:** Compliance evidence is scattered across README/tests/docs and hard to present during audits.

**Suggested updates:**
- Add:
  - `docs/AI_ACT_TECHNICAL_FILE.md`
  - `docs/GDPR_ROPA.md` (record of processing activities)
  - `docs/DPIA_TEMPLATE.md`
  - `docs/THIRD_PARTY_PROCESSORS.md`
- Link each control to code owners, tests, and runtime evidence.

## Recommended implementation order

1. Consent ledger + consent enforcement middleware.
2. Retention policy doc + retention workers.
3. DSAR export/delete/restrict endpoints.
4. Response transparency metadata standard.
5. Compliance event logging schema + redaction tests.
6. Governance documentation package.

## Minimal runnable example update suggestion

After implementing consent ledger + transparency metadata, update `examples/minimal_demo.py` to print:
- whether consent exists,
- which tools were allowed/blocked,
- assistant transparency metadata payload.
