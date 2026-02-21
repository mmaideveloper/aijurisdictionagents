# aijuristiction-api

Dedicated API service project for exposing `aijurisdictionagents` to frontend clients.

## Azure infrastructure

Use the root `infra/` folder to provision Azure resources and deploy from local machine:

```powershell
.\infra\scripts\deploy_api.ps1 -SubscriptionId "<your-subscription-id>" -AcrName "<globally-unique-acr-name>"
```

See `infra/README.md` for full setup.

## Run locally (Conda)

From the repository root:

```bash
conda env create -f environment.yml -p ./.conda
conda activate ./.conda
cd api/aijuristiction-api
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8080
```

If the `.conda` environment already exists, skip `conda env create`.

## Run with Docker

```bash
cd api/aijuristiction-api
docker compose up --build
```

## Endpoints scaffolded

- `GET /health`
- `GET /version`

`GET /version` response includes:
- `api_version`: API package version (`api/aijuristiction-api/pyproject.toml`).
- `core_version`: core system version from installed `aijurisdictionagents` package or local `src/aijurisdictionagents/__init__.py` during monorepo development.

Example:

```json
{
  "service": "aijuristiction-api",
  "version": "0.1.0",
  "api_version": "0.1.0",
  "core_version": "0.1.0"
}
```

## Version bump workflow

When API code changes:
1. Bump `version` in `api/aijuristiction-api/pyproject.toml`.

When core (`/src`) code changes:
1. Bump `__version__` in `src/aijurisdictionagents/__init__.py`.
2. Bump `[project].version` in root `pyproject.toml`.

## Swagger and authentication

- Swagger UI (local): `http://localhost:8080/docs`
- OpenAPI JSON (local): `http://localhost:8080/openapi.json`
- Chat endpoints under `/v1/chat/*` require header:
  - `x-api-key: aijuris` (currently hardcoded for initial integration)

Example:

```bash
curl -X POST "http://localhost:8080/v1/chat/sessions" \
  -H "Content-Type: application/json" \
  -H "x-api-key: aijuris" \
  -d "{}"
```

## Chat simulator (test app for frontend integration)

Use the lightweight simulator page to exercise chat endpoints before deploying frontend changes. The page is now implemented as a maintainable template + static assets bundle:

- URL: `http://localhost:8080/chat-simulator`
- Features:
  - Create a session (`POST /v1/chat/sessions`)
  - Send messages (`POST /v1/chat/messages`)
  - Refresh conversation history (`GET /v1/chat/sessions/{session_id}/messages`)
  - Clear current session state without reloading the page
  - Override API base URL and API key for remote environment testing

Minimal runnable example:

```bash
cd api/aijuristiction-api
uvicorn app.main:app --reload --port 8080
# open http://localhost:8080/chat-simulator
```

## OpenTelemetry

- FastAPI is instrumented with OpenTelemetry spans.
- If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces are exported to that OTLP endpoint.
- If not set, traces are written via console exporter.

## Build + deployment workflow

GitHub workflow: `.github/workflows/api_build_deploy.yml`

- CI checks: install deps, lint (`ruff`), type-check (`mypy`), tests (`pytest`), and Docker build.
- Deploy path: on manual dispatch with `deploy=true`, push image to Azure Container Registry and deploy/update Azure Container App.

Required GitHub Environment variables:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_APP_NAME`
- `AZURE_CONTAINER_REGISTRY`

The workflow dispatch input `github_environment` selects which GitHub Environment
supplies these variables.
`AZURE_CONTAINER_REGISTRY` should be the registry name (example: `arcjuris`).
The workflow also normalizes values like `arc-juris.azurecr.io` to `arcjuris`.

For Azure OIDC federation setup (GitHub -> Entra app federated credential for
`AZURE_CLIENT_ID`), see `infra/README.md` section `GitHub workflow deployment setup (OIDC federation)`.

## E2E testing recommendation

Because you are familiar with Playwright, use **Playwright API testing** (`APIRequestContext`) for API E2E:

1. Run tests from `e2e-playwright/` (API auto-start is enabled by default).

```bash
cd api/aijuristiction-api/e2e-playwright
npm install
npx playwright test
```

Playwright auto-start details:
- Default behavior: starts API before tests when `API_BASE_URL` is not set.
- If `API_BASE_URL` is set, Playwright targets that URL and does not auto-start local API unless `PW_START_API=1`.
- Python resolution order for local API start:
  1. `API_PYTHON`
  2. repo local `.conda` interpreter
  3. `python`/`py` from PATH

Run only the chat simulation test:

```bash
cd api/aijuristiction-api/e2e-playwright
API_KEY=aijuris npx playwright test tests/chat.spec.ts
```

On Windows PowerShell:

```powershell
cd api/aijuristiction-api/e2e-playwright
$env:API_KEY="aijuris"
npx playwright test tests/chat.spec.ts
```

This approach keeps one tool for UI + API E2E while still allowing pytest integration tests for backend internals.

### Behavior when API is not running

Playwright E2E tests target a live API and fail fast if the API is unavailable.

- When auto-start is enabled and Python is missing, run fails immediately with startup error.
- When targeting an external `API_BASE_URL`, each test checks `/health` and fails with connection details if unavailable.
- To tune readiness probe timeout, set `API_HEALTH_TIMEOUT_MS` (default `2000`).


## Current Task #7 progress

- Subtask 1 complete: architecture RFC + ADR (`docs/API_ARCHITECTURE_RFC.md`, `docs/adr/ADR-0001-api-framework-and-streaming.md`).
- Subtask 3 started: in-memory session/message domain model and initial chat endpoints.

New endpoints:
- `POST /v1/chat/sessions`
- `POST /v1/chat/messages`
- `GET /v1/chat/sessions/{session_id}/messages`
