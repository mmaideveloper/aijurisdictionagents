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
- Azure Container Apps Environment
- Azure Database for PostgreSQL Flexible Server
- PostgreSQL database (`aijurisdiction` by default)
- Azure Container Registry (ACR)
- Azure Storage Account (Blob Storage)
- Private blob container (`case-documents` by default)
- User-assigned Managed Identity with `AcrPull` on ACR
- User-assigned Managed Identity with `Storage Blob Data Contributor` on Storage Account
- Azure Container App (public ingress on port `8080`)

## Prerequisites

- Azure subscription with permission to create resources
- Azure CLI (`az`) installed
- Azure CLI Container Apps extension
- PowerShell 7+ (recommended)

Login once (interactive):

```powershell
az login
```

## Service principal login (recommended for automation)

Create a deployment resource group (one-time):

```powershell
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az group create -n "rg-aijurisdiction-dev" -l "austriaeast"
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
3. Update the Container App to the new image and database env vars
4. Apply API schema migrations to Azure PostgreSQL

The Bicep deployment provisions or reuses:

- Azure Database for PostgreSQL Flexible Server (`AZURE_POSTGRES_SERVER_NAME`, default `db-juris-dev`)
- PostgreSQL database (`AZURE_POSTGRES_DATABASE_NAME`, default `aijurisdiction`)
- firewall rule for Azure services
- `azure.extensions=vector`

Existing-resource behavior:

- If a named resource already exists in the target resource group, deployment reuses it instead of creating it again.
- The deploy script detects existing resource locations and aligns new resources to avoid location conflicts.

Parameter resolution priority in `deploy_api.ps1`:

1. Explicit script parameters
2. Values from `.env`
3. Existing process environment variables
4. Built-in defaults (for non-secret naming/location values)

## Environment variables for the API

By default, the script reads selected keys from repo `.env` and sets them on the Container App.

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
- `AZURE_POSTGRES_SERVER_NAME` = `db-juris-dev`
- `AZURE_POSTGRES_DATABASE_NAME` = `aijurisdiction`
- `AZURE_POSTGRES_ADMIN_USERNAME` = `<POSTGRES_ADMIN_USERNAME>`
- GitHub secret `AZURE_POSTGRES_ADMIN_PASSWORD` = `<POSTGRES_ADMIN_PASSWORD>`
- `AZURE_CONTAINER_REGISTRY` = `<ACR_NAME>`
- `AZURE_STORAGE_ACCOUNT_NAME` = `<STORAGE_ACCOUNT_NAME>` (optional; auto-derived if omitted)
- `AZURE_STORAGE_CONTAINER_NAME` = `<STORAGE_CONTAINER_NAME>` (optional; defaults to `case-documents`)

5. Run the workflow:

- Workflow: `API Build and Deploy`
- Inputs: `deploy=true`, `github_environment=<environment>`

## GitHub workflow for database schema upgrades only

If the Azure PostgreSQL server already exists and you only need to apply schema changes, run:

- Workflow: `Database Schema Upgrade`
- Inputs:
  - `github_environment=<environment>`
  - `dry_run=true|false`

This workflow:

1. Logs into Azure with OIDC
2. Opens a temporary firewall rule for the GitHub runner IP
3. Runs `python databases/scripts/apply_api_db_schema.py` against the existing Azure PostgreSQL server
4. Removes the temporary firewall rule

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

Required GitHub Environment variable for frontend deployment:

- `AZURE_FRONTEND_CONTAINER_APP_NAME`
