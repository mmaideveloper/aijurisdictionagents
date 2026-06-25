# Services

Standalone microservices live in this folder.

## Document Engine Service

Asynchronous document request processor:

- API creates rows in `document_requests` with `status = new`.
- Worker claims rows and changes status to `in_progress`.
- Worker finishes as `finished`, or stores `error` plus `error_message` and `correlation_id`.

Run with Docker Compose:

```bash
cd services/document-engine-service
docker compose up --build
```

See `services/document-engine-service/README.md` for API examples, Docker, Kubernetes manifests, and production settings.
