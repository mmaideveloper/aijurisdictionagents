# Document Processor Service

This service scans uploaded case documents, extracts best-effort text, creates embeddings through the shared system embedding configuration, stores the full document text/vector plus chunk text/vector records, and marks each document as `processed` or `failed`.

Current extraction behavior:

- Plain-text formats are decoded directly.
- PDFs first use embedded text extraction (`pypdf`).
- If a PDF appears scanned/image-only, the service falls back to OCR using `RapidOCR` over rendered PDF pages.
- Optional OCR libraries are loaded dynamically at runtime so API `mypy` checks do not require third-party type stubs for `fitz`, `numpy`, or `rapidocr_onnxruntime`.

Current runtime modes:

- `DOCUMENT_PROCESSOR_OPTION=local`: the API processes uploads immediately inside the API request after the file is stored.
- `DOCUMENT_PROCESSOR_OPTION=azure`: the API leaves uploads pending and this ACA scheduled job processes them asynchronously.

Embedding model env vars:

- `SYSTEM_EMBEDDING_MODEL_OPTION`: shared embedding mode switch. Use `local` for the built-in local sentence-transformer path, `cloud` to keep Azure/OpenAI embeddings.
- `SYSTEM_EMBEDDING_MODEL`: shared local embedding model name. Default: `all-MiniLM-L6-v2`. Local models are cached under the repo `aimodels/` folder.
- `AZURE_OPENAI_EMBEDDINGS_MODEL`: Azure OpenAI embedding deployment name. Recommended for Jurisdicta: `text-embedding-3-large`.
- `OPENAI_EMBEDDINGS_MODEL`: OpenAI embedding model name. Recommended default: `text-embedding-3-large`.
- Local tests and the minimal demo use `LLM_PROVIDER=mock`, which keeps embeddings deterministic and offline.
- Deployed Azure jobs should set `SYSTEM_EMBEDDING_MODEL_OPTION=cloud` so they keep the current cloud embedding behavior.

## Run locally

```bash
PYTHONPATH=src python -m services.document_processor --limit 20
```

## Minimal runnable example

```bash
python examples/document_processor_minimal_demo.py
```

Local embedding similarity demo:

```bash
python examples/local_embedding_semantic_search_demo.py
```

Startup logs now print the resolved embedding runtime before processing begins, for example:

- `[document-processor] startup embedding_option=local embedding_model=all-MiniLM-L6-v2`
- `[document-processor] startup embedding_option=cloud embedding_model=text-embedding-3-large`

## Azure Container Apps

Deploy this service as a scheduled Azure Container Apps Job so uploaded documents are processed into searchable text/vector records for each case.

GitHub Actions deployment is also available through `.github/workflows/document_processor_build_deploy.yml`.
