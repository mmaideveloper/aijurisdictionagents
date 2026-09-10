# Combined document review (#800, incorporating #623)

## Use case and architecture decision

Canonical records: [UC-002](../architecture/use-cases/UC-002-review-uploaded-legal-document.md)
and [ADR-002](../architecture/decisions/ADR-002-case-document-review-revisions.md).

An authenticated case owner uploads a PDF, DOCX, JPEG or PNG, checks extracted
text, explicitly requests Slovak legal review, and accepts or rejects proposed
changes before downloading a separate revision. Existing server document consumers
share the legal-basis representation; mobile and simulator need no separate resolver.

Decision: reuse the case document processor, embeddings, database model router and
MCP law corpus. Keep originals immutable. Persist structured proposals and decisions
against the original content hash using optimistic concurrency. Export from the same
accepted text used by the preview. A replacement whole document without individual
decisions would lose user oversight and is rejected.

Personal documents and vectors remain case-private. Derived review records follow
document/case deletion through foreign keys. External processing requires the existing
route acknowledgement. No autonomous legal decision or assertion of legal validity
is introduced. Source freshness and applicability must be supported by source metadata,
not by a model's confidence or by the document title. Unverified legal basis carries
the explicit human-review warning. Public legal searches must not contain personal
contract text. Treat uploaded text as data, never tool instructions.

Limits: 20 MiB per upload, 20 PDF pages, 25 million image pixels, 40 MiB expanded
DOCX XML. DOCX macro/embedded-object content is not executed. Unsupported, encrypted,
empty or unreadable inputs fail visibly. OCR text requires user inspection.

Validation: focused parser/revision tests followed by the real local frontend/API/
MCP/PostgreSQL/worker path with synthetic records and a configured real model.
Keep final screenshots, DOCX/PDF, rendered first PDF page and sanitized provider/source
manifest under ignored runs/ or artifacts/; follow docs/E2E_TEST_EVIDENCE_RULE.md.
Missing prerequisites leave real E2E pending. Default example remains
`python examples/minimal_demo.py`.

## API and frontend

From a case's document list, open an uploaded document in the signed-in tab, inspect
extracted text, add missing facts, and explicitly request review. The external-route
acknowledgement is initially unchecked. Accept or reject each proposed paragraph change.
Reload preserves decisions. DOCX/PDF download requires decisions on all proposals and
the current revision. Neither an empty proposal list nor source verification guarantees
legal correctness.

`GET/POST /v1/cases/{case_id}/documents/{doc_id}/review` reads extraction or creates
a review. `PATCH .../review/{review_id}` takes `expected_revision` and a map of change
IDs to `accepted`, `rejected`, or `pending`. `GET .../review/{review_id}/export` takes
`revision` and `format=docx|pdf`. All review routes require the existing API key and
`x-jurisdigta-device-id` / `x-jurisdigta-device-token` for the specified user, plus case
ownership. Unknown changes, stale revisions and unavailable extraction fail closed.
Responses include server-authoritative `preview_text`; the same text drives downloads.

POST accepts a client `request_id` UUID. Reuse it when retrying the same request;
the server returns the existing review and retains decisions. Use a new UUID for a
new review. Model proposals include exact original paragraph text and integer section
numbers. A mismatch, unknown source, overlapping edit or unsupported section fails
validation before persistence. Semantic context paths include chunk and extracted
paragraph ranges. OCR marks low-confidence lines for explicit source inspection.

`source_verified` means the cited section exists in the selected current-effective
corpus version. It does not establish official-source freshness or applicability.
Those limitations remain visible as `Právny základ vyžaduje odborné overenie`.
Numeric verification scores on unverified generated PDF exports are reduced to zero;
an unavailable score remains unavailable. The resolver verifies explicitly declared
act/provision pairs rather than guessing a legal regime from the document title.

DOCX revisions preserve the source paragraph/table hierarchy when extraction can
be mapped unambiguously. Ambiguous mappings fail visibly rather than changing the
wrong clause. Exports do not copy macros, remote relationships or embedded objects.
PDFs and image-origin DOCX exports use extracted reading order; pixel-identical
layout and Word's native tracked-changes format are not supported. The web preview
supplies the structured change display.

## Local validation

Focused offline example: `python examples/document_review_minimal_demo.py`.
It writes a synthetic DOCX under ignored `runs/document-review-demo/`.
Real-source seed helper: `python scripts/seed_document_review_e2e.py`, with an explicit
loopback `LAWS_DB_CLOUD` targeting a `review_800` database and real local embeddings.
The helper uses an obviously synthetic 9876/2026 law; never load it into production.
Remove the seed by deleting its recorded law document ID in the designated test DB;
foreign keys cascade its versions, provisions, metadata and source artifact.
Remove synthetic users/cases and generated files after evidence review. Keep sanitized
evidence for at most seven days, then delete the task's evidence directory.

When passing an explicit database URL to the approved credential-import helper, its
startup preflight now uses that named loopback database too. It must not migrate the
shared default database before using the isolated test database.

## Validation evidence (10 September 2026)

The real local frontend on port 5180, API on 8180 and internal MCP on 8170 used
isolated PostgreSQL databases `juris_review_800` and `laws_review_800`, current
migrations, in-process document processing, and approved Azure Foundry `gpt-4o-mini`.
Actual local `all-MiniLM-L6-v2` embeddings have 384 dimensions; cached model execution
was used, without mock embeddings or intercepted API responses.

- Uploaded DOCX, PNG, JPEG and scanned PDF through the signed-in frontend. OCR
  preserved the 100 EUR amount, law identifier and 30-day payment clause.
- The frontend question retrieved uploaded clauses and the MCP-seeded synthetic
  9876/2026 source; the visible answer distinguished 30 days in the contract from
  15 days in the synthetic law and displayed its source/version citation.
- A real model review returned a source-grounded change. Rejection retained original
  wording after reload; acceptance persisted and appeared in both DOCX and PDF.
- The original DOCX remained byte-for-byte unchanged. Export text and PDF structure
  were checked; the one-page PDF was rendered and visually inspected.
- A second authenticated synthetic user could not review the first user's document
  (404). Actual PostgreSQL deletion removed a source's derived review/text/vectors,
  and subsequent semantic retrieval omitted the deleted document.
- API lint/type-check and full unit suite passed (two existing skips); focused
  parser/revision tests passed. Frontend lint had no errors, build passed and all
  157 frontend tests passed. Existing React-refresh and bundle-size warnings remain.

Sanitized local evidence: `runs/document-review-800/manifest.json`,
`accepted-preview.png`, `rejected.png`, `semantic-law-answer.png`,
`image-extraction.png`, `accepted.docx`, `accepted.pdf`, `accepted-first-page.png`.
The fictitious law is a test fixture, not evidence that the live official Slovak
corpus is complete or current. Source freshness/applicability remain qualified.
Retain evidence for seven days at most. Task databases were removed after validation;
cleanup of remaining synthetic source files was rejected by automatic execution policy.
Those files remain under ignored task storage with the same maximum seven-day retention.
Reproduction requires reseeding and the approved credential helper.

## Screenshot acceptance follow-up (10 September 2026)

The upload button now includes a visible upload icon. The review displays its
persisted version beside the change controls and in the side-by-side original/new
preview. The new pane includes only accepted changes and the server legal basis.

A fresh synthetic run recreated the isolated databases above and used the approved
real Azure Foundry model. DOCX, PNG and scanned PDF uploads all reached `processed`.
Rejection persisted as v2 with the original 30-day clause; acceptance persisted as
v3 with 15 days in the revised pane and 30 days in the original pane. Both controls
remain available for reconsideration. The original bytes stayed unchanged; v3
DOCX/PDF exports contain the expected amount, revised clause and source citation.
The one-page PDF was rendered and visually checked.

Evidence is under ignored `runs/document-review-screenshots-20260910/`:
`01-upload.png`, `02-uploaded-files.png`, `03-approved-v3.png`,
`04-rejected-v2.png`, `accepted-v3.pdf`, `accepted-v3.docx`,
`accepted-v3-first-page.png` and sanitized `manifest.json`.
The same seven-day retention applies. This follow-up leaves its isolated local
services/databases available for inspection; it does not deploy or publish data.

The complete root test suite passes (316 passed, two skips), including regression
checks that same-name uploads preserve both files, processor errors omit raw
exception messages, and court PDF enrichment receives an actually readable PDF.
All 157 frontend tests, frontend lint (existing warnings only), production build,
and both minimal examples pass.
