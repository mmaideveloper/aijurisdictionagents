# Infrastructure (Azure)

This folder contains local-first infrastructure automation for deploying the API to Azure.

## Recommended deployment approach

- **Runtime:** Azure Container Apps
- **Image registry:** Azure Container Registry (ACR)
- **Infrastructure as code:** Bicep
- **Local execution:** Azure CLI + PowerShell from your workstation

This keeps deployment simple while matching the existing API container workflow.

## What gets provisioned

- Resource Group (created by script)
- Log Analytics Workspace
- Application Insights (`ai-juris-dev` by default)
- Azure Container Apps Environment
- Azure Database for PostgreSQL Flexible Server
- PostgreSQL database (`aijurisdiction` by default)
- Azure Container Registry (ACR)
- Azure Storage Account (Blob Storage)
- Private blob container (`case-documents` by default)
- User-assigned Managed Identity with `AcrPull` on ACR
- User-assigned Managed Identity with `Storage Blob Data Contributor` on Storage Account
- User-assigned Managed Identity with `Log Analytics Data Reader` on the shared workspace
- Azure Container App (public ingress on port `8080`)

ACA resources created by repository deployments:

- Managed Environment: `AZURE_CONTAINERAPPS_ENVIRONMENT`
- API Container App: `AZURE_CONTAINER_APP_NAME`
- Frontend Container App: `AZURE_FRONTEND_CONTAINER_APP_NAME`
- Laws Collector Container App: `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME`
- Document Processor ACA Job: `AZURE_DOCUMENT_PROCESSOR_JOB_NAME`

## Prerequisites

- Azure subscription with permission to create resources
- Azure CLI (`az`) installed
- Azure CLI Container Apps extension
- PowerShell 7+ (recommended)

## Azure login rule

For this repository, always use the service principal login flow for Azure CLI access to repo resources.
Do not use the currently signed-in interactive Azure user for deployment, diagnostics, log access, or resource inspection.
Before running repo Azure commands, prefer:

```powershell
.\infra\scripts\login_service_principal.ps1 -EnvFilePath ".env"
```

If the current Azure context points to the wrong tenant or subscription, run the helper again instead of continuing with the existing user session.

Register the PostgreSQL resource provider on the target subscription before running `infra_deploy`:

```powershell
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az provider register --namespace Microsoft.DBforPostgreSQL --wait
az provider show --namespace Microsoft.DBforPostgreSQL --query registrationState -o tsv
```

The final command should return `Registered`.

Login once (interactive):

```powershell
az login
```

## Service principal login (recommended for automation)

Create a deployment resource group (one-time):

```powershell
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az group create -n "rg-aijurisdiction-dev" -l "westeurope"
```

Create a service principal scoped to that resource group:

```powershell
az ad sp create-for-rbac `
  --name "sp-aijurisdiction-deploy" `
  --role Contributor `
  --scopes "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-aijurisdiction-dev"
```

Save output values:

- `appId` -> `AZURE_CLIENT_ID`
- `password` -> `AZURE_CLIENT_SECRET`
- `tenant` -> `AZURE_TENANT_ID`

Grant RBAC assignment permissions required by infra deployment:

```powershell
az role assignment create `
  --assignee "<AZURE_CLIENT_ID>" `
  --role "User Access Administrator" `
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-aijurisdiction-dev"
```

Login locally using the service principal:

```powershell
$env:AZURE_CLIENT_ID="<appId>"
$env:AZURE_CLIENT_SECRET="<password>"
$env:AZURE_TENANT_ID="<tenantId>"
$env:AZURE_SUBSCRIPTION_ID="<subscriptionId>"

az login --service-principal `
  --username $env:AZURE_CLIENT_ID `
  --password $env:AZURE_CLIENT_SECRET `
  --tenant $env:AZURE_TENANT_ID

az account set --subscription $env:AZURE_SUBSCRIPTION_ID
```

Use helper script (priority: parameters -> `.env` -> process env vars):

```powershell
.\infra\scripts\login_service_principal.ps1 -EnvFilePath ".env"
```

Skip reading `.env` if needed:

```powershell
.\infra\scripts\login_service_principal.ps1 -SkipEnvFile
```

## Deploy from local machine

From repository root:

```powershell
.\infra\scripts\deploy_api.ps1
```

Note: ACR registry names must be `5-50` characters, lowercase alphanumeric only.
If `.env` contains `AZURE_CONTAINER_REGISTRY` with `-` or `.azurecr.io`, the script normalizes it automatically.
The script also checks whether the current Azure login matches `AZURE_CLIENT_ID` from `.env`.
If it does not match (or no login exists), it runs `infra/scripts/login_service_principal.ps1` automatically.
For `AZURE_API_IMAGE_TAG`, both `tag` (for example `latest`) and `repository:tag`
(for example `ai-api-juris-dev:latest`) are supported.

The script will:

1. Provision/update Azure infrastructure via `infra/bicep/main.bicep`
2. Build the API image in ACR using `az acr build`
3. Store the Azure PostgreSQL connection string as a Container Apps secret and update the Container App image/env configuration
4. Provision or reuse the Application Insights resource and apply its connection string to the API Container App
5. Apply API schema migrations to Azure PostgreSQL

The Bicep deployment provisions or reuses:

- Azure Database for PostgreSQL Flexible Server (`AZURE_POSTGRES_SERVER_NAME`, default `db-juris-dev`)
- PostgreSQL database (`AZURE_POSTGRES_DATABASE_NAME`, default `aijurisdiction`)
- PostgreSQL database for the Slovak laws corpus (`AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`, default `laws_sk`)
- firewall rule for Azure services
- `azure.extensions=vector`
- Public frontend Azure Container App (`AZURE_FRONTEND_CONTAINER_APP_NAME`)
- Document processor ACA Job (`AZURE_DOCUMENT_PROCESSOR_JOB_NAME`, default `document-processor`)
- Private Azure Container App for the laws collector (`AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME`, default `laws-collector`)

Existing-resource behavior:

- If a named resource already exists in the target resource group, deployment reuses it instead of creating it again.
- The deploy script requires existing named resources to already be in the requested location. If a resource with the same name exists in a different region, deployment fails with a location mismatch instead of silently switching regions.
- Shared RBAC assignments for the user-assigned managed identity are intentionally keyed only by `scope + principal + role`. This keeps `AcrPull` and `Storage Blob Data Contributor` idempotent across `infra_deploy`, laws collector, frontend, and document processor workflows.

Parameter resolution priority in `deploy_api.ps1`:

1. Explicit script parameters
2. Values from `.env`
3. Existing process environment variables
4. Built-in defaults (for non-secret naming/location values)

## Environment variables for the API

By default, the script reads selected keys from repo `.env` and sets them on the Container App.
For Azure PostgreSQL deployments, the script uses `AZURE_POSTGRES_ADMIN_USERNAME` as provided when building `DB_CLOUD`,
stores that value in a Container Apps secret, and sets
`DB_CLOUD=secretref:db-cloud` on the API container.
If Application Insights exists or is provisioned by the same deployment, the script reads the connection string and sets
`APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:applicationinsights-connection-string` on the API container automatically.
The API deploy sets `AZURE_LOG_ANALYTICS_WORKSPACE_NAME` and
`AZURE_MANAGED_IDENTITY_NAME` on the API container so
`/v1/observability/logs` can resolve and query Azure telemetry. The deploy also sets
the standard Azure identity selector `AZURE_CLIENT_ID` on the container to the chosen
user-assigned managed identity client ID.
`STORE_CLOUD` is set as a blob URL prefix, not as a secret.
If `CORS_ALLOW_ORIGINS` is present in `.env`, the script passes it through to the API container unchanged.
Use that only for deployed browser clients such as Flutter web. Native Android/iOS builds do not require CORS configuration.

If your `.env` is at the repo root, no extra flag is needed. To use a different file:

```powershell
.\infra\scripts\deploy_api.ps1 `
  -SubscriptionId "<your-subscription-id>" `
  -AcrName "aijurdevacr12345" `
  -EnvFilePath ".env"
```

## GitHub workflow deployment setup (OIDC federation)

The API workflow `.github/workflows/api_build_deploy.yml` logs into Azure using OIDC
(`azure/login@v2`) and expects `AZURE_CLIENT_ID` to be an Entra application that has
a federated credential for GitHub.

1. Create an Entra app and service principal:

```powershell
$SubscriptionId = "<SUBSCRIPTION_ID>"
$ResourceGroupName = "<RESOURCE_GROUP_NAME>"
$AcrName = "<ACR_NAME>"
$RepoOwner = "<GITHUB_OWNER>"
$RepoName = "<GITHUB_REPO>"
$GithubEnvironment = "dev"   # must match workflow input github_environment

az account set --subscription $SubscriptionId
$TenantId = az account show --query tenantId -o tsv
$ClientId = az ad app create --display-name "aijurisdiction-api-deploy" --query appId -o tsv
az ad sp create --id $ClientId
```

2. Grant required Azure roles:

```powershell
az role assignment create `
  --assignee $ClientId `
  --role "Contributor" `
  --scope "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName"

az role assignment create `
  --assignee $ClientId `
  --role "AcrPush" `
  --scope "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.ContainerRegistry/registries/$AcrName"
```

3. Create federated credential for GitHub Environment:

```powershell
$federatedCredential = @{
  name        = "github-${RepoOwner}-${RepoName}-${GithubEnvironment}"
  issuer      = "https://token.actions.githubusercontent.com"
  subject     = "repo:${RepoOwner}/${RepoName}:environment:${GithubEnvironment}"
  description = "OIDC federation for API deployment workflow"
  audiences   = @("api://AzureADTokenExchange")
} | ConvertTo-Json -Depth 5

$tempFile = Join-Path $env:TEMP "github-federated-credential.json"
$federatedCredential | Out-File -FilePath $tempFile -Encoding utf8
az ad app federated-credential create --id $ClientId --parameters $tempFile
```

4. Configure GitHub Environment variables (Settings -> Environments -> `<environment>` -> Variables):

- `AZURE_CLIENT_ID` = `$ClientId`
- `AZURE_TENANT_ID` = `$TenantId`
- `AZURE_SUBSCRIPTION_ID` = `<SUBSCRIPTION_ID>`
- `AZURE_RESOURCE_GROUP` = `<RESOURCE_GROUP_NAME>`
- `AZURE_CONTAINERAPPS_ENVIRONMENT` = `<CONTAINERAPPS_ENV_NAME>`
- `AZURE_CONTAINER_APP_NAME` = `<CONTAINER_APP_NAME>`
- `AZURE_APPLICATION_INSIGHTS_NAME` = `ai-juris-dev`
- `AZURE_POSTGRES_SERVER_NAME` = `db-juris-dev`
- `AZURE_POSTGRES_DATABASE_NAME` = `aijurisdiction`
- `AZURE_POSTGRES_ADMIN_USERNAME` = `<POSTGRES_ADMIN_USERNAME>`
  - Use the exact Flexible Server administrator login, for example `jurisadmin` or `postgres`.
- GitHub secret `AZURE_POSTGRES_ADMIN_PASSWORD` = `<POSTGRES_ADMIN_PASSWORD>`
- `AZURE_CONTAINER_REGISTRY` = `<ACR_NAME>`
- `AZURE_STORAGE_ACCOUNT_NAME` = `<STORAGE_ACCOUNT_NAME>` (optional; auto-derived if omitted)
- `AZURE_STORAGE_CONTAINER_NAME` = `<STORAGE_CONTAINER_NAME>` (optional; defaults to `case-documents`)
- `LLM_PROVIDER` = `azurefoundry`
- `SYSTEM_EMBEDDING_MODEL_OPTION` = `local` by default for deployed worker environments
- `SYSTEM_EMBEDDING_MODEL` = `all-MiniLM-L6-v2`
- `AZURE_OPENAI_ENDPOINT` = `https://<resource>.openai.azure.com/`
- `AZURE_OPENAI_DEPLOYMENT` = `<chat_deployment_name>`
- `AZURE_OPENAI_EMBEDDINGS_MODEL` = `text-embedding-3-large` (or your embedding deployment name)
- `AZURE_OPENAI_API_VERSION` = `2024-12-01-preview`
- GitHub secret `AZURE_OPENAI_API_KEY` = `<AZURE_OPENAI_KEY>`
- `DOCUMENT_PROCESSOR_OPTION` = `azure` for deployed environments so the API leaves uploads pending for the ACA document-processor job. The Azure API deploy paths now force this value instead of inheriting `local` from workstation `.env` files.
- `CORS_ALLOW_ORIGINS` = comma-separated deployed browser origins allowed to call the API (optional)
  - Example: `https://mobile-web-dev.example.com,https://web-juris-dev.<region>.azurecontainerapps.io`
  - Do not set this for native Android/iOS-only clients unless you also have a browser-hosted build.

5. Run the workflow:

- Workflow: `API Build and Deploy`
- Push to `main`: automatically deploys to the `dev` GitHub Environment after tests/build pass
- Inputs: `deploy=true`, `github_environment=<environment>`
  - Manual `workflow_dispatch` is still the path for non-`dev` environments such as `test` and `prod`
- After the image deploy step, the workflow now waits for the Container App provisioning state to return to `Succeeded` before applying secrets and environment variables.
- If Azure still reports `ContainerAppOperationInProgress`, the workflow retries the secret/env update commands automatically instead of failing on the first race.

## GitHub workflow for database schema upgrades only

If the Azure PostgreSQL server already exists and you only need to apply schema changes, run:

- Workflow: `Database Schema Upgrade`
- Inputs:
  - `github_environment=<environment>`
  - `dry_run=true|false`

This workflow:

1. Logs into Azure with OIDC
2. Opens a temporary firewall rule for the GitHub runner IP
3. Runs `python scripts/databases/apply_api_db_schema.py` against the existing Azure PostgreSQL server
4. Removes the temporary firewall rule

## ACA API logs

Use the bundled helper when reproducing mobile/API issues:

```powershell
.\infra\scripts\tail_api_logs.ps1
```

Useful filters:

```powershell
.\infra\scripts\tail_api_logs.ps1 -Tail 200 -CorrelationId "<mobile-correlation-id>"
.\infra\scripts\tail_api_logs.ps1 -Tail 200 -RequestId "<request-id>"
.\infra\scripts\tail_api_logs.ps1 -SystemLogs -Tail 200
```

Resolution order for `tail_api_logs.ps1`:

1. Explicit parameters
2. Repo `.env`
3. Process environment variables

The API now logs both `request_id` and `correlation_id`, plus `origin` and `user_agent`, so a mobile-side error can be matched directly to ACA logs.

## Application Insights and alerts

Recommended production setup for this repo:

1. Keep ACA console and system logs in Log Analytics for platform/runtime troubleshooting.
2. Provision `Microsoft.Insights/components` and set its connection string on the API Container App as a secret-backed environment variable.
3. Use Application Insights for exceptions, failed requests, traces, and alert rules.

Deployment behavior:

- `infra/scripts/deploy_api.ps1` now provisions or reuses Application Insights and applies its connection string to ACA automatically. Explicit env input still overrides the deployment output if needed.
- `.github/workflows/api_build_deploy.yml` now queries the configured Application Insights resource and applies its connection string to ACA automatically.
- Azure API deploys inject `AZURE_LOG_ANALYTICS_WORKSPACE_NAME`, `AZURE_MANAGED_IDENTITY_NAME`, `AZURE_RESOURCE_GROUP`, `AZURE_SUBSCRIPTION_ID`, and the standard `AZURE_CLIENT_ID` selector so the API can query recent telemetry through `GET /v1/observability/logs`.
- Azure document processor and laws collector deployments now apply the same Application Insights connection string to their ACA jobs, so the observability endpoint can filter `api`, `document_processor`, and `laws_collector` in one place.
- Least-privilege workspace access for that managed identity is `Log Analytics Data Reader` on the Log Analytics workspace scope.

Recommended GitHub Environment additions:

- Variable: `AZURE_APPLICATION_INSIGHTS_NAME` with value `ai-juris-dev`
- Variable: `CORS_ALLOW_ORIGINS` only for browser-hosted clients

Example KQL for recent exceptions:

```kusto
AppExceptions
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| project TimeGenerated, ProblemId, Message, OperationName
```

Example KQL for failed requests:

```kusto
AppRequests
| where TimeGenerated > ago(30m)
| where Success == false
| summarize failures=count() by bin(TimeGenerated, 5m), Name, ResultCode
| order by TimeGenerated desc
```

Recommended alerts:

- Log alert on `AppExceptions` count above your chosen threshold over 5-10 minutes
- Log alert on failed request count / HTTP 5xx
- ACA system-log alert for `ContainerCrashing`, `ErrImagePull`, or revision provisioning failures
- Metric alerts for CPU, memory, and restart spikes on the Container App

## Files

- `infra/bicep/main.bicep`: Azure resources definition
- `infra/bicep/main.parameters.example.json`: example parameters file
- `infra/scripts/deploy_api.ps1`: local deployment entrypoint
- `infra/scripts/login_service_principal.ps1`: service principal login helper

## Troubleshooting

If deployment fails with `Microsoft.Authorization/roleAssignments/write`, your service principal can deploy resources but cannot create RBAC role assignments.

Grant one of these roles to your service principal at RG scope:

- `User Access Administrator` (recommended minimum for RBAC writes)
- `Owner`

Example:

```powershell
az role assignment create `
  --assignee "<AZURE_CLIENT_ID>" `
  --role "User Access Administrator" `
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP_NAME>"
```

If `AZURE_CONTAINER_REGISTRY` in `.env` contains `*.azurecr.io`, the deploy script now normalizes it to the registry name automatically.

If deployment fails with `MANIFEST_UNKNOWN` for Container App image update, verify that the ACR build produced the expected `repository:tag`.
The deploy script now waits for image manifest availability in ACR and fails early when the tag is missing.

If deployment fails with `AuthenticationFailed` and message `Signed expiry time ... must be after signed start time ...` during `az acr build`,
the script automatically falls back to local `docker build` + `docker push` (after `az acr login`).
If this still fails, ensure system time is synchronized and retry.

If Azure CLI on Windows throws `UnicodeEncodeError ... cp1252` during ACR build log streaming,
the deploy script uses `az acr build --no-logs` to avoid that stream encoding failure.

## Frontend container and workflow

New frontend deployment assets:

- `frontend/aijurisdictionfronend/Dockerfile`: multi-stage frontend image build (Node build + Nginx runtime)
- `infra/bicep/frontend.containerapp.bicep`: dedicated Azure Container App template for frontend
- `infra/bicep/frontend.containerapp.parameters.example.json`: example parameter values
- `.github/workflows/web_build_deploy.yml`: frontend CI/CD workflow
- `.github/workflows/infra_deploy.yml`: infrastructure provisioning workflow (Bicep)

Required GitHub Environment variables for frontend deployment:

- `AZURE_FRONTEND_CONTAINER_APP_NAME`
- `AZURE_LOCATION`
- `AZURE_MANAGED_IDENTITY_NAME`

`infra_deploy` now provisions or reuses the frontend Container App shell using `AZURE_FRONTEND_CONTAINER_APP_NAME`.
`web_build_deploy` updates that app with the built frontend image and can also bootstrap it directly if the shell was not provisioned yet.

For a repo-level checklist to create additional GitHub Environments such as `test`
and `prod`, see `docs/GITHUB_ENVIRONMENTS.md`.

## Deploy laws collector ACA job

A dedicated deployment script and Bicep template are available for the laws collector worker:

- Script: `infra/scripts/deploy_laws_collector.ps1`
- Template: `infra/bicep/laws_collector.job.bicep`

The deployment creates/updates a scheduled ACA Job named `laws-collector` (by default), assigns ACR pull identity, and configures runtime environment variables for PostgreSQL-backed ingestion.
Before updating the ACA job, the deploy path applies the laws collector PostgreSQL schema migrations to `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK` or the explicit `-PostgresDatabaseName` override.

Run from repository root:

```powershell
./infra/scripts/deploy_laws_collector.ps1 \
  -SubscriptionId "<subscription-id>" \
  -ResourceGroupName "<resource-group>" \
  -Location "westeurope" \
  -ContainerAppEnvironmentName "<container-app-env-name>" \
  -AcrName "<acr-name>" \
  -ManagedIdentityName "<managed-identity-name>" \
  -PostgresServerName "<postgres-server-name>" \
  -PostgresDatabaseName "laws_sk" \
  -PostgresAdminUsername "<postgres-admin-user>" \
  -PostgresAdminPassword "<postgres-admin-password>" \
  -ImageTag "latest"
```

The script builds the laws collector image in ACR using `src/services/laws_collector/Dockerfile` and deploys the ACA Job with the image tag you provide.

GitHub Actions workflow:

- Workflow file: `.github/workflows/laws_collector_build_deploy.yml`
- Push to `main` for laws collector changes: runs `tests/test_laws_collector.py` and `tests/test_db_migration_safety.py`, validates the Docker image build, and deploys to the `dev` GitHub Environment
- Pull requests: run tests and Docker build only
- Manual run: supports `deploy=true|false`, custom GitHub Environment, and optional image tag override
- The deploy job temporarily opens the GitHub runner IP on Azure PostgreSQL, installs Python dependencies, applies `python scripts/databases/apply_laws_db_schema.py`, and then deploys the ACA job

Required GitHub Environment variables/secrets for deployment:

- Variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `AZURE_CONTAINERAPPS_ENVIRONMENT`, `AZURE_CONTAINER_REGISTRY`, `AZURE_MANAGED_IDENTITY_NAME`, `AZURE_POSTGRES_SERVER_NAME`, `AZURE_POSTGRES_ADMIN_USERNAME`
- Secrets: `AZURE_POSTGRES_ADMIN_PASSWORD`
- Optional variables: `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME`, `AZURE_LAWS_COLLECTOR_MAX_PROBES`, `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`, `SYSTEM_EMBEDDING_MODEL_OPTION`, `SYSTEM_EMBEDDING_MODEL`
- Optional schedule variable: `AZURE_LAWS_COLLECTOR_CRON_EXPRESSION` with default `0 0 * * *`

Recommended GitHub Environment values:

- `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME=laws-collector`
- `AZURE_LAWS_COLLECTOR_CRON_EXPRESSION=0 0 * * *`
- `AZURE_LAWS_COLLECTOR_MAX_PROBES=1`
- `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK=laws_sk`
- `SYSTEM_EMBEDDING_MODEL_OPTION=local` by default, or `SYSTEM_EMBEDDING_MODEL_OPTION=cloud` if you want Azure/OpenAI embeddings
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2`

Azure Container Apps Jobs use 5-field cron expressions. The deploy paths also accept legacy 6-field values with a leading `0` seconds field and normalize them automatically.

Database migration rule:

- PostgreSQL migrations must be backward-compatible with the currently deployed API, document processor, and laws collector.
- Do not add destructive SQL such as `DROP TABLE`, `DROP COLUMN`, `DROP CONSTRAINT`, `RENAME COLUMN`, `ALTER COLUMN TYPE`, or `SET NOT NULL` in migration files.
- Expand first: add new tables or nullable/defaulted columns, deploy application changes, then clean up in a later coordinated release if needed.


## Deploy document processor ACA job

A dedicated deployment script and Bicep template are available for the document processor service:

- Script: `infra/scripts/deploy_document_processor.ps1`
- Template: `infra/bicep/document_processor.job.bicep`

The deployment builds `src/services/document_processor/Dockerfile`, publishes the image to ACR, and creates or updates a scheduled Azure Container Apps Job that processes uploaded case documents into text/vector records.
The deploy script passes the resolved `AZURE_DOCUMENT_PROCESSOR_LOCATION` or `AZURE_LOCATION` into the ACA Job Bicep deployment, so the requested job region no longer falls back to the resource group location.

Use `DOCUMENT_PROCESSOR_OPTION=azure` on the deployed API Container App together with this ACA job.
For local development only, you can set `DOCUMENT_PROCESSOR_OPTION=local` so uploads are processed immediately inside the API process.
All Azure deployment workflows now append an `ACA deployment summary` table to the GitHub Actions run summary so you can see which ACA resources were created, reused, or updated without scanning the raw logs.
`infra_deploy` also provisions or reuses the initial document processor ACA job shell so the later document processor workflow can focus on publishing the service image and job configuration updates.

```powershell
./infra/scripts/deploy_document_processor.ps1 \
  -SubscriptionId "<subscription-id>" \
  -ResourceGroupName "<resource-group>" \
  -Location "westeurope" \
  -ContainerAppEnvironmentName "<container-app-env-name>" \
  -AcrName "<acr-name>" \
  -ManagedIdentityName "<managed-identity-name>" \
  -PostgresServerName "<postgres-server-name>" \
  -PostgresDatabaseName "api" \
  -PostgresAdminUsername "<postgres-admin-user>" \
  -PostgresAdminPassword "<postgres-admin-password>" \
  -StorageAccountName "<storage-account-name>" \
  -StorageContainerName "documents" \
  -CronExpression "*/15 * * * *" \
  -ImageTag "latest"
```

GitHub Actions workflow:

- Workflow file: `.github/workflows/document_processor_build_deploy.yml`
- Push to `main` for document processor changes: runs tests, validates the Docker image build, and deploys to the `dev` GitHub Environment
- Pull requests: run tests and Docker build only
- Manual run: supports `deploy=true|false`, custom GitHub Environment, and optional image tag override

Required GitHub Environment variables/secrets for deployment:

- Variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINERAPPS_ENVIRONMENT`, `AZURE_CONTAINER_REGISTRY`, `AZURE_MANAGED_IDENTITY_NAME`, `AZURE_POSTGRES_SERVER_NAME`, `AZURE_POSTGRES_DATABASE_NAME`, `AZURE_POSTGRES_ADMIN_USERNAME`, `AZURE_STORAGE_ACCOUNT_NAME`, `LLM_PROVIDER`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_EMBEDDINGS_MODEL`, `AZURE_OPENAI_API_VERSION`
- Variables: `SYSTEM_EMBEDDING_MODEL_OPTION`, `SYSTEM_EMBEDDING_MODEL`
- Secrets: `AZURE_POSTGRES_ADMIN_PASSWORD`, `AZURE_OPENAI_API_KEY`
- Optional variables: `AZURE_STORAGE_CONTAINER_NAME`, `AZURE_DOCUMENT_PROCESSOR_LOCATION`, `AZURE_DOCUMENT_PROCESSOR_JOB_NAME`, `AZURE_DOCUMENT_PROCESSOR_CRON_EXPRESSION`

Recommended GitHub Environment values:

- `AZURE_DOCUMENT_PROCESSOR_LOCATION=westeurope` unless your shared ACA environment is in a different region
- `AZURE_DOCUMENT_PROCESSOR_CRON_EXPRESSION=*/15 * * * *` unless you need a different schedule
- `SYSTEM_EMBEDDING_MODEL_OPTION=local` by default, or `SYSTEM_EMBEDDING_MODEL_OPTION=cloud` if you want Azure/OpenAI embeddings
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2`

For the document processor Azure job, `SYSTEM_EMBEDDING_MODEL_OPTION=local` is supported directly from GitHub Environment variables. In that mode the deployment no longer requires Azure OpenAI embedding settings for the worker, and the container downloads/caches the local sentence-transformer model under `/app/aimodels`.

Azure Container Apps Jobs use 5-field cron expressions. The deploy paths also accept legacy 6-field values with a leading `0` seconds field and normalize them automatically.
