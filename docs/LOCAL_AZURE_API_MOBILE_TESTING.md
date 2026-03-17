# Local + Azure API/PostgreSQL/Mobile Testing Runbook

This runbook defines how to validate:

1. Local API with local PostgreSQL.
2. Mobile app against local API.
3. Azure infrastructure deployment (including Azure Database for PostgreSQL Flexible Server).
4. API deployment configured to use Azure PostgreSQL.
5. Local mobile app against deployed Azure API.

It also includes a fallback readiness workflow for constrained environments where Docker/Flutter/Azure CLI are not installed.

## Quick readiness check (minimal runnable example)

Run from repository root:

```bash
python examples/local_azure_readiness_check.py
```

The script verifies required tools, local ports, API health, and required Azure environment variables.

## Prerequisites

- Docker + Docker Compose
- PowerShell (`pwsh`) for bundled project skills
- Azure CLI (`az`) with active login
- Flutter SDK
- Python 3.11+
- API dependencies installed (`pip install -e "api/aijuristiction-api[dev]"` from repo root or inside env)

## 1) Validate local PostgreSQL + API

Preferred path (PowerShell skill scripts):

```powershell
.\skills\start-postgress\scripts\start_postgress.ps1
.\skills\start-api\scripts\start_api.ps1 -Background -LlmProvider mock -DatabaseOption postgres
```

Manual Linux fallback:

```bash
cd databases
docker compose up -d postgres
cd ..
cd api/aijuristiction-api
DB_OPTION=postgres \
DB_CLOUD="postgresql://postgres:postgres@localhost:5432/aijurisdiction" \
STORAGE_OPTION=local \
LLM_PROVIDER=mock \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Health checks:

```bash
curl -fsS http://127.0.0.1:8080/health
python examples/minimal_demo.py
```

## 2) Validate local mobile app with local API

Preferred skill command:

```powershell
.\skills\start-mobile-app\scripts\start_mobile_app.ps1 -Background -ApiMode localApi -DatabaseOption postgres
```

Manual fallback:

```bash
cd mobile_app
flutter run -d chrome --web-port 7357 --dart-define=AIJ_API_BASE_URL=http://127.0.0.1:8080
```

Smoke check:

- Open `http://127.0.0.1:7357`.
- Perform sign-in/sign-up and one chat request.
- Confirm API logs show incoming requests.

## 3) Deploy Azure infrastructure + ensure Azure PostgreSQL exists

```bash
az login
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
```

Use repo deployment script:

```powershell
.\infra\scripts\deploy_api.ps1 -SubscriptionId <sub-id> -AcrName <unique-acr>
```

Verify Azure PostgreSQL Flexible Server:

```bash
az postgres flexible-server show \
  --name "$AZURE_DB_SERVER_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "{name:name,state:state,version:version,publicAccess:network.publicNetworkAccess}" -o json
```

## 4) Deploy API configured for Azure PostgreSQL

Ensure container app env vars include:

- `DB_OPTION=azure`
- `DB_CLOUD=postgresql://<user>:<password>@<server>.postgres.database.azure.com:5432/<db>?sslmode=require`
- `STORAGE_OPTION=azure|local` (as desired)
- `STORE_CLOUD=<storage connection string>` if `STORAGE_OPTION=azure`

Run DB bootstrap/migrations against Azure DB before or during startup:

```bash
DB_OPTION=azure \
DB_CLOUD="postgresql://...sslmode=require" \
PYTHONPATH=src python databases/scripts/apply_db_migrations.py --project api

DB_OPTION=azure \
DB_CLOUD="postgresql://...sslmode=require" \
PYTHONPATH=src python databases/scripts/apply_api_db_schema.py
```

Validate deployed API:

```bash
curl -fsS https://<deployed-api-host>/health
curl -fsS https://<deployed-api-host>/version
```

## 5) Validate local mobile app against Azure-deployed API

```bash
cd mobile_app
flutter run -d chrome --web-port 7357 --dart-define=AIJ_API_BASE_URL=https://<deployed-api-host>
```

Check:

- Auth endpoints return success.
- Chat/session endpoints persist metadata to Azure PostgreSQL.
- New data appears in Azure DB tables (`users`, `subscriptions`, `case_documents`, etc.).

Important:

- Flutter web or any browser-hosted mobile build requires the API to allow that exact origin in `CORS_ALLOW_ORIGINS`.
- Native Android/iOS app builds do not need CORS configuration.
- The mobile app already sends `x-correlation-id` and `x-request-id`; the API now echoes both so the same ID can be copied from the app and searched in ACA logs.

ACA log tracing example:

```powershell
.\infra\scripts\tail_api_logs.ps1 -Tail 200 -CorrelationId "<copied-mobile-correlation-id>"
```

Application Insights tracing example:

```kusto
AppTraces
| where TimeGenerated > ago(30m)
| where Message has "<copied-mobile-correlation-id>"
| order by TimeGenerated desc
```

Recommended alert baseline for the deployed API:

- `AppExceptions` log alert
- failed request / HTTP 5xx alert
- ACA system log alert for revision or container crashes

If a deployed browser build fails before reaching the handler, verify preflight/CORS:

```powershell
Invoke-WebRequest -Method Options `
  -Uri "https://<deployed-api-host>/v1/users/sign-in" `
  -Headers @{
    Origin = "https://<your-browser-host>"
    "Access-Control-Request-Method" = "POST"
    "Access-Control-Request-Headers" = "content-type,x-api-key"
  }
```

Expected result:

- `200` with `Access-Control-Allow-Origin: https://<your-browser-host>`

If the origin is not configured, the API returns `400 Disallowed CORS origin`.

## Environment-constrained fallback plan

If current workstation/container is missing required tooling:

1. Run `python examples/local_azure_readiness_check.py` and capture JSON output.
2. Install missing tools (`docker`, `pwsh`, `flutter`, `az`) or switch to a dev VM that has them.
3. Re-run readiness check until all `tool:*` checks pass.
4. Execute steps 1-5 in this runbook.
5. Archive outputs:
   - Health check responses
   - Deployment command logs
   - API revision details
   - Mobile smoke-test recording/screenshot

This provides a reproducible test/deploy workflow even when immediate execution is not possible in the active environment.
