# Document Processor Service

This service scans uploaded case documents, extracts best-effort text, stores deterministic vector representations, and marks each document as `processed` or `failed`.

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
