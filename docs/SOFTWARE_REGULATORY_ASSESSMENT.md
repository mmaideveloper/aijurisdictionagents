# Software regulatory assessment (issue #896)

The implementation provides an explicit case-private assessment workspace and a
dedicated LangGraph runtime. It does not certify software or establish complete
legal-source coverage. Real-provider acceptance evidence is recorded separately.

## Scope
Slovakia and EU; all software with a medical/IVD specialist path. Initial channels
are web, API and chat simulator, with shared server assessment and PDF contracts.
Mobile is a follow-up. Case-specific editable prompts and model routing must obey
existing versioning, publication, external-processing and human-review controls.

## Evidence and action contract
Every assessment records its confirmed facts, missing facts, document versions,
flow/prompt versions and actual model route. Every finding carries an immutable
identifier, classification (suspected gap or missing evidence),
source document/version/location and exact supporting excerpt. PDF page numbers
must come from extraction metadata; flattened text cannot establish a page number.
Unknown locations and OCR uncertainty remain explicit.

Each action links the relevant retrieved original legal provision, applicability
rationale, source date, priority and responsible party to a mitigation and evidence
or verification plan. Model-produced source IDs and document excerpts must be
validated before presentation. Legal quotations come directly from retrieved
provisions on the server, never from generated text; longer quotes are marked
as truncated previews. A phone number
alone never establishes a GDPR violation. Risk-based encryption recommendations
must account for processing context, access controls and other safeguards.

States: open -> evidence requested -> ready for review -> verified.
Verification requires an authorized reviewer and records the evidence reviewed.
Reassessment preserves separately selectable history. Reviewers compare results
and track resolved, remaining and new gaps; automatic cross-version reconciliation
is not provided in this release.

## Initial implementation review
Existing case_types supports editable prompts and linked templates. Flow packages
and registered case workflows provide facts, interrupts, publication and review.
Task routing policies support provider/model selection with external acknowledgment
and EU-data-zone policies. Existing document_review authenticates users, checks
case access, validates proposals against source IDs and exact original text.
The assessment extracts embedded PDF text from the original bytes to preserve
page numbers. DOCX/text have paragraph references; images/scanned pages without
embedded text are explicitly unreadable. No page numbers are inferred from
flattened text. Limits are 10 files, 20 pages per PDF, 100,000 total characters,
12,000 characters per evidence section and 200 sections. Oversized evidence fails
visibly instead of silently truncating the assessment.

## Using the workspace
Create/select a case in the web assistant, expand **Software regulatory assessment
· SK + EU**, enter the description and intake facts, select original uploads and
acknowledge external AI processing where required. Unknown answers produce
questions, not inferred facts. Run assessment again after confirming facts or
replacing documents. Previous assessments remain separately selectable.

Findings show document version/page/paragraph, excerpt, official legal source,
priority, action, owner and verification. Supply an evidence/reviewer note before
changing action status; **verified** requires **ready for review** first. Supplier
items require receipt before review. Select recommended documents to generate a
short working draft, edit/save it and download the revision-bound PDF. Draft edits
retain previous text and reviewer metadata. PDFs always carry review limitations.
Model output gets one bounded retry for schema/evidence mistakes. If a structured
result still contains unsupported items, only independently validated actions,
applicability entries, supplier requirements and linked verification plans survive.
The result is explicitly incomplete and gains a release blocker reporting the
omitted item count. No citation is repaired by substituting an ID or changing a
quote, and an unsupported violation is never relabelled as a valid finding.

The simulator links to `/static/software-assessment.html`. Sign in with an actual
device session (including OTP/MFA where required), select an existing private case,
upload synthetic documents and run the same API assessment. Its diagnostic result
is text-only JSON; detailed review/edit controls are in the web workspace/API.
It does not store tokens/passwords in browser storage. Mobile is outside this release.

## API and administration
All endpoints require `x-api-key`, `x-jurisdigta-device-id`,
`x-jurisdigta-device-token`, `user_id` and case access. Mutation also requires the
existing case write window. Base: `/v1/cases/{case_id}/software-assessments`.

| Endpoint | Purpose |
| --- | --- |
| GET / POST base | List or create an assessment; UUID request ID provides retry idempotency |
| GET / DELETE `/{assessment_id}` | Fetch or delete case-private results |
| PATCH `/{assessment_id}/actions/{action_id}` | Review status with expected revision and evidence note |
| PATCH `/{assessment_id}/supplier-checklist/{index}` | Record supplier receipt/review |
| POST `/{assessment_id}/drafts` | Explicitly draft a recommended document |
| PATCH `/{assessment_id}/drafts/{index}` | Save user-edited draft with expected revision |
| GET `/{assessment_id}/export?revision=N` | Export assessment and drafts as a server-rendered PDF |

`facts` contains description, intended_purpose, users, lifecycle, role, suppliers
and nullable flags personal_data, health_data, uses_ai, medical_purpose,
specimen_analysis and automated_decisions. POST also accepts selected document UUIDs,
external_acknowledged and optional selected_model_profile_id. Revision conflicts,
changed evidence, unavailable routes and validation failures remain visible.

Admins edit the case prompt through the existing case catalogue:
`sk.software.regulatory_assessment` / jurisdiction `SK`. Upgrades add missing seeds
but preserve custom prompts and disabled/deleted states. Assessments pin prompt ID,
update timestamp, hash and `software_regulatory_assessment@1` graph.
Configure existing model route policies for task type `software_regulatory_assessment`.
Provider permissions/EU routing/external acknowledgment remain enforced.
An unavailable or disallowed user selection can use only the independently
authorized default route, with disclosure. Case authorization and default-route
processing/EU policies still apply; no route failure silently switches to mock.

This explicit graph is independent of automatic primary-chat routing. Existing
unreviewed case assignments continue to escalate; no flow is automatically published
or production-approved by adding this workspace.

## Source and qualification limits
MCP searches reviewed public regulatory topics, never software facts/upload text.
Only bounded complete provisions from allowed official HTTPS source hosts can
ground findings; excerpts must match supplied document and legal evidence exactly.
No sources or missing intake facts prevents a model assessment. Source metadata
records original document ID, version and effective date when present; legal
freshness/coverage still requires expert review. Missing EU/national medical corpus
coverage must be treated as an evidence gap, not a negative applicability decision.
Guidance/standards, when recommended, are not automatically binding legislation.

## Storage and deletion
Migration `databases/api/migrations/20261012_software_assessments.sql` adds case-bound
assessment JSON and selected-document relations. SQLite uses the matching core
initializer. Runtime data remains in existing API storage. Removing an evidence
document purges every assessment referencing it, including drafts/review notes;
case deletion also purges assessments. Explicit assessment DELETE is available.
Existing case retention governs remaining artifacts; no new secret/environment key.

## Required outputs
- Applicability register with source coverage and effective-date uncertainty.
- Supplier checklist separating legal, contractual and recommended evidence.
- Risk/action register with document and legal traceability.
- Verification plan separating tests, document review and clinical/performance evidence.
- User-selected concise documentation drafts and PDF exports.
- Responsibility map, architecture alternatives, release blockers and change impacts.

## Privacy and operations
Use case authorization, confidential storage and existing deletion/retention controls.
Do not require patient records. Treat uploads as untrusted evidence, not instructions.
Log metadata and provenance without document text, prompts, credentials or personal data.
Legal/medical conclusions require appropriate expert review; no automatic certificate.
SQL assets belong under databases/<projectname>; runtime storage under
runs/storage/<projectname>. No new environment setting is assumed in this design.

## Validation and acceptance
Exercise non-medical, AI, medical and IVD synthetic scenarios, evidence mismatch,
page provenance, injection, source gaps, authorization, revisions and reassessment.
Final acceptance requires local frontend/API/MCP/relevant services, migrated and
synthetically seeded PostgreSQL and the configured real model. Retain a sanitized
manifest and final screenshot; exported PDFs also need structure/text checks and
first-page rendering per docs/E2E_TEST_EVIDENCE_RULE.md. Evidence is transient,
ignored and subject to that rule's retention policy. Missing prerequisites leave
final E2E pending.

Issue #896 was exercised through the real local frontend, API, MCP and isolated
PostgreSQL databases with Azure Foundry `gpt-4o-mini`. Synthetic scenarios covered
non-medical software, AI, medical software and IVDR, page-2 evidence, all four
specialist source paths, visible real-model fallback, short draft generation and
saved draft edits. PDF structure/text checks and first-page visual inspection passed.
These synthetic law fixtures prove workflow grounding, not substantive legal
accuracy or completeness of the deployed legal corpus. Supplier checklist items
can offer working-outline drafts when the model omitted document suggestions;
these outlines do not replace actual supplier evidence.

Minimal runnable intake example (offline, synthetic, no provider call):
`python examples/minimal_demo.py`.

Focused checks: `python -m pytest api/aijuristiction-api/tests/test_software_assessment.py`
and `scripts/validate_api.ps1`; frontend `npm test` / `npm run build` / `npm run lint`.
Real local fixture: bootstrap the approved credential using the documented helper,
create isolated API/laws PostgreSQL databases, run
`python scripts/run_issue_896_e2e.py --prepare`, then
`python scripts/run_issue_896_e2e.py`. This uses real Azure Foundry and MCP, synthetic
data and local synthetic authentication. The seeded law is clearly marked **NOT
actual legislation** and validates retrieval/traceability only. Retain sanitized
results, screenshot, PDF and first-page render under ignored `runs/e2e/issue896` for
at most seven days. Clean synthetic cases and uploaded files after evidence capture.
