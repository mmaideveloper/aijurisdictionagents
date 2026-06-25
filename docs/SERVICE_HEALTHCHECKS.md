# Service Health Checks

JurisDigta services use two health models. The goal is fast operational triage
without exposing personal data, legal documents, prompts, generated legal
outputs, credentials, or raw dependency errors.

## Rule For New Services

- New HTTP-serving services must expose `GET /health`.
- New worker, scheduler, or batch services must expose supervisor health plus
  freshness, heartbeat, latest run result, and sanitized error status through an
  internal/protected status path. Do not make a worker public only to add
  `/health`.
- Public health payloads must be privacy-minimized. They may include service
  name, overall status, dependency names, dependency status, and coarse backend
  names. They must not include exception traces, connection strings, tokens,
  user identifiers, emails, prompts, document text, or generated legal output.
- Critical dependency failure should return HTTP 503 for HTTP services. Optional
  dependency failure should report `degraded` in the protected aggregate status.
- Legal-risk freshness checks must stay visible to operators so stale laws,
  failed document processing, or failed email jobs can be reviewed by a human.

## Current Contracts

| Service | Contract | Exposure | Healthy Signal | Failure Signal |
| --- | --- | --- | --- | --- |
| API | `GET /health` | Public | HTTP 200, `status=ok`, `service=aijuristiction-api`, `llm.status=ok`, `database.status=ok` | HTTP 503 when the database check fails; unsupported LLM provider reports `llm.status=error` |
| MCP | `GET /health` | Public | HTTP 200, `status=ok`, `service=jurisdigta-mcp-server`, `database.status=ok` | HTTP 503 when the database check fails |
| Web frontend | `GET /health` | Public | HTTP 200 with body `ok` | Non-2xx or missing body |
| Chat simulator | `GET /health` | Local/dev | HTTP 200 health before simulator flows | Non-2xx startup failure |
| Document engine API | `GET /health` | Loopback/private network only | HTTP 200, `service=document-engine-service`, `database.status=ok` | HTTP 503 when the database check fails |
| Document engine worker | Supervisor/container state and lifecycle tests | Internal only | Worker process running and request lifecycle tests pass | Container not running, failed lifecycle tests, or protected status error |
| Laws collector | Protected `/v1/system/status`, `/version` freshness fields, logs, and metrics | Protected/internal | Recent successful run, latest processed law, next law, up-to-date terminal log | Stale run, import error, error count, or freshness SLA breach |
| Document processor | Protected `/v1/system/status`, logs, and metrics | Protected/internal | Recent scheduled run, processed/failed counts, sanitized summary | Stale run, repeated failure, or failed-document count breach |
| Email scheduler | Protected `/v1/system/status`, logs, and metrics | Protected/internal | Enabled/disabled state, recent run result, processed count | Stale run, SMTP/API failure, or sanitized error count |

## Minimal Verification

Run the local API health contract:

```bash
python examples/minimal_demo.py
```

Run targeted tests after health contract changes:

```bash
cd api/aijuristiction-api
ruff check app tests
mypy app
cd ../..
./conda/python.exe -m pytest api/aijuristiction-api/tests/test_health.py api/aijuristiction-api/tests/test_mcp_service.py
cd services/document-engine-service
python -m pytest tests/test_api_health.py tests/test_lifecycle.py
```

For production, keep public checks limited to externally reachable services and
verify worker health through `/v1/system/status`, Prometheus metrics, container
state, and sanitized logs.
