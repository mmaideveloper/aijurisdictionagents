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

### Console logging

- API now writes request logs to console by default (method, path, status, duration, request id).
- On startup, API prints `API Starting` with API/core version and active log level.
- API defaults `LLM_PROVIDER` to `azurefoundry` when not explicitly set.
- Set log level with `API_LOG_LEVEL` (fallback: `LOG_LEVEL`), for example:

```bash
API_LOG_LEVEL=DEBUG uvicorn app.main:app --reload --port 8080
```

Required env vars for default Azure Foundry provider:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- one of: `AZURE_OPENAI_API_KEY` or `AZURE_OPENAI_AD_TOKEN`

Local API startup loads the repository root `.env` automatically. If you override variables in the shell before starting `uvicorn`, those explicit shell values still win because `.env` is loaded with `override=False`.

When using API key auth, leave `AZURE_OPENAI_AD_TOKEN` unset instead of setting it to an empty string. Likewise, leave `AZURE_OPENAI_API_KEY` unset when using Entra ID auth. The shared Azure Foundry loader strips blank auth values, but direct SDK smoke scripts can fail with an invalid `Authorization: Bearer ` header when an empty token variable is present.

Optional explicit override:

```bash
LLM_PROVIDER=mock uvicorn app.main:app --reload --port 8080
```

## Run with Docker

```bash
cd api/aijuristiction-api
docker compose up --build
```

## Endpoints scaffolded

- `GET /health`
- `GET /version`
- `POST /v1/users/sign-up`
- `POST /v1/users/sign-in`
- `POST /v1/users/sign-in/phone`
- `PATCH /v1/users/{user_id}`

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

## User profile endpoints

The local API now supports simple profile management for the mobile app using the
same `x-api-key` guard as the chat endpoints.

- `POST /v1/users/sign-up`
  - request: `phone_number`, `email`, `password`, optional `first_name`, `last_name`
- `POST /v1/users/sign-in`
  - request: `email`, `password`
- `POST /v1/users/sign-in/phone`
  - request: `phone_number`
- `PATCH /v1/users/{user_id}`
  - request: `phone_number`, optional `password`, optional `first_name`, optional `last_name`
- `GET /v1/users/subscriptions/plans`
  - returns seeded plans: free, case, basic, premium
- `GET /v1/users/{user_id}/subscriptions`
  - returns subscription history for a user
- `POST /v1/users/{user_id}/subscriptions`
  - request: `plan_code`; creates a pending subscription change while old paid plan remains active
- `PATCH /v1/users/subscriptions/{subscription_id}`
  - request: `status` in (`pending`, `paying`, `paid`, `canceled`, `expired`)
  - monthly plans start a 30-day window when status changes to `paid`

These endpoints persist users through `aijurisdictionagents.api_db.ApiDatabaseStore`
and support three database modes:

- `DB_OPTION=local`: local SQLite metadata (`DB_LOCAL`, default `./databases/api.sqlite3`)
- `DB_OPTION=postgres`: local PostgreSQL for Docker-based development (`DB_CLOUD=postgresql://...`)
- `DB_OPTION=azure`: Azure Database for PostgreSQL Flexible Server (`DB_CLOUD=postgresql://...sslmode=require`)

The dedicated local PostgreSQL project now lives under `databases/README.md`.

## Case history + documents

- `GET /v1/cases/{case_id}/history?user_id=...&offset=0&limit=5` returns the selected case's persisted chat history page plus stored case-document metadata.
- `GET /v1/cases/{case_id}/documents/{doc_id}?user_id=...` downloads a previously stored case document or chat attachment.
- The mobile app uses these endpoints to show the latest 5 saved case messages after case selection and to expose case-document download buttons.

## PDF export

- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=summary` returns the session summary.
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document` now builds a document that matches the detected case topic instead of always returning a lease template.
- Direct `POST /v1/chat/sessions/{session_id}/reply` sessions also persist a session result now, so the mobile `Real Agent` flow can download PDFs without going through the simulator stream.
- In `Real Agent` mode, the lawyer can first ask whether a formal document should be prepared as PDF; once the user confirms, the next direct reply marks `metadata.document_ready=true` in `GET /v1/chat/sessions/{session_id}/result`.
- For Slovak and other Central European locales, the exporter uses a Unicode TrueType font when available so characters such as `á`, `č`, `ľ`, `ô`, and `ž` render correctly in the generated PDF.

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

- API enables CORS for local development origins by default:
  - `http://localhost:8090`
  - `http://127.0.0.1:8090`
  - `http://localhost:7357`
  - `http://127.0.0.1:7357`
- Override allowed origins with `CORS_ALLOW_ORIGINS` (comma-separated), for example:

```bash
CORS_ALLOW_ORIGINS=http://localhost:8090,http://127.0.0.1:8090,http://localhost:7357,http://127.0.0.1:7357 uvicorn app.main:app --reload --port 8080
```

## Chat simulator

The chat simulator has been moved to a separate application: `api/chat-simulator-app`.

Run it independently to test chat flows before frontend deployment.

For Slovak simulated discussions, the AI user now ends the conversation with `To je vsetko` instead of the internal sentinel word `finish`.

## OpenTelemetry

- FastAPI is instrumented with OpenTelemetry spans.
- If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces are exported to that OTLP endpoint.
- If not set, traces are written via console exporter.
- Console trace export uses a synchronous processor in local default mode to avoid shutdown-time exporter thread errors during tests.


## Database schema updates (local + cloud)

The API now applies SQL migrations during app startup for PostgreSQL/Azure, then runs the in-code bootstrap/compatibility checks. SQLite remains code-driven.

For pre-deploy validation, run from repository root:

```bash
PYTHONPATH=src python scripts/apply_db_migrations.py --project api --dry-run
PYTHONPATH=src python scripts/apply_api_db_schema.py --dry-run
PYTHONPATH=src python scripts/apply_db_migrations.py --project api
PYTHONPATH=src python scripts/apply_api_db_schema.py
```

Local PostgreSQL example:

```bash
cd databases
docker compose up -d
cd ..
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@localhost:5432/aijurisdiction STORAGE_OPTION=local PYTHONPATH=src python scripts/apply_api_db_schema.py
```

Cloud rollout:
1. Build/push/deploy API image.
2. Provision or update Azure PostgreSQL Flexible Server (`db-juris-dev` by default) through infra deployment.
3. Confirm Container App env vars: `DB_OPTION=azure`, `DB_CLOUD`, `STORAGE_OPTION`, `STORE_CLOUD`.
4. Roll out a new revision (or restart) and verify startup logs include selected `db_option`.

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
- AI user simulation normalizes non-answer outputs (questions/clarification requests) into factual continuation replies.

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
