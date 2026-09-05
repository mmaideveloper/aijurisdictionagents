# Document Templates API

This API adds a persistent catalog of legal-document templates that can be seeded from public source indexes,
matched against a client request, and later extended with full template bodies for contract generation.

## Purpose

The template catalog is meant to support the next step of document generation:

- keep a managed list of common legal templates per jurisdiction
- store template metadata, source URL, format, optional body, matching keywords, and legal disclaimer text/footer
- allow add/update/delete without editing application code
- support request-to-template matching before rendering a concrete contract

The initial seed now contains the user-provided Slovak template groups:

- Obchodne a spolocenske zmluvy
- Pracovne a personalne dokumenty
- Sudne podania a konania
- Plne moci a autorizacie
- Nehnutelnosti a najom

It now also seeds a deterministic snapshot of the direct template/form entries listed on the Ministry of Justice SR page
`https://www.justice.gov.sk/sluzby/vzory-a-formulare/vzory-pre-fo-a-po/` as reviewed on August 14, 2026.
This import boundary intentionally excludes nested external subcatalog contents such as `eZaloby`, `spravcovia`,
or other linked collections that require opening a second index page.

## Storage

Runtime data uses SQLite under repository runtime storage:

- default: `runs/storage/api/sqlite/document_templates.sqlite3`
- override env: `API_DOCUMENT_TEMPLATES_SQLITE_PATH`
- when `DB_OPTION=postgres|azure`, the store uses `DB_CLOUD`

SQL asset:

- `databases/api/document_templates_schema.sql`
- production Postgres migration: `databases/api/migrations/0019_document_templates_case_catalog.sql`

Notes:

- delete is implemented as soft delete
- templates can exist with metadata-only seed rows first (`body` can stay empty)
- later updates can attach a full template body and richer source references
- template versions also retain source profile, capture/review metadata, normalization notes, and legal-basis reference URLs; these catalog fields contain no user facts or captured third-party body content
- `body_completeness_status` explicitly distinguishes `metadata_only`, `partial_body`, and `reviewed_full_body` template versions for safe admin review and generation routing
- Ministry of Justice catalog entries use the `official_governed_form` source profile. They retain reviewed metadata and the official source, but deliberately do not generate a clause-complete substitute; their preview and disclosure direct users to the current official form and individual legal review.
- `sk.employment.employment_contract` now ships with a managed canonical body instead of metadata-only seed content
- Sprint C also supplies reviewed canonical bodies for the work-performance agreement, employee-initiated employment termination notice, and general and special powers of attorney; each records an exact reviewed source URL and retains a human-review requirement for legal-risk use
- Sprint C normalizes structured case, chat, and profile facts through template-specific aliases for those four templates. Their legally material fields are required before the template-first path can draft a final document; missing data is returned as a precise Slovak follow-up question rather than silently leaving an unresolved placeholder. The mapping is deterministic, does not infer facts, and preserves the template's visible source and human-review disclosure.
- Every template-first workflow draft now persists a fact-free provenance snapshot with its final artifact: template key, immutable template version and lineage, primary source URL, reviewed source references, and the stored human-review disclosure. This makes the exact managed template source retrievable with the output while avoiding a second copy of user facts or document content.
- as of August 29, 2026, the chat export path treats `employment_contract` as a first-class document kind and routes
  detected Slovak employment-contract exports through the managed template instead of the generic memo formatter
- the legal-document workflow `draft_documents` node now uses a template-first strategy for `Pracovna zmluva` when
  verified employment facts satisfy the managed template, and only falls back to the model path when template rendering
  is unavailable or unresolved
- the template preview endpoint now has standalone PDF fallback rendering, and the employment-template regression suite
  asserts exact reviewed-source provenance, non-empty clause-rich seed content, and filled preview output without
  metadata-only or unresolved-field fallback
- the canonical Slovak employment-contract seed contains an original reviewed body, an exact reviewed guidance URL,
  an official Slov-Lex legal-basis reference, visible draft/human-review warnings, and article/signature structure;
  startup versions only a legacy empty instance of this seed and never replaces a non-empty managed body
- the same catalog database now also stores `case_types`, `case_type_templates`, and `case_prompts`
- Postgres and Azure deployments must apply the numbered API migration stream; the document-template
  and case-catalog tables are no longer deploy-safe as runtime-only schema drift fixes

## Case Types And Prompts

The same backing catalog database now stores reusable case metadata on top of `document_templates`:

- `case_types`: stable case IDs/keys, names, short descriptions, keywords, and enable/delete flags
- `case_type_templates`: many-to-many links from a case type to zero, one, or many suitable templates
- `case_prompts`: exactly one editable stored reusable prompt per case type

Default behavior:

- every seeded template creates one seeded case type with the same title
- every seeded case type gets one generic reusable prompt
- every seeded case type gets a richer default description covering typical use, required inputs, and the linked-template expectation
- manually created case types can exist without any linked template
- startup seeding and seeded-description refresh use only each template lineage's latest active version, so historical versions cannot create duplicate case-type keys on a clean PostgreSQL database
- clean case-type seeding is batched in one transaction, and description refresh reads only the required metadata; case-type lookup connections close before prompt/template hydration, preventing PostgreSQL connection storms during startup
- linked templates can be added later without reseeding the catalog

## Endpoints

All endpoints require `x-api-key`.

- `GET /v1/document-templates?include_deleted=false&jurisdiction=SK`
- `GET /v1/document-templates/{template_key}?jurisdiction=SK`
- `POST /v1/document-templates`
- `PATCH /v1/document-templates/{template_key}?jurisdiction=SK`
- `DELETE /v1/document-templates/{template_key}?jurisdiction=SK`
- `GET /v1/document-templates/match/search?request_text=...&country=SK&template_kind=rental_agreement`
- `GET /v1/document-templates/{template_key}/preview/pdf?jurisdiction=SK`
- `GET /v1/case-types?jurisdiction=SK`
- `GET /v1/case-types/{case_type_key}?jurisdiction=SK`
- `POST /v1/case-types`
- `PATCH /v1/case-types/{case_type_key}?jurisdiction=SK`
- `DELETE /v1/case-types/{case_type_key}?jurisdiction=SK`
- `GET /v1/case-types/resolve/search?request_text=...&country=SK`

Template payloads also support:

- `disclaimer_title`
- `disclaimer_text`
- `disclaimer_footer`

## Admin Catalog View

The existing admin route at `/app/admin` now includes a read-only **Case Catalog** section that reuses:

- `GET /v1/case-types`
- `GET /v1/document-templates`

The admin UI intentionally shows only generic catalog metadata plus stored reusable prompts:

- case types and their enabled/disabled state
- linked-template visibility per case type
- document-template metadata such as title, category, kind, and source URL
- stored generic prompt text per case type

The view does not expose user-specific case data, uploaded documents, chat history, or provider secrets.
It also shows read-only template QA signals for completeness, source profile, source-capture time, and legal-review status so operators can identify metadata-only or unreviewed templates before use.

## Match behavior

The match endpoint scores templates using:

- jurisdiction
- template kind
- template title
- configured keywords

This is intended as the selection layer for future contract rendering:

1. detect the client request intent
2. find the best template candidate
3. render a concrete draft by filling placeholders from extracted facts

## Case-Type Resolution Behavior

The case-type resolve endpoint scores case types using:

- case-type name
- case-type keywords
- case-type description
- linked template titles and keywords

If no direct case-type score is found, the store falls back to template matching and then resolves the linked case type
for the matched template when possible.

This allows the system to:

1. infer which legal case the user likely wants to work on
2. retrieve the reusable prompt for that case type
3. check whether one or more suitable templates already exist in `document_templates`
4. continue gracefully even when a case type currently has no template

## Chat Export Behavior

The chat document export endpoint (`GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document`)
now recognizes visible Slovak rental-package sections such as:

- `Zmluva o nájme bytu`
- `Inventárny zoznam`
- `Potvrdenie o prevzatí bytu` / odovzdávací protokol

When at least two separate package documents are detected, including multilingual variants such as Slovak plus
English versions, the default endpoint response returns a ZIP archive instead of collapsing the package into one PDF.
If the client explicitly needs one combined PDF, call the same endpoint with `bundle=single_pdf`; each generated legal
document starts on a new page in the combined PDF. Slovak rental export text is generated with UTF-8 Slovak literals and the
Central-European PDF font profile, so headings such as `Nájomná zmluva`, `Čl. I`, `prenajímateľ`, and
`nájomca` render without mojibake.

If a chat run only asks for a single rental contract, the endpoint still returns one PDF.

For generated court-facing or client/third-party output documents, including requests such as
`potvrdenie o zaplateni`, the API applies the JurisDicta professional PDF document template:

- branded JurisDicta header/contact/sidebar layout
- formal centered document title and body typography; single-document exports use the legal document type inferred from the lawyer recommendation, not the session ID
- `potvrdenie o zaplateni` / `potvrdenie o platbe` requests are classified as payment confirmations before older
  rental or easement context is considered, so stale case memory cannot turn the export into a lease agreement or
  pre-litigation demand
- duplicate first body headings are removed when they repeat the professional PDF title
- long document titles are wrapped instead of overflowing the page
- article headings such as `Čl. I` / `Článok 1` are rendered larger and bold
- footer with a small JurisDicta logo and the document verification score when a session validation score is available
- legal-draft disclaimer page when the document verification score is unknown or lower than `DOCUMENT_SHOW_DISCLAIMER` (default `50`)
- footer QR code containing traceability metadata: generation date, API version, core
  system version, case ID, session ID when available, user ID when available, and document verification score
- case-document PDF links render only the selected generated legal-document block; conversational assistant text,
  summary bullets, follow-up prompts, raw markdown separators/bold markers, and unselected alternate-language
  document blocks are not included in the final PDF
- structured `CASE_UPDATE_JSON.case.documents` entries are treated as the source of truth for generated legal
  documents; each entry with its own `content`/`body`/`text` field is persisted and exported as the legal-document
  body even when there is only one generated document, so assistant confirmations, download status text, and
  technical payloads cannot contaminate the PDF body. Multiple entries are exported as separate generated
  documents by default, so case history, download, and email attachment flows expose all language variants
- missing party details in generated documents can be filled from the signed-in user's profile by default
  (name, address, tax number, identity card number, date of birth, and social security number); these values
  are used in the document body only and are not added to the QR payload
- lawyer prompts receive a minimal signed-in profile note with only the available client name and address, so
  chat replies do not ask again for those fields or render `[nebolo poskytnute]` when the profile already has them
- rental exports also read common draft labels such as `Podnájomník`, `Adresa nehnuteľnosti`, and
  `Mesačné nájomné` from the conversation when structured case JSON is incomplete
- generated session documents can be emailed through `POST /v1/chat/sessions/{session_id}/documents/send-email`;
  when the client omits `recipient`, the API uses the signed-in user's profile email and returns a confirmation
  response before queueing attachments; if the user corrects the recipient in chat (for example `nie na other@example.com`),
  the corrected address is confirmed and used for the queued email
- generated case documents can be emailed through `POST /v1/cases/{case_id}/documents/send-email`; generated
  documents are queued as the same rendered `application/pdf` bytes shown by the case document preview, and the
  email body includes one authenticated case deep link at `{JURISDIGTA_AGENT_BASE_URL}/case/{case_id}`
- lawyer output is validated before display so profile-backed data does not remain listed as missing; when profile
  data is missing, the user-facing note tells the user to complete Profile for future document defaults
- document processing status messages shown to clients hide internal `session-*.txt` filenames; those identifiers are
  kept in API logs for troubleshooting only
- existing case chat sessions refresh memory from prior question/answer history before asking follow-up questions, so
  already answered rental-property address and party-role questions are not repeated; if a document was already
  prepared in the case, follow-up chat does not restart intake
- prior assistant questions and user answers are summarized into the case memory prompt generally; repeated answered
  questions are removed from user-facing replies and `CASE_UPDATE_JSON.case.open_questions`
- incomplete missing-information intros are normalized so the client always sees a concrete follow-up question, using
  the first `CASE_UPDATE_JSON.case.open_questions` item when available

Internal workflow-style outputs (for example legal summary / next-step memorandum style drafts) and
discussion summaries intentionally keep the plain PDF style without the corporate template.

When no managed document-template body is available, the intended source order is:

1. Managed template catalog metadata/body for the detected document type.
2. Laws connector DB / law-citation metadata already attached to the session; exported citations are marked as
   `laws connector DB` with source score `1.0`.
3. `AIWebSearchAgent` internet source discovery only when the local laws corpus has no relevant support; external
   sources must be logged with the URL/title and source score `0.9`.

Generated document PDFs repair common UTF-8 mojibake before text wrapping/rendering, so Slovak text returned as
`PredÅ¾alobnÃ¡ vÃ½zva` is normalized before it reaches the PDF canvas.

## PDF Preview

The template preview endpoint renders one template directly through the same PDF builder used by chat document
exports. It fills known placeholders with realistic sample data, returns `application/pdf`, and uses a
`Content-Disposition` filename ending in `-preview.pdf`. Preview PDFs use the same JurisDicta
professional document layout as generated client-facing PDFs.

For Slovak templates and generated Slovak document exports, the renderer now adds a visible legal disclaimer block on
the first page and repeats a short disclaimer in the footer so the draft status is not easy to miss.

The `sk.employment.employment_contract` preview is deliberately a canonical fill-in draft rather than legal advice.
Employment salary rendering accepts values with or without the Slovak `brutto` qualifier, emits that qualifier only
once, and labels variable compensation separately from the payday. The renderer also normalizes the same two legacy
phrases in already-persisted canonical bodies, without replacing managed custom template content.
Its source alignment was reviewed on August 28, 2026 against the exact AK Samec employment-contract guidance page and
the official current Slov-Lex page for Act No. 311/2001 Coll., especially Sections 42–44. The body is original
JurisDigta text: external template wording is not copied. Bracketed fields must be completed and the result must be
reviewed by a qualified human before signature. The structured employment fact/placeholder schema is maintained as a
separate follow-up so this canonical-source change does not silently invent or persist employee facts.

As of August 29, 2026, the chat export regression suite also proves the end-to-end `GET /v1/chat/sessions/{session_id}/export`
path can take a realistic employment questionnaire, infer `employment_contract`, and render a final `Pracovna zmluva`
PDF with article-based canonical structure (`Článok I`, salary section, signature blocks) instead of a thin summary-only
layout.

Generate a synthetic, locally seeded preview and validate its extracted article/signature markers with:

```powershell
.\conda\python.exe examples\employment_contract_preview_demo.py
```

The demo writes its disposable SQLite runtime below `runs/storage/api/sqlite/`, removes it after rendering, and stores
the generated PDF under the ignored `runs/document-template-demo/` path by default.

The chat simulator now includes a **Document Templates** panel. Use **Refresh Templates** to load templates from
the selected API base URL and **Generate PDF** on any row to download that template preview. This is intended for
quick visual checks of Slovak characters, typography, spacing, and final PDF quality before using a template in a
real chat flow.

To batch-test every enabled template PDF from the command line, run:

```powershell
.\skills\testdocument\scripts\test_document_templates.ps1
```

The skill uses the same preview endpoint as the chat simulator button and writes PDFs plus `manifest.json` to:

```text
runs\testdocument\document-template-pdfs\
```

Use those PDFs to compare the final document look and feel with the expected `generate_document_template.png`
reference image when the image is present in the workspace.

## Source download

Template source URLs can be downloaded into runtime storage for local inspection.

Recommended runtime folder:

- `runs/storage/api/template_sources/`

## Minimal runnable example

```bash
python examples/document_templates_minimal_demo.py
```

Resolve a case type and inspect its linked templates/prompt:

```bash
python examples/case_types_minimal_demo.py
```

Generate one sample third-party corporate PDF output:

```bash
python examples/document_template_pdf_sample_demo.py
```

Repository default smoke demo remains available:

```bash
python examples/minimal_demo.py
```

The payment-confirmation reference case links template
`sk.civil.payment_confirmation` to flow `sk.civil.payment_confirmation@4` on
`legal_document_workflow@3`. The primary LangGraph router discovers this active published
assignment without a static case-type allowlist. The dedicated LangGraph run pins
that relationship, fills only verified facts, blocks unresolved placeholders, records MCP source
IDs, and requires human review disclosure before use. Admin Case Catalog shows the active graph,
flow lifecycle/version, validation result, and assignment history.
