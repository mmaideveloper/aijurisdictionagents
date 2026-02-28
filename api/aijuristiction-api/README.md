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

When chat simulator code changes:
1. Bump `version` in `api/chat-simulator-app/pyproject.toml`.
2. Bump `version` in `api/chat-simulator-app/app/main.py`.

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

## CORS for local simulator

- API enables CORS for local chat simulator origins by default:
  - `http://localhost:8090`
  - `http://127.0.0.1:8090`
- Override allowed origins with `CORS_ALLOW_ORIGINS` (comma-separated), for example:

```bash
CORS_ALLOW_ORIGINS=http://localhost:8090,http://127.0.0.1:8090 uvicorn app.main:app --reload --port 8080
```

## Chat simulator

The chat simulator has been moved to a separate application: `api/chat-simulator-app`.

Run it independently to test chat flows before frontend deployment.

## OpenTelemetry

- FastAPI is instrumented with OpenTelemetry spans.
- If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces are exported to that OTLP endpoint.
- If not set, traces are written via console exporter.
- Console trace export uses a synchronous processor in local default mode to avoid shutdown-time exporter thread errors during tests.

## Build + deployment workflow

GitHub workflow: `.github/workflows/api_build_deploy.yml`

Before opening a PR from a feature branch, sync it with latest `main`:

```bash
git fetch origin
git merge origin/main
```

- CI checks: install deps, lint (`ruff`), type-check (`mypy`), tests (`pytest`), and Docker build.
- Local pre-flight command to mirror CI from this folder:

```bash
ruff check . && mypy app && pytest -q
```

Typing note: keep `UserResponseProvider` and `MessageCallback` imports in `app/chat/core_runtime.py`
inside the `TYPE_CHECKING` block so both `ruff` and `mypy --strict` stay green.

Telemetry processor selection (OTLP vs console) is covered by unit tests in `tests/test_telemetry.py`.

The API `pyproject.toml` also sets `mypy_path = ["../../src"]` so strict type checks can resolve the monorepo core package during CI and local runs.
The `pytest` command is configured with `pythonpath = ["."]` in `pyproject.toml`, so direct invocation works consistently in local runs and GitHub Actions.
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
- Existing local API is not reused by default. Set `PW_REUSE_EXISTING_SERVER=1` to reuse one.
- Python resolution order for local API start:
  1. `API_PYTHON`
  2. repo local `.conda` interpreter
  3. `python`/`py` from PATH

Current E2E specs:
- `tests/health.spec.ts`
- `tests/version.spec.ts`
- `tests/chat.spec.ts`
- `tests/chat-simulator.spec.ts`
- Negative auth test in `tests/chat.spec.ts` runs only when `RUN_NEGATIVE_AUTH_TESTS=1`.

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

Run chat test with negative auth coverage enabled:

```bash
cd api/aijuristiction-api/e2e-playwright
RUN_NEGATIVE_AUTH_TESTS=1 npx playwright test tests/chat.spec.ts
```


Run the chat simulator streaming test with fixture input and uploaded txt document:

```bash
cd api/aijuristiction-api/e2e-playwright
API_KEY=aijuris npx playwright test tests/chat-simulator.spec.ts
```

The test persists question/answer review output to the Playwright test-results folder as `chat-simulator-qa.json` and attaches it to the report.

For simulator-style streaming automation, the stream payload also supports:
- `communication_minutes`: how long simulated user responses are allowed
- `user_simulation_mode`: `ReadUser` (default) or `AIUserSimulatorAgent`
- Lawyer asks about PDF export only after clarifying questions are resolved.
- In `AIUserSimulatorAgent` mode, the closing sequence is automated:
  - answer each AI agent question first
  - request PDF result
  - send thank-you
  - send `finish` to close discussion
- AI user simulation now uses full conversation context and avoids exact repeated replies across turns.

PDF export options:
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=summary` -> discussion summary PDF
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document` -> generated lawyer document PDF
- Summary PDF includes `AI Jurisdiction` branding and session metadata (session ID, country, language).
- Document PDF (`kind=document`) includes:
  - one-line header: `AI Jurisdicta Solution | Generated: <timestamp>`
  - one-line footer: `AIJ | API <api_version> | Core <core_version>`
  - right-top logo mark (`AI Jurisdicta [AIJ]`)
- Document PDF uses a formal legal-agreement structure (articles/clauses and signature fields) when generating final contract output.
- PDF filenames:
  - document/final: `{case_id}-{yyyyMMddHHmmss}-final-document.pdf`
  - summary: `{case_id}-{yyyyMMddHHmmss}-discussion-summary.pdf`

Run only the version endpoint test:

```bash
cd api/aijuristiction-api/e2e-playwright
npx playwright test tests/version.spec.ts
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
- `POST /v1/chat/sessions/{session_id}/reply` (store user message and generate immediate lawyer answer)
- `GET /v1/chat/sessions/{session_id}/messages`
- `POST /v1/chat/sessions/{session_id}/stream` (SSE streaming from core orchestrator)
- `GET /v1/chat/sessions/{session_id}/result`
- `GET /v1/chat/sessions/{session_id}/export?format=json|pdf&kind=summary|document` (`kind` applies to `pdf`)


## Minimal runnable example (streaming API + core)

Start API first, then run:

```bash
python examples/api_streaming_demo.py
```
