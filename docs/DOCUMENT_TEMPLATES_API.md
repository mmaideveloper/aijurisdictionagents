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

For generated court-facing or third-party organization output documents, the API applies the
Jurisdicta default corporate template:

- branded Jurisdicta header block
- right-aligned corporate contact details
- clean divider line and centered document title
- same API/Core export footer metadata for traceability

Internal workflow-style outputs (for example legal summary / next-step memorandum style drafts) and
discussion summaries intentionally keep the plain PDF style without the corporate template.

## PDF Preview

The template preview endpoint renders one template directly through the same PDF builder used by chat document
exports. It fills known placeholders with realistic sample data, returns `application/pdf`, and uses a
`Content-Disposition` filename ending in `-preview.pdf`. Preview PDFs use the Jurisdicta A4 corporate
layout with the logo block, contact panel, blue sidebar, and API/system version block from
`docs/generated_document_template.png`.

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
