# aijuristiction-api

## Testing

Run the API unit tests from the repo-managed Python environment:

```powershell
..\..\.conda\python.exe -m pytest tests
```

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

- API now writes request logs to console by default (method, path, status, duration, request id, correlation id, origin, user agent).
- On startup, API prints `API Starting` with API/core version and active log level.
- API defaults `LLM_PROVIDER` to `azurefoundry` when not explicitly set.
- Set log level with `API_LOG_LEVEL` (fallback: `LOG_LEVEL`), for example:

```bash
API_LOG_LEVEL=DEBUG uvicorn app.main:app --reload --port 8080
```

Required env vars for default Azure Foundry provider:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDINGS_MODEL` (embedding deployment name, recommended: `text-embedding-3-large`)
- one of: `AZURE_OPENAI_API_KEY` or `AZURE_OPENAI_AD_TOKEN`

Optional env vars for the OpenAI provider:

- `OPENAI_KEY`
- `OPENAI_MODEL`
- `OPENAI_EMBEDDINGS_MODEL` (recommended: `text-embedding-3-large`)

Local API startup loads the repository root `.env` automatically. If you override variables in the shell before starting `uvicorn`, those explicit shell values still win because `.env` is loaded with `override=False`.

Document processing mode:

- `DOCUMENT_PROCESSOR_OPTION=local`: uploaded case documents are processed immediately inside the API and stored with extracted text plus vector data.
- `DOCUMENT_PROCESSOR_OPTION=azure`: uploads stay pending until the Azure Container Apps document-processor job runs.
- Recommended deployed value: `DOCUMENT_PROCESSOR_OPTION=azure`

### Policy-driven multi-intent document task planning

The chat reply path now uses a single legal agent with a reusable policy layer for uploaded-document intents. Each matched policy contributes ordered tasks and communication rules before the legal agent is prompted.

Implementation note: the policy logic now lives in a dedicated chat service module so `app/chat/api.py` can stay focused on endpoint mapping and request/response handling.

Examples:

- `Fix uploaded document based on current law and send me summary from document`
- `Analyze uploaded agreement, rebuild outdated clauses, and summarize the result`

When the same message asks for multiple document actions, the API keeps the user's intent order and instructs the model to execute the tasks in sequence, for example:

1. review uploaded document
2. update/rebuild if current law requires it
3. prepare summary

Current built-in policies:

- `document_analysis`
- `document_modernization`
- `document_summary`

The summary step is instructed to describe the updated result when both update + summary are requested together. Future policies can add their own tasks/guidance while still using the same single-agent flow.

If summary-like output is requested before uploaded documents are processed, the policy note tells the agent to defer content-specific summary output until processed documents are available.

Minimal runnable example:

```bash
python examples/document_task_plan_demo.py
```

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

This local Docker stack now runs:

- PostgreSQL 16 with `pgvector`
- API container built from the repository root so it includes `src/aijurisdictionagents`, migrations, and scripts

Useful overrides:

```bash
API_PORT=8081 LLM_PROVIDER=mock docker compose up --build
```

The compose file stores database files under the shared repository `databases/` folder and points the API at:

- `DB_OPTION=postgres`
- `DB_CLOUD=postgresql://postgres:postgres@postgres:5432/aijurisdiction`
- `STORAGE_OPTION=local`

Do not run this stack at the same time as `cd databases && docker compose up -d` because both use the same PostgreSQL data directory.
That shared database directory is now `databases/postgress/data`.

If you want only the database container, use the dedicated project in `databases/README.md`.

## Endpoints scaffolded

- `GET /health`
- `GET /version`
- `POST /v1/users/sign-up`
- `POST /v1/users/sign-in`
- `POST /v1/users/sign-in/phone`
- `PATCH /v1/users/{user_id}`

`GET /health` now verifies the configured API database connection before returning healthy.
If the database is unreachable or misconfigured, the endpoint returns `503` with
`error=database_unavailable` and a `message` field that the mobile app can show directly.

`GET /version` response includes:
- `api_version`: API package version (`api/aijuristiction-api/pyproject.toml`).
- `core_version`: core system version from installed `aijurisdictionagents` package or local `src/aijurisdictionagents/__init__.py` during monorepo development.
- `last_law_update_date`: latest law-ingestion timestamp available to the system from the laws database. This reflects the newest law content collected by the law processor, even when the underlying LLM was trained earlier.
- `last_law_update_source`: whether that timestamp comes from country-specific or global `law_documents` data.
- `last_collector_run_at`: latest sequential laws collector run timestamp stored in `collector_progress`.
- `last_processed_law`: latest successfully processed law identifier in `number/year` format, for example `234/2026`.
- `model_knowledge_cutoff_date`: cached fallback date used when `last_law_update_date` is not available yet.
- `model_knowledge_cutoff_source`: source of that fallback date, currently the cached `MODEL_KNOWLEDGE_CUTOFF_DATE` value.
- `law_reference_links`: recent official law links available in the system knowledge store.
- `mobile_app_version`: latest mobile app version from `mobile_app/pubspec.yaml`.
- `mobile_app_release_url`: release page used by the mobile app update flow.
- `mobile_app_apk_download_url`: default APK asset URL used by Android in-app update flow.

Fallback configuration:

- `MODEL_KNOWLEDGE_CUTOFF_DATE`: manually configured cutoff date used only when `law_documents` has no imported records yet.
- `MODEL_KNOWLEDGE_CUTOFF_CACHE_FILE`: JSON cache file persisted on first startup/run so the fallback date remains stable without expiration until real law-import timestamps become available.

The API warms this snapshot during startup, so the cached fallback file is created on the initial run when the laws database is empty and `MODEL_KNOWLEDGE_CUTOFF_DATE` is configured.

Example:

```json
{
  "service": "aijuristiction-api",
  "version": "1.0.260321",
  "api_version": "1.0.260321",
  "core_version": "0.1.0",
  "last_law_update_date": "2026-03-20T00:00:00Z",
  "last_law_update_source": "law_documents_global",
  "last_collector_run_at": "2026-03-30T12:30:00Z",
  "last_processed_law": "234/2026",
  "model_knowledge_cutoff_date": "2020-12-31",
  "model_knowledge_cutoff_source": "model_knowledge_cutoff_cache",
  "law_reference_links": [
    "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/10/"
  ],
  "mobile_app_version": "0.1.5+18",
  "mobile_app_release_url": "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest",
  "mobile_app_apk_download_url": "https://github.com/mmaideveloper/aijurisdictionagents/releases/latest/download/app-release.apk"
}
```

## User profile endpoints

The local API now supports simple profile management for the mobile app using the
same `x-api-key` guard as the chat endpoints.

- `POST /v1/users/sign-up`
  - request: `phone_number`, `email`, `password`, optional `first_name`, `last_name`
  - sends a registration email notification to the new user email
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
  - queues a subscription-change email notification in the email outbox database
- `PATCH /v1/users/subscriptions/{subscription_id}`
  - request: `status` in (`pending`, `paying`, `paid`, `failed`, `canceled`, `expired`)
  - monthly plans start a 30-day window when status changes to `paid`
  - queues an email for every subscription status change (including payment failure)

### Email notification service

### Email outbox + scheduler

Emails are first persisted into a dedicated email database (`email_outbox`) and then delivered by a scheduler.

- Scheduler cadence: every 60 seconds by default (`EMAIL_SCHEDULER_INTERVAL_SECONDS`)
- Retry policy: max 2 attempts. After the second failed attempt, status changes to `failed` and scheduler skips it.
- Queue claiming uses DB-level processing state so multiple scheduler replicas do not pick the same email at once.

Email DB configuration (separate from API metadata DB):

- `EMAIL_DB_OPTION` (`local`/`postgres`/`azure`, default inherits `DB_OPTION`)
- `EMAIL_DB_LOCAL` (default `./databases/email.sqlite3`)
- `EMAIL_DB_CLOUD` (required for postgres/azure, default inherits `DB_CLOUD`)
- `EMAIL_SCHEDULER_ENABLED` (default `true`)

Postgres/Azure email schema migrations are stored under `databases/migrations/email`.

Run scheduler as a separate process (recommended for ACA split deployment):

```bash
python -m app.email_scheduler_main
```

For API-only replicas set `EMAIL_SCHEDULER_ENABLED=false`; run exactly one scheduler replica/process with it enabled.

User and subscription endpoints support email notifications with configurable transport:

- `EMAIL_TRANSPORT=log` (default): logs notifications to API logs (safe for local dev/tests)
- `EMAIL_TRANSPORT=smtp`: sends real emails via SMTP

SMTP configuration (used when `EMAIL_TRANSPORT=smtp`):

- `EMAIL_SENDER` (default: `noreply@aijurisdiction.local`)
- `EMAIL_SMTP_HOST` (default: `localhost`)
- `EMAIL_SMTP_PORT` (default: `1025`)
- `EMAIL_SMTP_USE_TLS` (default: `false`)
- `EMAIL_SMTP_USERNAME` (optional)
- `EMAIL_SMTP_PASSWORD` (optional)

Email enqueue message composition for these endpoints is centralized in `app/users/notifications.py` to keep endpoint handlers small and reduce merge conflicts with payment/subscription feature work.
- `POST /v1/users/{user_id}/subscriptions/checkout`
  - request: `plan_code`, `payment_provider` (`paypal` or `google_pay`)
  - creates a pending subscription change, sets subscription status to `paying`, and returns a fake checkout URL
- `POST /v1/users/subscriptions/{subscription_id}/confirm-payment`
  - request: `payment_id` returned from checkout
  - payment simulation rule: only user phone `+421944400166` is allowed to complete payment successfully
  - all other phone numbers receive simulated payment failure and the requested subscription is canceled (no upgrade)

### Subscription payment flow (PayPal / Google Pay simulation)

### Mobile-app simulation behavior

- The checkout/confirm API path is the same path used by the mobile app integration.
- To test a successful payment upgrade in local/dev, create/sign in a user with phone `+421944400166`.
- To test unsuccessful payment handling, use any other phone number; confirmation returns HTTP `402` and subscription remains not upgraded.

Minimal runnable example:

```bash
python examples/minimal_demo.py
```

```bash
# 1) Start checkout for new subscription
curl -X POST "http://localhost:8080/v1/users/<USER_ID>/subscriptions/checkout" \
  -H "x-api-key: aijuris" \
  -H "Content-Type: application/json" \
  -d '{"plan_code":"premium","payment_provider":"paypal"}'

# 2) Confirm returned payment_id (simulated webhook/callback)
curl -X POST "http://localhost:8080/v1/users/subscriptions/<SUBSCRIPTION_ID>/confirm-payment" \
  -H "x-api-key: aijuris" \
  -H "Content-Type: application/json" \
  -d '{"payment_id":"PAY-..."}'
```

These endpoints persist users through `aijurisdictionagents.api_db.ApiDatabaseStore`
and support three database modes:

- `DB_OPTION=local`: local SQLite metadata (`DB_LOCAL`, default `./databases/api.sqlite3`)
- `DB_OPTION=postgres`: local PostgreSQL for Docker-based development (`DB_CLOUD=postgresql://...`)
- `DB_OPTION=azure`: Azure Database for PostgreSQL Flexible Server (`DB_CLOUD=postgresql://...sslmode=require`)
  - Use the exact Flexible Server administrator login as the username.

The dedicated local PostgreSQL project now lives under `databases/README.md`.

## Case history + documents

- `GET /v1/cases/{case_id}/history?user_id=...&offset=0&limit=5` returns the selected case's persisted chat history page plus stored case-document metadata.
- `GET /v1/cases/{case_id}/documents/{doc_id}?user_id=...` downloads a previously stored case document or chat attachment.
- Uploaded case documents are stored as `case -> many documents`. Each processed uploaded document keeps the extracted full text plus a real embedding in `case_document_contents`, and chunk-level text/embedding rows in `case_document_chunks`.
- Direct `POST /v1/chat/sessions/{session_id}/reply` now loads the most relevant processed document chunks for the user query by combining lexical overlap with semantic similarity from real embeddings, then injects those chunks into the extra system-context document message.
- Local API starts through [skills/start-api/scripts/start_api.ps1](/C:/Users/maton/Projects/aijurisdictionagents/skills/start-api/scripts/start_api.ps1) now enable `LOCAL_LLM_IO_LOGGING=1` by default, so local logs include the exact model payload and raw model response for debugging without changing deployed environments.
- The mobile app uses these endpoints to show the latest 5 saved case messages after case selection and to expose case-document download buttons.
- If an older case-history transcript blob is missing or unreadable, the API now falls back to the stored communication summary instead of failing the history load or blocking new session creation for that case.

## PDF export

- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=summary` returns the session summary.
- The summary PDF now includes generation date, API version, system core version, the latest law update date available to the system, the law-update source, the final recommendation for the user case, official law links stored by the law processor, and a dedicated case-validation section at the end with accuracy and validation summary.
- When the user asks to review and recreate an uploaded document under current law, the summary PDF also includes a dedicated legal-basis section that states which legal dataset and official law links were used to evaluate the document.
- `GET /v1/chat/sessions/{session_id}/export?format=pdf&kind=document` now builds a document that matches the detected case topic instead of always returning a lease template.
- Direct `POST /v1/chat/sessions/{session_id}/reply` sessions also persist a session result now, so the mobile `Real Agent` flow can download PDFs without going through the simulator stream.
- In `Real Agent` mode, the lawyer can first ask whether a formal document should be prepared as PDF; once the user confirms, the next direct reply marks `metadata.document_ready=true` in `GET /v1/chat/sessions/{session_id}/result`.
- Explicit document-revision requests that mention uploaded documents plus update/fix wording such as reviewing a contract against newer laws are also treated as document-preparation requests, so the API can prepare an updated export without waiting for a separate summary-only path.
- `GET /v1/chat/sessions/{session_id}/result` metadata now also includes `last_law_update_date`, `last_law_update_source`, `model_knowledge_cutoff_date`, `model_knowledge_cutoff_source`, `law_reference_links`, `api_version`, and the backward-compatible `knowledge_last_updated_at` alias.
- When the laws database has no import timestamp yet, `knowledge_last_updated_at` falls back to the cached `MODEL_KNOWLEDGE_CUTOFF_DATE` value while `last_law_update_date` remains empty.
- For Slovak and other Central European locales, the exporter uses a Unicode TrueType font when available so characters such as `á`, `č`, `ľ`, `ô`, and `ž` render correctly in the generated PDF.

Additional PDF font notes:
- The API container installs `fonts-dejavu-core` and the exporter prefers `DejaVu Serif` on Linux, so Azure deployments do not fall back to Helvetica for Slovak or German PDFs.
- On Windows, the exporter prefers `Times New Roman` and then `Arial` for Central European PDF exports.

## Version bump workflow

Rule:
- Whenever API or system core code changes, increase the revision number in the corresponding version file in the same change.
- Unless explicitly requested otherwise, do not change major or minor version numbers for these routine updates.

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
  - `http://localhost:<any-port>`
  - `http://127.x.x.x:<any-port>` for loopback IPv4 addresses
  - `http://[::1]:<any-port>` for IPv6 loopback
- Deployed browser clients are blocked until you set `CORS_ALLOW_ORIGINS` explicitly.
- Native Android/iOS builds do not require `CORS_ALLOW_ORIGINS`.
- Override allowed origins with `CORS_ALLOW_ORIGINS` (comma-separated), for example:

```bash
CORS_ALLOW_ORIGINS=http://localhost:8090,http://127.0.0.1:8090,http://localhost:7357,http://127.0.0.1:7357 uvicorn app.main:app --reload --port 8080
```

Example for a deployed browser build:

```bash
CORS_ALLOW_ORIGINS=https://mobile-web-dev.example.com,https://web-juris-dev.<region>.azurecontainerapps.io uvicorn app.main:app --reload --port 8080
```

## Chat simulator

The chat simulator has been moved to a separate application: `api/chat-simulator-app`.

Run it independently to test chat flows before frontend deployment.

For persisted-case debugging with local PostgreSQL, start the API with:

```bash
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5432/aijurisdiction STORAGE_OPTION=local DOCUMENT_PROCESSOR_OPTION=local LOCAL_LLM_IO_LOGGING=1 uvicorn app.main:app --reload --port 8080
```

The simulator can then call `GET /v1/cases/{case_id}/documents/debug?user_id=...&query=...` to show:
- stored uploaded document rows from the API database
- embedding/vector presence and chunk counts
- the exact document chunks selected for prompt injection for a query

For Slovak simulated discussions, the AI user now ends the conversation with `To je vsetko` instead of the internal sentinel word `finish`.

## OpenTelemetry

- Recommended production path: set `APPLICATIONINSIGHTS_CONNECTION_STRING` and the API will export requests, traces, logs, and unhandled exceptions to Azure Monitor / Application Insights.
- The API keeps writing structured request logs to console, so ACA log streaming and Log Analytics remain available even when Application Insights is enabled.
- Fallback behavior:
  - If `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, Azure Monitor OpenTelemetry is used.
  - Else if `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces are exported to that OTLP endpoint.
  - Else traces are written via the console exporter.
- `OTEL_SERVICE_NAME` defaults to `aijuristiction-api` if not set explicitly.
- Console trace export uses a synchronous processor in local default mode to avoid shutdown-time exporter thread errors during tests.

Local Azure Monitor example:

```bash
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=..." uvicorn app.main:app --reload --port 8080
```

Local OTLP fallback example:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces uvicorn app.main:app --reload --port 8080
```


## Database schema updates (local + cloud)

The API now applies SQL migrations during app startup for PostgreSQL/Azure, then runs the in-code bootstrap/compatibility checks. SQLite remains code-driven.

For pre-deploy validation, run from repository root:

```bash
PYTHONPATH=src python databases/scripts/apply_db_migrations.py --project api --dry-run
PYTHONPATH=src python databases/scripts/apply_api_db_schema.py --dry-run
PYTHONPATH=src python databases/scripts/apply_db_migrations.py --project api
PYTHONPATH=src python databases/scripts/apply_api_db_schema.py
```

Local PostgreSQL example:

```bash
cd databases
docker compose up -d
cd ..
DB_OPTION=postgres DB_CLOUD=postgresql://postgres:postgres@localhost:5432/aijurisdiction STORAGE_OPTION=local PYTHONPATH=src python databases/scripts/apply_api_db_schema.py
```

Cloud rollout:
1. Build/push/deploy API image.
2. Provision or update Azure PostgreSQL Flexible Server (`db-juris-dev` by default) through infra deployment.
3. Confirm Container App configuration:
   - `DB_OPTION=azure`
   - `DB_CLOUD=secretref:db-cloud`
   - `STORAGE_OPTION=azure`
   - `STORE_CLOUD=https://<storage-account>.blob.core.windows.net/<container-name>`
4. Roll out a new revision (or restart) and verify startup logs include selected `db_option`.

ACA log access:

```powershell
.\infra\scripts\tail_api_logs.ps1 -Tail 200
.\infra\scripts\tail_api_logs.ps1 -Tail 200 -CorrelationId "<mobile-correlation-id>"
```

The API echoes both `x-request-id` and `x-correlation-id` in responses, and ACA request logs include those values for direct filtering.

Application Insights and alerts:

- In ACA, set `APPLICATIONINSIGHTS_CONNECTION_STRING` as a secret-backed environment variable.
- The infra deployment now provisions or reuses the Application Insights resource `ai-juris-dev` by default and applies its connection string to the API Container App automatically.
- Recommended alert sources:
  - failed requests / HTTP 5xx
  - `AppExceptions` count
  - ACA system logs for revision or container failures
- Example KQL for recent API exceptions:

```kusto
AppExceptions
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| project TimeGenerated, ProblemId, Message, InnermostMessage, OperationName
```

- Example KQL for failed requests:

```kusto
AppRequests
| where TimeGenerated > ago(30m)
| where Success == false
| order by TimeGenerated desc
| project TimeGenerated, Name, ResultCode, DurationMs, OperationId
```

GitHub workflows:

- `.github/workflows/infra_deploy.yml`: provisions or updates Azure infrastructure, including PostgreSQL Flexible Server
- `.github/workflows/api_build_deploy.yml`: builds and deploys the API image, applies schema updates to Azure PostgreSQL, and injects `APPLICATIONINSIGHTS_CONNECTION_STRING` into ACA when the GitHub Environment secret is present
- `.github/workflows/database_schema_upgrade.yml`: upgrades schema on an existing Azure PostgreSQL server without rebuilding or redeploying the API

## Build + deployment workflow

GitHub workflow: `.github/workflows/api_build_deploy.yml`

Before opening a PR from a feature branch, sync it with latest `main`:

```bash
git fetch origin
git merge origin/main
```

- CI checks: install deps, lint (`ruff`), type-check (`mypy`), tests (`pytest`), and Docker build.
- GitHub Actions installs both the repo root package (`pip install -e ../..`) and the API package (`pip install -e .[dev]`) so tests can import `../../src/aijurisdictionagents` with its runtime dependencies.
- Local pre-flight command to mirror CI from this folder:

```bash
ruff check . && mypy app && pytest -q
```

Typing note: keep `UserResponseProvider` and `MessageCallback` imports in `app/chat/core_runtime.py`
inside the `TYPE_CHECKING` block so both `ruff` and `mypy --strict` stay green.

Telemetry processor selection (OTLP vs console) is covered by unit tests in `tests/test_telemetry.py`.

The API `pyproject.toml` also sets `mypy_path = ["../../src"]` so strict type checks can resolve the monorepo core package during CI and local runs.
The `pytest` command is configured with `pythonpath = [".", "../../src"]` in `pyproject.toml`, so tests can import the monorepo core package during direct local runs and GitHub Actions.
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
- `tests/mobile-auth-subscription.spec.ts` (covers mobile login + subscription request flow against user endpoints)
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



Run the mobile authentication + subscription lifecycle check used by the Flutter app:

```bash
cd api/aijuristiction-api/e2e-playwright
API_KEY=aijuris npx playwright test tests/mobile-auth-subscription.spec.ts
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
- To smoke-test Slovak and German glyph rendering locally, run `python examples/minimal_pdf_export.py` and open `runs/minimal-pdf-export.pdf`.
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

If `POST /v1/chat/sessions` is created with `case_id`, the API now seeds that new in-memory session with the stored case history so the next reply/stream turn can continue the existing case context instead of starting with an empty prompt.
If one of those seeded case-history transcript files is missing, the API falls back to the saved summary text so existing cases can still create a session and continue.


## Minimal runnable example (streaming API + core)

Start API first, then run:

```bash
python examples/api_streaming_demo.py
```
