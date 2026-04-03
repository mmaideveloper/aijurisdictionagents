# GitHub Environments Checklist

Use this guide to create `test` and `prod` GitHub Environments that mirror the existing `dev` setup for this repository.

Maintenance rule:

- Whenever a GitHub workflow gains new parameters, or infrastructure/deployment setup changes, update this document in the same change so `test` and `prod` setup instructions stay current.

## Goal

Create two new GitHub Environments:

- `test`
- `prod`

These environments are used by repository workflows that deploy infrastructure, API, frontend, document processor jobs, and mobile builds.

## 1. Create the GitHub Environments

In GitHub:

1. Open the repository.
2. Go to `Settings -> Environments`.
3. Create a new environment named `test`.
4. Create a new environment named `prod`.

Recommended protection rules:

- `test`: optional reviewers, optional wait timer
- `prod`: required reviewers, optional branch restriction to `main`, optional wait timer

## 2. Decide the Azure Resource Layout

For each environment, decide whether it will use:

- a dedicated Azure resource group and dedicated resources, or
- shared Azure resources with different app names and URLs

Recommended approach:

- `dev`: shared developer sandbox
- `test`: dedicated pre-production resources
- `prod`: dedicated production resources

## 3. Create OIDC Federated Credentials in Azure

Each GitHub Environment needs a matching federated credential on the Azure app registration used by GitHub Actions.

The important part is the `subject`, which must exactly match the repository and environment name:

- `repo:mmaideveloper/aijurisdictionagents:environment:test`
- `repo:mmaideveloper/aijurisdictionagents:environment:prod`

Example PowerShell for `test`:

```powershell
$RepoOwner = "mmaideveloper"
$RepoName = "aijurisdictionagents"
$GithubEnvironment = "test"
$ClientId = "<AZURE_APP_CLIENT_ID>"

$federatedCredential = @{
  name        = "github-$RepoOwner-$RepoName-$GithubEnvironment"
  issuer      = "https://token.actions.githubusercontent.com"
  subject     = "repo:${RepoOwner}/${RepoName}:environment:${GithubEnvironment}"
  description = "OIDC federation for GitHub Actions ($GithubEnvironment)"
  audiences   = @("api://AzureADTokenExchange")
} | ConvertTo-Json -Depth 5

$tempFile = Join-Path $env:TEMP "github-federated-credential-$GithubEnvironment.json"
$federatedCredential | Out-File -FilePath $tempFile -Encoding utf8
az ad app federated-credential create --id $ClientId --parameters $tempFile
```

Repeat the same for `prod` with `GithubEnvironment = "prod"`.

## 4. Configure Shared Azure Deployment Variables

Add these GitHub Environment variables to both `test` and `prod` when those environments will run Azure deployment workflows:

| Variable | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | Azure app registration / service principal client ID used by GitHub OIDC |
| `AZURE_TENANT_ID` | Azure tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_RESOURCE_GROUP` | Resource group for the target environment |
| `AZURE_LOCATION` | Azure region, for example `westeurope` |
| `AZURE_CONTAINERAPPS_ENVIRONMENT` | Azure Container Apps environment name |
| `AZURE_CONTAINER_REGISTRY` | ACR name or login server |

## 5. Configure API and Infra Variables

These are used by infrastructure deployment and API deployment workflows:

| Variable | Purpose |
| --- | --- |
| `AZURE_CONTAINER_APP_NAME` | API Azure Container App name |
| `AZURE_FRONTEND_CONTAINER_APP_NAME` | Frontend Azure Container App name provisioned by `infra_deploy` and updated by `web_build_deploy` |
| `AZURE_APPLICATION_INSIGHTS_NAME` | Application Insights resource name |
| `LLM_PROVIDER` | Runtime LLM provider, keep `azurefoundry` for deployed Azure environments |
| `SYSTEM_EMBEDDING_MODEL_OPTION` | Shared embedding mode for API + workers; set `cloud` in deployed Azure environments to preserve Azure/OpenAI embeddings |
| `SYSTEM_EMBEDDING_MODEL` | Shared local embedding model name, recommended default `all-MiniLM-L6-v2` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI / Foundry endpoint URL used by chat and document embeddings |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI chat deployment name used by the API |
| `AZURE_OPENAI_EMBEDDINGS_MODEL` | Azure OpenAI embedding deployment name used for document chunk embeddings, recommended `text-embedding-3-large` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version, keep aligned with `.env.example` unless you intentionally upgrade |
| `AZURE_POSTGRES_SERVER_NAME` | Azure PostgreSQL Flexible Server name |
| `AZURE_POSTGRES_DATABASE_NAME` | API database name |
| `AZURE_POSTGRES_ADMIN_USERNAME` | PostgreSQL admin login |
| `AZURE_STORAGE_ACCOUNT_NAME` | Azure Storage account name |
| `AZURE_STORAGE_CONTAINER_NAME` | Blob container name |
| `AZURE_LOG_ANALYTICS_WORKSPACE_NAME` | Log Analytics workspace name |
| `AZURE_MANAGED_IDENTITY_NAME` | Managed identity name |
| `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME` | Optional laws collector Azure Container App name, default `laws-collector` |
| `AZURE_LAWS_COLLECTOR_MAX_PROBES` | Optional laws collector live probe count per Azure job execution, default `1` |
| `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK` | Optional Slovak laws collector PostgreSQL database name, default `laws_sk` |
| `AZURE_DOCUMENT_PROCESSOR_JOB_NAME` | Optional ACA job name for the document processor, default `document-processor` |
| `AZURE_DOCUMENT_PROCESSOR_CRON_EXPRESSION` | Optional ACA job schedule, default `*/15 * * * *` |
| `DOCUMENT_PROCESSOR_OPTION` | API document-processing mode: use `azure` in deployed environments, `local` only for local/dev API runs without the ACA job |
| `AZURE_POSTGRES_SKU_NAME` | Optional infra sizing value |
| `AZURE_POSTGRES_SKU_TIER` | Optional infra sizing value |
| `AZURE_POSTGRES_VERSION` | Optional PostgreSQL version |
| `AZURE_POSTGRES_STORAGE_SIZE_GB` | Optional PostgreSQL storage size |
| `CORS_ALLOW_ORIGINS` | Optional browser origins allowed to call the API |

Required GitHub Environment secret:

| Secret | Purpose |
| --- | --- |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key used by the API and document processor for chat completions and embeddings |
| `AZURE_POSTGRES_ADMIN_PASSWORD` | PostgreSQL admin password |

Optional GitHub Environment secret:

| Secret | Purpose |
| --- | --- |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | API telemetry connection string when used |

## 6. Configure Frontend Variables

These are used by the web frontend deployment workflow:

| Variable | Purpose |
| --- | --- |
| `AZURE_FRONTEND_CONTAINER_APP_NAME` | Frontend Azure Container App name |

The frontend workflow also reuses these shared Azure deployment variables:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_MANAGED_IDENTITY_NAME`

## 7. Configure Document Processor Variables

These are used by the document processor deployment workflow and by `infra_deploy` when it provisions the initial ACA job shell:

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | Runtime provider for the job, keep `azurefoundry` in Azure deployments |
| `SYSTEM_EMBEDDING_MODEL_OPTION` | Shared embedding mode for the job; use `cloud` in Azure deployments |
| `SYSTEM_EMBEDDING_MODEL` | Shared local embedding model name; keep default `all-MiniLM-L6-v2` unless you intentionally switch models |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI / Foundry endpoint URL used for embeddings |
| `AZURE_OPENAI_EMBEDDINGS_MODEL` | Embedding deployment name used by the job, recommended `text-embedding-3-large` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version for embeddings |
| `AZURE_MANAGED_IDENTITY_NAME` | Identity used by the job |
| `AZURE_STORAGE_ACCOUNT_NAME` | Storage account with uploaded documents |
| `AZURE_STORAGE_CONTAINER_NAME` | Storage container name |
| `AZURE_DOCUMENT_PROCESSOR_LOCATION` | Optional document processor deployment region override, default `westeurope`; keep it aligned with the ACA managed environment region |
| `AZURE_DOCUMENT_PROCESSOR_JOB_NAME` | Optional ACA job name |
| `AZURE_DOCUMENT_PROCESSOR_CRON_EXPRESSION` | Optional 5-field cron schedule, default `*/15 * * * *`; legacy `0 */15 * * * *` values are normalized during deployment |

## 8. Configure Laws Collector Variables

These are used by the laws collector deployment workflow:

| Variable | Purpose |
| --- | --- |
| `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME` | Optional private ACA name for the laws collector, default `laws-collector` |
| `AZURE_LAWS_COLLECTOR_CRON_EXPRESSION` | Optional 5-field cron schedule, default `0 0 * * *`; legacy `0 0 * * * *` values are normalized during deployment |
| `AZURE_LAWS_COLLECTOR_MAX_PROBES` | Optional live probe count per scheduled job execution, default `1` |
| `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK` | Optional PostgreSQL database name for the Slovak laws corpus, default `laws_sk`; the laws deployment applies schema migrations to this database before updating the ACA job |
| `SYSTEM_EMBEDDING_MODEL_OPTION` | Shared embedding mode for the job; use `cloud` in Azure deployments |
| `SYSTEM_EMBEDDING_MODEL` | Shared local embedding model name, default `all-MiniLM-L6-v2` |

The laws collector workflow reuses these shared Azure deployment variables:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_MANAGED_IDENTITY_NAME`
- `AZURE_POSTGRES_SERVER_NAME`
- `AZURE_POSTGRES_ADMIN_USERNAME`
- secret `AZURE_POSTGRES_ADMIN_PASSWORD`

## 9. Configure Mobile Build Variables

The mobile workflow reads the API base URL from the selected GitHub Environment.

Required variable:

| Variable | Purpose |
| --- | --- |
| `API_BASE_URL` | API base URL passed into Flutter builds |

Recommended signing secrets for stable Android release upgrades:

| Secret | Purpose |
| --- | --- |
| `MOBILE_ANDROID_KEYSTORE_BASE64` | Base64-encoded release keystore |
| `MOBILE_ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `MOBILE_ANDROID_KEY_ALIAS` | Key alias inside the keystore |
| `MOBILE_ANDROID_KEY_PASSWORD` | Key password |

Paste those values without extra whitespace. The mobile workflow trims accidental
line breaks, validates the keystore and alias with `keytool`, and warns early if
the selected GitHub Environment contains stale or mismatched signing secrets.

## 10. Populate `test` and `prod`

The fastest approach is:

1. Open the existing `dev` environment.
2. Copy all variables and secrets into a secure local note.
3. Create matching entries in `test`.
4. Replace values with test-specific Azure resource names and URLs.
5. Create matching entries in `prod`.
6. Replace values with prod-specific Azure resource names and URLs.

At minimum, you should expect these values to differ between `test` and `prod`:

- `AZURE_RESOURCE_GROUP`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_APP_NAME`
- `AZURE_FRONTEND_CONTAINER_APP_NAME`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDINGS_MODEL`
- `SYSTEM_EMBEDDING_MODEL_OPTION=cloud`
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2`
- `AZURE_POSTGRES_SERVER_NAME`
- `AZURE_STORAGE_ACCOUNT_NAME`
- `AZURE_APPLICATION_INSIGHTS_NAME`
- `AZURE_DOCUMENT_PROCESSOR_JOB_NAME`
- `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME`
- `AZURE_LAWS_COLLECTOR_MAX_PROBES`
- `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`
- `API_BASE_URL`
- `CORS_ALLOW_ORIGINS`

## 11. Run the Workflows Against the New Environment

Use manual workflow dispatch and set `github_environment` to `test` or `prod`.

Typical order:

1. `infra_deploy`
2. `Database Schema Upgrade` if needed
3. `API Build and Deploy`
4. `Document Processor Build and Deploy`
5. `Laws Collector Build and Deploy`
6. `web_build_deploy`
7. `mobile_flutter_build`

Recommended deployed value:

- `DOCUMENT_PROCESSOR_OPTION=azure` for `dev`, `test`, and `prod`
- `SYSTEM_EMBEDDING_MODEL_OPTION=cloud` for `dev`, `test`, and `prod`
- Keep `DOCUMENT_PROCESSOR_OPTION=local` only in local workstation `.env` files when you want the API process to extract documents immediately without waiting for the ACA job

## 12. Current Workflow Defaults

Some workflows default to `dev` for push-based execution.

That means:

- `API Build and Deploy` now deploys automatically to `dev` on `push` to `main` after tests/build pass
- `API Build and Deploy` waits for Azure Container App provisioning to settle before applying secret and environment updates, which reduces transient `ContainerAppOperationInProgress` failures during deployment
- `API Build and Deploy` now fails during environment validation when `AZURE_OPENAI_API_KEY` is empty, because the deployed API always requires that secret for Azure OpenAI access
- `Laws Collector Build and Deploy` now deploys automatically to `dev` on `push` to `main` after its tests/build pass
- `test` and `prod` remain manual `workflow_dispatch` targets unless a workflow is explicitly changed to auto-deploy them

## 13. Quick Validation Checklist

After setup, verify:

- GitHub Environment `test` exists
- GitHub Environment `prod` exists
- OIDC federated credential exists for `test`
- OIDC federated credential exists for `prod`
- `API_BASE_URL` is set in both environments
- required Azure variables are set in both environments
- required secrets are set in both environments
- `workflow_dispatch` works with `github_environment=test`
- `workflow_dispatch` works with `github_environment=prod`
