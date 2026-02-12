# aijuristiction-api

Dedicated API service project for exposing `aijurisdictionagents` to frontend clients.

## Run locally (Python)

```bash
cd api/aijuristiction-api
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload --port 8080
```

## Run with Docker

```bash
cd api/aijuristiction-api
docker compose up --build
```

## Endpoints scaffolded

- `GET /health`
- `GET /version`

## Build + deployment workflow

GitHub workflow: `.github/workflows/api_build_deploy.yml`

- CI checks: install deps, lint (`ruff`), type-check (`mypy`), tests (`pytest`), and Docker build.
- Deploy path: on manual dispatch with `deploy=true`, push image to Azure Container Registry and deploy/update Azure Container App.

Required secrets:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_APP_NAME`
- `AZURE_CONTAINER_REGISTRY`

## E2E testing recommendation

Because you are familiar with Playwright, use **Playwright API testing** (`APIRequestContext`) for API E2E:

1. Bring up the API (`docker compose up --build`).
2. Run tests from `e2e-playwright/`.

```bash
cd api/aijuristiction-api/e2e-playwright
npm install
npx playwright test
```

This approach keeps one tool for UI + API E2E while still allowing pytest integration tests for backend internals.


## Current Task #7 progress

- Subtask 1 complete: architecture RFC + ADR (`docs/API_ARCHITECTURE_RFC.md`, `docs/adr/ADR-0001-api-framework-and-streaming.md`).
- Subtask 3 started: in-memory session/message domain model and initial chat endpoints.

New endpoints:
- `POST /v1/chat/sessions`
- `POST /v1/chat/messages`
- `GET /v1/chat/sessions/{session_id}/messages`
