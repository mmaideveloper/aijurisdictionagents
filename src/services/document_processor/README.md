# Document Processor Service

This service scans uploaded case documents, extracts best-effort text, stores extracted text plus vector representations, and marks each document as `processed` or `failed`.

Current extraction behavior:

- Plain-text formats are decoded directly.
- PDFs first use embedded text extraction (`pypdf`).
- If a PDF appears scanned/image-only, the service falls back to OCR using `RapidOCR` over rendered PDF pages.

Current runtime modes:

- `DOCUMENT_PROCESSOR=local`: the API processes uploads immediately inside the API request after the file is stored.
- `DOCUMENT_PROCESSOR=azure`: the API leaves uploads pending and this ACA scheduled job processes them asynchronously.

## Run locally

```bash
PYTHONPATH=src python -m services.document_processor --limit 20
```

## Minimal runnable example

```bash
python examples/document_processor_minimal_demo.py
```

## Azure Container Apps

Deploy this service as a scheduled Azure Container Apps Job so uploaded documents are processed into searchable text/vector records for each case.

GitHub Actions deployment is also available through `.github/workflows/document_processor_build_deploy.yml`.
