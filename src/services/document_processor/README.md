# Document Processor Service

This service scans uploaded case documents, extracts best-effort text, creates embeddings through the shared system embedding configuration, stores the full document text/vector plus chunk text/vector records, and marks each document as `processed` or `failed`.

Current extraction behavior:

- Plain-text formats are decoded directly.
- PDFs first use embedded text extraction (`pypdf`).
- If a PDF appears scanned/image-only, the service falls back to OCR using `RapidOCR` over rendered PDF pages.
- PDF visual rendering uses Poppler's `pdftoppm` first. If Poppler is unavailable, the service falls back to PyMuPDF rendering for local compatibility.
- Optional OCR libraries are loaded dynamically at runtime so API `mypy` checks do not require third-party type stubs for `fitz`, `numpy`, or `rapidocr_onnxruntime`.

Current runtime modes:

- `DOCUMENT_PROCESSOR_OPTION=api`: the API processes uploads immediately inside the API request after the file is stored.
- `DOCUMENT_PROCESSOR_OPTION=local`: legacy alias for `api`.
- `DOCUMENT_PROCESSOR_OPTION=azure`: the API leaves uploads pending and this ACA scheduled job processes them asynchronously.
- `DOCUMENT_PROCESSOR_MAX_RUNNING_TIME=<minutes>`: optional runtime cap for Azure job executions. Default is `15`; set `0` for unlimited runtime.

Embedding model env vars:

- `SYSTEM_EMBEDDING_MODEL_OPTION`: shared embedding mode switch. Use `local` for the built-in local sentence-transformer path, `cloud` to keep Azure/OpenAI embeddings.
- `SYSTEM_EMBEDDING_MODEL`: shared local embedding model name. Default: `all-MiniLM-L6-v2`. Local models are cached under `aimodels/` locally and baked into Azure worker images under `/app/aimodels` during deployment.
- `SYSTEM_EMBEDDING_DEVICE`: local embedding device selector. Default: `auto`, which tries CUDA/MPS and falls back to CPU when GPU support is unavailable or a GPU runtime error occurs.
- `AZURE_OPENAI_EMBEDDINGS_MODEL`: Azure OpenAI embedding deployment name. Recommended for Jurisdicta: `text-embedding-3-large`.
- `OPENAI_EMBEDDINGS_MODEL`: OpenAI embedding model name. Recommended default: `text-embedding-3-large`.
- Local tests and the minimal demo use `LLM_PROVIDER=mock`, which keeps embeddings deterministic and offline.
- Deployed Azure jobs default to:
- `SYSTEM_EMBEDDING_MODEL_OPTION=local`
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2`
- `SYSTEM_EMBEDDING_DEVICE=auto`
- You can still set `SYSTEM_EMBEDDING_MODEL_OPTION=cloud` explicitly to keep Azure/OpenAI embeddings
- When the Azure job runs in `local` mode, the worker no longer requires Azure OpenAI embedding settings.

## Run locally

```bash
PYTHONPATH=src python -m services.document_processor --limit 20
```

## Self-managed production server

`Deployment/server/deploy_jurisdigta_prod.sh` builds
`jurisdigta-document-processor:local` from this Dockerfile and installs a locked
cron wrapper at `/srv/jurisdigta/ops/run_document_processor.sh`.

Defaults for the self-managed GitHub `prod` deployment:

- `JURISDIGTA_INSTALL_DOCUMENT_PROCESSOR_CRON=1`
- `JURISDIGTA_DOCUMENT_PROCESSOR_CRON_EXPRESSION=*/15 * * * *`
- `JURISDIGTA_DOCUMENT_PROCESSOR_LIMIT=20`

Server-local runtime settings remain in
`/srv/jurisdigta/secrets/jurisdigta.env`. Use
`DOCUMENT_PROCESSOR_OPTION=azure` for production so API uploads remain pending
until the scheduled worker processes them. Set
`DOCUMENT_PROCESSOR_MAX_RUNNING_TIME` to a bounded value such as `15` minutes.

Validation on the server:

```bash
docker image inspect jurisdigta-document-processor:local >/dev/null
test -x /srv/jurisdigta/ops/run_document_processor.sh
crontab -l | grep run_document_processor.sh
/srv/jurisdigta/ops/run_document_processor.sh
tail -n 80 /srv/jurisdigta/runs/logs/document-processor-latest.log
```

The worker shares the API PostgreSQL database and local file storage. Keep
uploaded document contents, extracted text, embeddings, API keys, and raw
connection strings out of logs.

## Minimal runnable example

```bash
python examples/document_processor_minimal_demo.py
```

Poppler visual render smoke demo:

```bash
python examples/poppler_pdf_render_minimal_demo.py
```

Local embedding similarity demo:

```bash
python examples/local_embedding_semantic_search_demo.py
```

Local embedding cache demo:

```bash
python examples/local_embedding_cache_demo.py
```

Startup logs now print the resolved embedding runtime before processing begins, for example:

- `[document-processor] startup embedding_option=local embedding_model=all-MiniLM-L6-v2 embedding_device=cpu`
- `[document-processor] startup embedding_option=cloud embedding_model=text-embedding-3-large`
- `[document-processor] batch_results={...}` is emitted as a single-line JSON payload so Azure Container Apps does not split one batch summary into many log rows.
- When `AZURE_MONITOR_ENABLED=true` and `APPLICATIONINSIGHTS_CONNECTION_STRING` are present on the Azure ACA job, those startup and processing logs are also exported to Application Insights under application name `document_processor`. The connection string alone does not enable export.
- Failed documents now also emit a compact per-document error line with `doc_id`, `case_id`, `original_filename`, and `error`.

## Azure Container Apps

Deploy this service as a scheduled Azure Container Apps Job so uploaded documents are processed into searchable text/vector records for each case.

GitHub Actions deployment is also available through `.github/workflows/document_processor_build_deploy.yml`.
