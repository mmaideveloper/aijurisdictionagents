---
name: testdocument
description: Generate PDF previews for every API document template from this repository. Use when the user asks for "/testdocument", "test document templates", "generate all document template PDFs", or wants to inspect final PDF quality and compare the rendered look and feel with the document-template reference image.
---

# Test Document Templates

## Workflow

1. Run the bundled launcher from repository root:
   `.\skills\testdocument\scripts\test_document_templates.ps1`
2. The launcher checks `http://127.0.0.1:8080/health`.
3. If the API is not healthy, the launcher starts `juris-api` with repository defaults:
   - local PostgreSQL (Docker Desktop)
   - `LLM_PROVIDER=azurefoundry`
   - API endpoint `http://127.0.0.1:8080`
4. It calls `GET /v1/document-templates?jurisdiction=SK` and then generates one PDF per enabled template through:
   `GET /v1/document-templates/{template_key}/preview/pdf?jurisdiction=SK`
5. Inspect the generated PDFs under:
   `runs\testdocument\document-template-pdfs\`

## Commands

- Generate all Slovak template previews:
  `.\skills\testdocument\scripts\test_document_templates.ps1`
- Use a different jurisdiction:
  `.\skills\testdocument\scripts\test_document_templates.ps1 -Jurisdiction CZ`
- Use an already running API without bootstrap:
  `.\skills\testdocument\scripts\test_document_templates.ps1 -SkipApiBootstrap`
- Continue after individual template failures and write a manifest:
  `.\skills\testdocument\scripts\test_document_templates.ps1 -ContinueOnError`

## Quality Check

The skill intentionally uses the production API preview endpoint instead of rendering PDFs locally. That keeps
the output aligned with the chat simulator **Generate PDF** button and the current Jurisdicta document-template
look and feel. Compare the generated files with the expected `generate_document_template.png` reference image
when that image is available in the workspace.
