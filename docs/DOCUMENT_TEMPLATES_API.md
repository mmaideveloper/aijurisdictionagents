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

## Storage

Runtime data uses SQLite under repository runtime storage:

- default: `runs/storage/api/sqlite/document_templates.sqlite3`
- override env: `API_DOCUMENT_TEMPLATES_SQLITE_PATH`
- when `DB_OPTION=postgres|azure`, the store uses `DB_CLOUD`

SQL asset:

- `databases/api/document_templates_schema.sql`

Notes:

- delete is implemented as soft delete
- templates can exist with metadata-only seed rows first (`body` can stay empty)
- later updates can attach a full template body and richer source references

## Endpoints

All endpoints require `x-api-key`.

- `GET /v1/document-templates?include_deleted=false&jurisdiction=SK`
- `GET /v1/document-templates/{template_key}?jurisdiction=SK`
- `POST /v1/document-templates`
- `PATCH /v1/document-templates/{template_key}?jurisdiction=SK`
- `DELETE /v1/document-templates/{template_key}?jurisdiction=SK`
- `GET /v1/document-templates/match/search?request_text=...&country=SK&template_kind=rental_agreement`
- `GET /v1/document-templates/{template_key}/preview/pdf?jurisdiction=SK`

Template payloads also support:

- `disclaimer_title`
- `disclaimer_text`
- `disclaimer_footer`

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

## Chat Export Behavior

The chat document export endpoint (`GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document`)
now recognizes visible Slovak rental-package sections such as:

- `Zmluva o nájme bytu`
- `Inventárny zoznam`
- `Potvrdenie o prevzatí bytu` / odovzdávací protokol

When at least two separate package documents are detected, the endpoint returns a ZIP archive instead of
collapsing the package into one PDF. Slovak rental export text is generated with UTF-8 Slovak literals and the
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

Generate one sample third-party corporate PDF output:

```bash
python examples/document_template_pdf_sample_demo.py
```

Repository default smoke demo remains available:

```bash
python examples/minimal_demo.py
```
