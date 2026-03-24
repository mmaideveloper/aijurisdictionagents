# Document Processor Service

This service scans uploaded case documents, extracts best-effort text, creates real embeddings through the configured provider, stores the full document text/vector plus chunk text/vector records, and marks each document as `processed` or `failed`.

Current extraction behavior:

- Plain-text formats are decoded directly.
- PDFs first use embedded text extraction (`pypdf`).
- If a PDF appears scanned/image-only, the service falls back to OCR using `RapidOCR` over rendered PDF pages.
- Optional OCR libraries are loaded dynamically at runtime so API `mypy` checks do not require third-party type stubs for `fitz`, `numpy`, or `rapidocr_onnxruntime`.

Current runtime modes:

- `DOCUMENT_PROCESSOR_OPTION=local`: the API processes uploads immediately inside the API request after the file is stored.
- `DOCUMENT_PROCESSOR_OPTION=azure`: the API leaves uploads pending and this ACA scheduled job processes them asynchronously.

Embedding model env vars:

- `AZURE_OPENAI_EMBEDDINGS_MODEL`: Azure OpenAI embedding deployment name. Recommended for Jurisdicta: `text-embedding-3-large`.
- `OPENAI_EMBEDDINGS_MODEL`: OpenAI embedding model name. Recommended default: `text-embedding-3-large`.
- Local tests and the minimal demo use `LLM_PROVIDER=mock`, which keeps embeddings deterministic and offline.

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
