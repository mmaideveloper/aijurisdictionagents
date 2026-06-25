# Document Engine Service

Standalone microservice for asynchronous legal-document request processing.

## Lifecycle

1. Client creates a document request through `POST /document-requests`.
2. API stores the row in `document_requests` with `status = new`.
3. Worker claims `new` rows and moves them to `in_progress`.
4. Worker stores the generated result and sets `finished`.
5. On failure, worker sets `error`, `error_message`, and keeps `correlation_id`.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn document_engine.api:app --reload
```

Run worker in a second terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python -m document_engine.worker
```

Default local DB is SQLite at `document_engine.db`.

## Docker Compose

```powershell
docker compose up --build
```

API will be available at `http://127.0.0.1:8000`.

## Example Request

```powershell
$body = @{
  document_type = "confirmation"
  requested_by = "client@example.com"
  correlation_id = "manual-test-001"
  payload = @{
    title = "Potvrdenie"
    issuer = "JurisDigta"
    recipient = "Klient"
    facts = "Potvrdzuje sa prevzatie dokumentov."
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/document-requests `
  -ContentType "application/json" `
  -Body $body
```

Poll status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/document-requests/<id>
```

## Supported Document Types

- `confirmation`
- `power_of_attorney`
- `purchase_contract_movable`
- `purchase_contract_real_estate`

The current processor is intentionally deterministic. Replace or extend
`src/document_engine/processor.py` when plugging in JurisDigta legal checks,
LLM drafting, PDF/DOCX export, or human review.

## Kubernetes

Build and push the image, create a real `Secret` from
`k8s/secret.example.yaml`, then apply:

```powershell
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/worker-deployment.yaml
```

For production, replace `emptyDir` with object storage or a persistent volume,
and use managed PostgreSQL.

## Self-Managed Production

The main production workflow `.github/workflows/self_managed_prod_deploy.yml`
builds and starts this service from `services/document-engine-service`.

Default self-managed containers:

- `jurisdigta-document-engine-api`
- `jurisdigta-document-engine-worker`

GitHub Environment variables:

- `JURISDIGTA_DOCUMENT_ENGINE_ENABLED` defaults to `1`
- `JURISDIGTA_DOCUMENT_ENGINE_API_PORT` defaults to `8060`
- `JURISDIGTA_DOCUMENT_ENGINE_DATABASE_NAME` defaults to `document_engine`

Server-side generated documents are mounted under:

```text
/srv/jurisdigta/runs/storage/document-engine/generated-documents
```

The self-managed production API is intentionally bound to loopback only:

```text
http://127.0.0.1:8060/health
```

The health response checks database connectivity and returns only
privacy-minimized operational fields:

```json
{
  "status": "ok",
  "service": "document-engine-service",
  "database": {
    "status": "ok",
    "backend": "postgresql"
  }
}
```

If the database is unavailable, `/health` returns HTTP 503 with
`error=database_unavailable` and a sanitized message. It does not echo
connection strings, credentials, document payloads, or raw exception text.

Do not publish the document engine directly to a public hostname in the current
phase. It has no standalone end-user authentication, rate limiting, or public
audit boundary. Public document workflows should go through the main JurisDigta
API, which can enforce user auth, authorization, request validation, audit
events, and retention policy before delegating to this private service.

The document-engine worker does not expose a public HTTP health endpoint. Monitor
it through container/supervisor state, worker lifecycle tests, request status
counts, and the protected aggregate JurisDigta system status.

## Recommendations

- Keep API and worker as separate Kubernetes Deployments, even if they share one image.
- Add retry metadata before production: `attempt_count`, `max_attempts`, `next_attempt_at`.
- Add a `dead_letter` status for permanently failed jobs after retries.
- Store generated files in S3-compatible storage, not only the container filesystem.
- Add optimistic locking or `SELECT FOR UPDATE SKIP LOCKED` if worker concurrency becomes high.
- Keep `correlation_id` on every log line and external callback.
