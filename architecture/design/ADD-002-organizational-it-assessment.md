# ADD-002: Organizational IT assessment using shared case safeguards

- Status: In Review; target implementation, not release approval.
- Date: 2026-10-15; owner: implementation maintainer.
- Upstream: [UC-003](../use-cases/UC-003-organizational-it-legal-analysis.md), [#909](https://github.com/mmaideveloper/aijurisdictionagents/issues/909).
- Decision: [ADR-003](../decisions/ADR-003-share-assessment-controls.md), Proposed.
- Profile: jurisdigta, root AGENTS.md and architecture/toolkit-profile.yaml.
- BDR: unnecessary; the stakeholder confirmed scope and existing processing policy is reused.

## Evidence and drivers

Confirmed current: app/software_assessment already provides bounded Pydantic facts,
LangGraph assessment, official provision retrieval, reference/excerpt validation,
authenticated case storage, revision checks, deletion and authorized human review.
Its intake and prompt are software-specific. The new business behavior requires
entity/purpose analysis and a jurisdiction gate, not a new processing provider.
Must: preserve software behavior, no patient-level intake, no false compliance claim,
no unsupported national-law substitution, same server contract in all scoped channels.

## Target responsibilities, boundaries and data flow

Web organizational panel / chat intake -> authenticated case API -> deterministic
IT jurisdiction/intake gate -> existing task routing and external acknowledgment ->
MCP public-topic retrieval -> local laws PostgreSQL -> source-bounded model assessment
-> existing reference validation -> case-private PostgreSQL assessment JSON -> UI.
The existing software assessment graph is parameterized by a typed IT context and
trusted IT base prompt. The stable case key is sk.it.legal_analysis and graph
provenance is organizational_it_assessment@1. Existing model task policy is reused.

The new /v1/cases/{case_id}/it-assessments resource has create/list/read/delete and
action/checklist review. ITContext fields use bounded text and countries as codes.
Storage uses existing software_assessments with kind=organizational_it or
organizational_it_chat; no SQL migration or new runtime database is needed.
History listings separate assessment kinds. Case ownership and reviewer authorization
remain authoritative. Generation/export reject IT records even via legacy endpoints.
No new cloud resources, services, environment variables or secrets are introduced.

## Failure, quality and governance scenarios

Missing facts/jurisdiction: no retrieval or model; show questions. No real provider:
fail visibly; selected-model fallback follows existing real-model policy. Unsupported
references are rejected with bounded retry and explicit incomplete status. Retention,
deletion and optimistic concurrency remain case-store responsibilities. Log static
diagnostics only; no new plaintext case/model logging. Reassessment preserves input,
prompt/version/hash, sources, date and actual provider/model route.

Purpose limitation, separate entity roles and health-data conditions are mandatory
questions. Source relevance/current applicability and legal/AI classification remain
human-reviewed; no model can mark actions verified. Non-health projects do not inherit
clinical duties simply because the test organization owns hospitals. Scope excludes
mobile, Czech national law, drafting and PDFs. Governance blocker: no release claim
without real local E2E and source review. Legal correctness is To verify per assessment.

## Delivery, validation, rollback and ownership

Add case catalog seed, typed context/intake, API aliases, web mode and conversational
adapter. Run shared regression plus new jurisdiction, authorization, consent and
reference tests; build/type-check frontend and run API CI-equivalent checks. Run
the synthetic PostgreSQL/MCP/real-model browser path and retain sanitized evidence.
No standalone C4 view needed: no service/deployment boundary changes; the flow above
answers which trust boundaries are crossed. Additional documentation is
[IT_LEGAL_ANALYSIS](../../docs/IT_LEGAL_ANALYSIS.md).

Rollback: disable sk.it.legal_analysis in the catalog and hide its workspace entry;
retain historical records for authorized read/deletion. No database rollback is
necessary. Implementation maintainer owns checks; product/legal owners retain release
and reliance decisions. Availability/cost targets are unchanged and not newly promised.
