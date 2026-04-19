# Document Templates API

This API adds a persistent catalog of legal-document templates that can be seeded from public source indexes,
matched against a client request, and later extended with full template bodies for contract generation.

## Purpose

The template catalog is meant to support the next step of document generation:

- keep a managed list of common legal templates per jurisdiction
- store template metadata, source URL, format, optional body, and matching keywords
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

## Source download

Template source URLs can be downloaded into runtime storage for local inspection.

Recommended runtime folder:

- `runs/storage/api/template_sources/`

## Minimal runnable example

```bash
python examples/document_templates_minimal_demo.py
```

Repository default smoke demo remains available:

```bash
python examples/minimal_demo.py
```

