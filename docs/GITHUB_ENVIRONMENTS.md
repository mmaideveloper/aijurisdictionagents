# GitHub Environments Checklist

Use this guide to create `test` and `prod` GitHub Environments that mirror the existing `dev` setup for this repository.

Maintenance rule:

- Whenever a GitHub workflow gains new parameters, or infrastructure/deployment setup changes, update this document in the same change so `test` and `prod` setup instructions stay current.

## Temporary encrypted `dev` secret export

The manual `Temporary encrypted dev secrets export` workflow is a short-lived,
operator-only migration aid. It reads the explicitly allowlisted secrets from the
protected `dev` GitHub Environment, creates a dotenv file on the hosted runner,
encrypts it to the repository operator's age recipient, and uploads only the
encrypted file plus its SHA-256 checksum. The artifact retention period is one day.

Safety requirements:

- Require environment approval for `dev` before running the job.
- Enter `EXPORT_DEV_SECRETS` in the workflow confirmation input.
- Never print, inspect, or upload the plaintext file.
- Delete the workflow after the one-time transfer is complete.
- Keep `C:\__jurisdigta\age-identity.txt` private and outside Git.

Download the workflow artifact, extract it under `C:\__jurisdigta`, and decrypt it:

```powershell
age --decrypt `
  --identity C:\__jurisdigta\age-identity.txt `
  --output C:\__jurisdigta\.env `
  C:\__jurisdigta\dev-secrets.env.age
```

Confirm the encrypted download before decryption when the checksum file is present:

```powershell
$expected = (Get-Content C:\__jurisdigta\dev-secrets.env.age.sha256).Split()[0]
$actual = (Get-FileHash C:\__jurisdigta\dev-secrets.env.age -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "Encrypted artifact checksum mismatch" }
```

The resulting `.env` contains only the 12 allowlisted GitHub Environment secrets;
it does not include ordinary `dev` Environment variables. Apply restrictive local
ACLs and merge it with the required non-secret configuration rather than treating
it as a complete runtime configuration.

## Goal

Create two new GitHub Environments:

- `test`
- `prod`
- `Prod` if you use the capitalized corporate web production target

These environments are used by repository workflows that deploy infrastructure, API, frontend, document processor jobs, and mobile builds.
The corporate website workflow additionally exposes a capitalized `Prod` manual dispatch option for hosts configured under that exact GitHub Environment name.
The self-managed production server workflow uses only the lowercase `prod` GitHub Environment and deploys to `jurisdigta-server` over SSH.

## 1. Create the GitHub Environments

In GitHub:

1. Open the repository.
2. Go to `Settings -> Environments`.
3. Create a new environment named `test`.
4. Create a new environment named `prod`.
5. Create a new environment named `Prod` if the corporate website should deploy through the capitalized production environment.

Recommended protection rules:

- `test`: optional reviewers, optional wait timer
- `prod`: required reviewers, optional branch restriction to `main`, optional wait timer

### Production build gate

Production deployment is fail-closed. Before approving or manually dispatching any workflow that
targets `prod` or `Prod`, identify the exact commit SHA that will be deployed and confirm that every
applicable build, lint, type-check, unit/integration test, E2E gate, image build, and other required
check has completed successfully for that SHA.

A failed, cancelled, pending, or missing applicable check blocks production deployment. Fix the
underlying problem on a dedicated task branch, rerun the affected checks, and wait until all
applicable checks are green. Do not bypass the gate by rerunning only a deploy job, choosing another
manual workflow, or deploying an unverified local checkout. If the target SHA changes, validate the
new SHA again. The deployment record must retain the exact SHA and links to the successful GitHub
Actions runs without copying secrets or personal data into the evidence.

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
- `repo:mmaideveloper/aijurisdictionagents:environment:Prod` if using the capitalized corporate web environment

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
Repeat for `Prod` with `GithubEnvironment = "Prod"` if using the capitalized corporate web environment.

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
| `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` | Long random secret used to encrypt model provider credentials stored in API database routing tables |
| `SYSTEM_EMBEDDING_MODEL_OPTION` | Shared embedding mode for API + workers; worker deployments now default to `local`, while `cloud` remains available when you want Azure/OpenAI embeddings |
| `SYSTEM_EMBEDDING_MODEL` | Shared local embedding model name, recommended default `all-MiniLM-L6-v2` |
| `SYSTEM_EMBEDDING_DEVICE` | Local embedding device selector, default `auto`; workers try CUDA/MPS when supported and fall back to CPU on unavailable GPU support or runtime errors |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI / Foundry endpoint URL used by document embeddings; chat endpoint belongs in `ai_model_providers` |
| `AZURE_OPENAI_EMBEDDINGS_MODEL` | Azure OpenAI embedding deployment name used for document chunk embeddings, recommended `text-embedding-3-large` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version, keep aligned with `.env.example` unless you intentionally upgrade |
| `JURISDIGTA_UNLIMITED_ACCESS_EMAILS` | Privileged comma- or semicolon-separated email allowlist for controlled test/operator accounts with unlimited case/document access; default `mmaideveloper@gmail.com` |
| `JURISDIGTA_ADMIN_EMAILS` | Global admin fallback allowlist for `/app/admin` and admin APIs. Users with database `role=admin` are also authorized. Cloudflare Access must provide `cf-access-authenticated-user-email`; keep this restricted to approved operator accounts. |
| `AZURE_POSTGRES_SERVER_NAME` | Azure PostgreSQL Flexible Server name |
| `AZURE_POSTGRES_DATABASE_NAME` | API database name |
| `AZURE_POSTGRES_ADMIN_USERNAME` | PostgreSQL admin login |
| `AZURE_STORAGE_ACCOUNT_NAME` | Azure Storage account name |
| `AZURE_STORAGE_CONTAINER_NAME` | Blob container name |
| `AZURE_LOG_ANALYTICS_WORKSPACE_NAME` | Log Analytics workspace name |
| `AZURE_MANAGED_IDENTITY_NAME` | Managed identity name |
| `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME` | Optional laws collector Azure Container App name, default `laws-collector` |
| `AZURE_LAWS_COLLECTOR_MAX_PROBES` | Optional laws collector live probe count per Azure job execution, default `1` |
| `AZURE_LAWS_STORAGE_CONTAINER_NAME` | Optional blob container for immutable Slov-Lex ZIP source bundles, default `laws-collection-sk` |
| `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK` | Optional Slovak laws collector PostgreSQL database name, default `laws_sk`; the API deploy also uses it to inject `LAWS_DB_CLOUD` so `/version` can read the latest collector metadata |
| `LAWS_COLLECTOR_IMPORT` | Laws collector import mode. Default `zip`; set `one_law_url` to keep the older sequential per-law probe importer |
| `LAWS_COLLECTOR_IMPORT_ZIP_MAX_THREADS` | Optional ZIP import worker count for archive/monthly bundle law-group import. Default `4`; bootstrap recommendation `10` |
| `LAWS_STORAGE_CLOUD` | Optional explicit blob container URL override for laws source storage. When unset, the deploy derives `https://<AZURE_STORAGE_ACCOUNT_NAME>.blob.core.windows.net/<AZURE_LAWS_STORAGE_CONTAINER_NAME or laws-collection-sk>` |
| `AZURE_DOCUMENT_PROCESSOR_JOB_NAME` | Optional ACA job name for the document processor, default `document-processor` |
| `AZURE_DOCUMENT_PROCESSOR_CRON_EXPRESSION` | Optional ACA job schedule, default `*/15 * * * *`; comma-list values such as `0,15,30,45 * * * *` are supported |
| `DOCUMENT_PROCESSOR_MAX_RUNNING_TIME` | Optional max runtime per document-processor Azure run in minutes; default `15`, set `0` for unlimited |
| `DOCUMENT_PROCESSOR_OPTION` | API document-processing mode; Azure API deployments default to `azure`, while `local` is only for local/dev API runs without the ACA job |
| `EMAIL_TRANSPORT` | API email transport. Use `smtp` for deployed email delivery; use `log` only for queue/log testing |
| `EMAIL_SENDER` | Outbound sender address, default `no-reply@jurisdigta.eu` |
| `EMAIL_SMTP_HOST` | SMTP host, default `mail.webhouse.sk` |
| `EMAIL_SMTP_PORT` | SMTP port, default `587` |
| `EMAIL_SMTP_USE_TLS` | SMTP STARTTLS flag, default `true` |
| `EMAIL_SMTP_USERNAME` | SMTP username, default `no-reply@jurisdigta.eu` |
| `EMAIL_SCHEDULER_ENABLED` | Optional email scheduler toggle for API replicas, default `true`; set `false` when a dedicated Azure email scheduler job is deployed |
| `EMAIL_SCHEDULER_INTERVAL_SECONDS` | Optional scheduler interval for Azure API replicas, default `60` |
| `CAR_VALIDATION_API_BASE_URL` | Optional vehicle validation API base URL, for example `https://www.databazavozidiel.sk`; leave unset to skip live car API checks |
| `AZURE_POSTGRES_SKU_NAME` | Optional infra sizing value |
| `AZURE_POSTGRES_SKU_TIER` | Optional infra sizing value |
| `AZURE_POSTGRES_VERSION` | Optional PostgreSQL version |
| `AZURE_POSTGRES_STORAGE_SIZE_GB` | Optional PostgreSQL storage size |
| `CORS_ALLOW_ORIGINS` | Optional browser origins allowed to call the API. Include browser-hosted frontend origins such as `https://web.jurisdigta.eu` and `https://agent.jurisdigta.eu`; self-managed prod deploy appends those two origins when starting the API container |
| `MCP_CORS_ALLOW_ORIGINS` | Optional browser origins allowed to call the dedicated MCP service; default production value should include `https://mcp.jurisdigta.eu` |
| `INTERNAL_MCP_BASE_URL` | Optional API-to-MCP base URL for internal assistant law lookups. Self-managed prod injects `http://jurisdigta-mcp:8070` into the API container so chat answers can call the same MCP `searchLaws` and `getLawText` tools as external assistants |
| `INTERNAL_MCP_SHARED_SECRET` | Optional service-to-service secret for API-originated internal MCP tool calls. If unset, the API and MCP service use the existing `MCP_API_JWT_SECRET`; set this only when you want a separate internal shared secret in both containers |
| `INTERNAL_MCP_REQUEST_TIMEOUT_SECONDS` | Bounded timeout per internal JSON-RPC attempt, default `10` |
| `INTERNAL_MCP_RETRY_ATTEMPTS` | Bounded transient API-to-MCP attempts, default `3` |
| `INTERNAL_MCP_RETRY_BACKOFF_SECONDS` | Delay between internal MCP attempts, default `1` |
| `INTERNAL_MCP_STARTUP_PROBE_ENABLED` | Optional fail-closed API startup probe, default `false`; the self-managed production deploy independently runs the authenticated probe as a required post-start gate |
| `INTERNAL_MCP_STARTUP_PROBE_ATTEMPTS` | Startup-only authenticated probe attempt cap, default `30` |
| `MCP_PORT` | Local/self-managed MCP service port when using Docker Compose, default `8070` |
| `JURISDIGTA_WEB_PUBLIC_BASE_URL` | Public production frontend used by required post-deployment browser tests; default `https://web.jurisdigta.eu` |
| `MCP_OAUTH_TEST_MFA_BYPASS_ENABLED` | Optional, default `false`; enables password-only MFA bypass only for hardcoded synthetic MCP OAuth E2E emails when the allowlist and expiry are also set |
| `MCP_OAUTH_TEST_MFA_BYPASS_EMAILS` | Optional synthetic E2E allowlist; use `mcp-claude-test-free@jurisdigta.eu,mcp-claude-test-paid@jurisdigta.eu` only for controlled connector validation |
| `MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT` | Optional ISO timestamp for the synthetic MCP OAuth E2E bypass, for example `2030-01-01T00:00:00Z` |
| `CONTACT_CAPTCHA_REQUIRED` | Set `true` in public environments to require Cloudflare Turnstile verification for `POST /v1/contact` |
| `CONTACT_RATE_LIMIT_MAX_REQUESTS` | Optional backend per-IP contact form throttle, default `5` |
| `CONTACT_RATE_LIMIT_WINDOW_SECONDS` | Optional backend per-IP contact form throttle window, default `600` |

Required GitHub Environment secret:

| Secret | Purpose |
| --- | --- |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key used by the API and document processor for chat completions and embeddings |
| `MCP_API_JWT_SECRET` | Long random secret used to sign MCP OAuth/JWT bearer tokens for ChatGPT, Claude, VS Code, and other remote MCP clients |
| `MCP_OAUTH_AUTHORIZATION_RESPONSE_ISS` | Optional issuer callback flag for strict OAuth clients; default `true`, keep enabled for Claude web custom connectors |
| `JURISDIGTA_E2E_TEST_USER_PASSWORD` | Secret used by `python scripts/provision_e2e_users.py` to create/update the synthetic free and paid E2E accounts; do not expose it in logs or source |
| `AZURE_POSTGRES_ADMIN_PASSWORD` | PostgreSQL admin password |

Optional and conditional GitHub Environment secrets:

| Secret | Purpose |
| --- | --- |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional override for Application Insights connection string; API and Azure workers otherwise resolve it from `AZURE_APPLICATION_INSIGHTS_NAME` during deployment |
| `EMAIL_SMTP_PASSWORD` | SMTP mailbox password; required by `API Build and Deploy` when `EMAIL_TRANSPORT=smtp` |
| `CAR_VALIDATION_API_KEY` | Optional vehicle validation API key, injected as a Container App secret when configured |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key for backend contact-form verification when `CONTACT_CAPTCHA_REQUIRED=true` |

Optional telemetry variable:

| Variable | Purpose |
| --- | --- |
| `AZURE_MONITOR_ENABLED` | Set to `true` only in `test` or `prod` environments where API and worker telemetry should be exported to Azure Monitor. Defaults to disabled, even when `APPLICATIONINSIGHTS_CONNECTION_STRING` is present. |

## 6. Configure Frontend Variables

These are used by the web frontend deployment workflow:

| Variable | Purpose |
| --- | --- |
| `AZURE_FRONTEND_CONTAINER_APP_NAME` | Frontend Azure Container App name |

The frontend deployment workflow runs the full frontend gate before deployment: lint, unit tests, Playwright E2E tests, and build. `npm run test:e2e` starts the Vite app locally and uses mocked API responses, so no additional GitHub Environment variables or secrets are required for the E2E gate. If any Playwright test fails, `web_build_deploy` stops before building or deploying the Azure Container App image.

The frontend workflow also reuses these shared Azure deployment variables:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_MANAGED_IDENTITY_NAME`

## 6a. Configure Corporate Web FTP Variables

These are used by `.github/workflows/corporate_web_deploy.yml`, whose manual environment choices are `dev`, `test`, `prod`, and `Prod`.

| Variable | Purpose |
| --- | --- |
| `corporate_web_ftp` | FTP server host for corporate web deployment |
| `corporate_web_ftp_username` | FTP username |
| `corporate_web_ftp_dir` | FTP remote directory for the selected corporate web hostname/subdomain. It must be dedicated to this site because the deploy uses clean-slate upload for that folder |
| `CORPORATE_WEB_API_BASE_URL` | API base URL injected into corporate web contact form; set this to the dev/test/prod API URL for the matching environment. `/v1` or `/v1/contact` suffixes are accepted. When unset, the workflow falls back to `API_BASE_URL`, then `https://api.jurisdigta.eu` |
| `TURNSTILE_SITE_KEY` | Public Cloudflare Turnstile site key injected into the static contact form |

Required secret:

| Secret | Purpose |
| --- | --- |
| `corporate_web_ftp_password` | FTP password |

Configure the same entries on `Prod` when using the capitalized corporate web production environment.

## 7. Configure Document Processor Variables

These are used by the document processor deployment workflow and by `infra_deploy` when it provisions the initial ACA job shell:

| Variable | Purpose |
| --- | --- |
| `SYSTEM_EMBEDDING_MODEL_OPTION` | Shared embedding mode for the job; default `local`, or set `cloud` for Azure OpenAI embeddings |
| `SYSTEM_EMBEDDING_MODEL` | Shared local embedding model name; keep default `all-MiniLM-L6-v2` unless you intentionally switch models. In `local` mode the deploy prefetches that model into the worker image before `az acr build` |
| `SYSTEM_EMBEDDING_DEVICE` | Local embedding device selector for `local` mode, default `auto`; use `cpu` to force CPU-only execution |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI / Foundry endpoint URL used for embeddings |
| `AZURE_OPENAI_EMBEDDINGS_MODEL` | Embedding deployment name used by the job, recommended `text-embedding-3-large` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version for embeddings |
| `AZURE_MANAGED_IDENTITY_NAME` | Identity used by the job |
| `AZURE_STORAGE_ACCOUNT_NAME` | Storage account with uploaded documents |
| `AZURE_STORAGE_CONTAINER_NAME` | Storage container name |
| `AZURE_DOCUMENT_PROCESSOR_LOCATION` | Optional document processor deployment region override, default `westeurope`; keep it aligned with the ACA managed environment region |
| `AZURE_DOCUMENT_PROCESSOR_JOB_NAME` | Optional ACA job name |
| `AZURE_DOCUMENT_PROCESSOR_CRON_EXPRESSION` | Optional 5-field cron schedule, default `*/15 * * * *`; legacy `0 */15 * * * *` values are normalized during deployment |
| `DOCUMENT_PROCESSOR_MAX_RUNNING_TIME` | Optional max runtime per Azure job execution in minutes; default `15`, set `0` for unlimited |

## 8. Configure Laws Collector Variables

These are used by the laws collector deployment workflow:

| Variable | Purpose |
| --- | --- |
| `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME` | Optional private ACA name for the laws collector, default `laws-collector` |
| `AZURE_LAWS_COLLECTOR_CRON_EXPRESSION` | Optional 5-field cron schedule, default `0 0 * * *`; legacy `0 0 * * * *` values are normalized during deployment |
| `AZURE_LAWS_COLLECTOR_MAX_PROBES` | Optional live probe count per scheduled job execution, default `1` |
| `LAWS_COLLECTOR_MAX_RUNNING_TIME` | Optional max runtime per laws collector Azure job execution in minutes; default `60`, set `0` for unlimited |
| `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK` | Optional PostgreSQL database name for the Slovak laws corpus, default `laws_sk`; the laws deployment applies schema migrations to this database before updating the ACA job |
| `AZURE_LAWS_STORAGE_CONTAINER_NAME` | Optional blob container that stores immutable Slov-Lex ZIP source bundles, default `laws-collection-sk` |
| `LAWS_COLLECTOR_IMPORT` | Import mode for the live laws collector job. Default `zip`, which bootstraps from the full Slov-Lex archive and then continues from monthly `exportZmeny.zip` deltas |
| `LAWS_COLLECTOR_IMPORT_ZIP_MAX_THREADS` | Optional ZIP import worker count for archive/monthly bundle law-group import. Default `4`; bootstrap recommendation `10` |
| `LAWS_STORAGE_CLOUD` | Optional explicit blob container URL override for laws source storage. Normally leave this unset and let the deploy derive it from `AZURE_STORAGE_ACCOUNT_NAME` plus `AZURE_LAWS_STORAGE_CONTAINER_NAME` |
| `SYSTEM_EMBEDDING_MODEL_OPTION` | Shared embedding mode for the job; default `local`, or set `cloud` for Azure OpenAI embeddings |
| `SYSTEM_EMBEDDING_MODEL` | Shared local embedding model name, default `all-MiniLM-L6-v2`. In `local` mode the deploy prefetches that model into the worker image before `az acr build` |
| `SYSTEM_EMBEDDING_DEVICE` | Local embedding device selector for `local` mode, default `auto`; use `cpu` to force CPU-only execution |

Court-decision collector settings are required before enabling court-decision MCP/API search in an environment:

| Variable | Notes |
| --- | --- |
| `COURT_DECISIONS_DB_BACKEND` | Must be `postgres` |
| `COURT_DECISIONS_DB_CLOUD` | Dedicated PostgreSQL connection string for the court decisions database, for example `court_decisions_sk`; keep it separate from laws collector databases |
| `COURT_DECISIONS_STORAGE_LOCAL` | Runtime artifact path, default `./runs/storage/court-decision-collector/files/sk` |
| `COURT_DECISIONS_SOURCE_BASE_URL` | InfoSud API base URL, default `https://obcan.justice.sk/pilot/api/ress-isu-service/v1` |
| `COURT_DECISIONS_SOURCE_TIMEOUT_SECONDS` | InfoSud request timeout, default `90`; increase only with retry logging enabled so slow upstream calls remain traceable |
| `COURT_DECISIONS_SOURCE_RETRY_ATTEMPTS` | InfoSud retry attempts for connect/read timeouts and connection errors, default `3` |
| `COURT_DECISIONS_SOURCE_RETRY_BACKOFF_SECONDS` | Sleep between InfoSud retries, default `5` |
| `COURT_DECISIONS_WORKER_POLL_HOURS` | Future scheduled worker cadence, default `1` |
| `COURT_DECISIONS_EMBEDDING_DIMENSIONS` | Stored vector dimensions, default `32` |
| `COURT_DECISIONS_IMPORT_LIMIT` | Bounded import page size for smoke runs, default `25` |
| `COURT_DECISIONS_DAILY_NEW_LIMIT` | Maximum newly discovered decisions committed per UTC day, default `10000`; overflow remains new-priority work before backfill |
| `COURT_DECISIONS_DISCOVERY_OVERLAP_PAGES` | Source pages re-read before a growth watermark to tolerate page-boundary movement, default `2` |
| `COURT_DECISIONS_BACKFILL_PAGES_PER_CYCLE` | Historical reconciliation pages per hourly cycle after the new queue is empty, default `10` |
| `COURT_DECISIONS_MAX_PDF_BYTES` | Maximum accepted on-demand InfoSud PDF size, default `26214400` (25 MiB) |
| `COURT_DECISION_MCP_SEARCH_TIMEOUT_MS` | Scoped PostgreSQL statement timeout for MCP court-decision search, default `600000`; do not replace the global legal-search timeout with this value |
| `COURT_DECISIONS_ALLOW_INTERNAL_RAW_MCP` | Keep `false` for external MCP users; set `true` only for a controlled internal runtime approved to retrieve raw court-decision text |

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

## 9. Configure Email Scheduler Job Variables

These are used by the dedicated email scheduler deployment workflow and by `infra_deploy` when it provisions the initial ACA job shell:

| Variable | Purpose |
| --- | --- |
| `AZURE_EMAIL_SCHEDULER_JOB_NAME` | Optional ACA job name for the email scheduler, default `email-scheduler` |
| `AZURE_EMAIL_SCHEDULER_CRON_EXPRESSION` | Optional 5-field cron schedule for the email scheduler ACA job, default `*/5 * * * *`; legacy `0 */5 * * * *` values are normalized during deployment |
| `EMAIL_TRANSPORT` | Email delivery transport for the job, normally `smtp` in Azure |
| `EMAIL_SENDER` | Outbound sender address, default `no-reply@jurisdigta.eu` |
| `EMAIL_SMTP_HOST` | SMTP host, default `mail.webhouse.sk` |
| `EMAIL_SMTP_PORT` | SMTP port, default `587` |
| `EMAIL_SMTP_USE_TLS` | SMTP STARTTLS flag, default `true` |
| `EMAIL_SMTP_USERNAME` | SMTP username, default `no-reply@jurisdigta.eu` |

Required secret when `EMAIL_TRANSPORT=smtp`:

| Secret | Purpose |
| --- | --- |
| `EMAIL_SMTP_PASSWORD` | SMTP mailbox password used by the email scheduler ACA job |

The email scheduler workflow reuses these shared Azure deployment variables:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_CONTAINERAPPS_ENVIRONMENT`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_MANAGED_IDENTITY_NAME`
- `AZURE_POSTGRES_SERVER_NAME`
- `AZURE_POSTGRES_DATABASE_NAME`
- `AZURE_POSTGRES_ADMIN_USERNAME`
- secret `AZURE_POSTGRES_ADMIN_PASSWORD`

Keep `EMAIL_SCHEDULER_ENABLED=false` on the API Container App when this dedicated email job is enabled, so API replicas only write to `email_outbox`.

## 10. Configure Mobile Build Variables

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

### Plugin release workflow

`.github/workflows/plugin_release.yml` packages `plugins/jurisdigta/` and the
repository marketplace into a versioned ZIP, creates a SHA-256 checksum, and
publishes both files as a GitHub prerelease.

- Dispatch the workflow manually from `main`.
- The version and immutable tag come from
  `plugins/jurisdigta/.codex-plugin/plugin.json`.
- The workflow uses repository `GITHUB_TOKEN` with scoped `contents: write`
  permission.
- It does not use the `test` or `prod` GitHub Environments.
- No variables or secrets must be added to either Environment.
- Plugin releases use `make_latest: false`, preserving the stable mobile APK
  release returned by GitHub's latest-release API.

## 11. Configure Self-Managed Production Server Variables

These are used by `.github/workflows/self_managed_prod_deploy.yml` to deploy API, MCP, frontend web, the document processor, laws collector, and system status monitoring to the Ubuntu `jurisdigta-server`.

Before the SSH deployment job starts, the workflow runs a GitHub-hosted `e2e_gate` job with `npm ci`, Chromium installation, and `npm run test:e2e` from `frontend/aijurisdictionfronend`. The E2E tests use local Vite plus mocked API responses, so the `prod` environment does not need extra secrets for this gate. If any E2E test fails, the deploy job is skipped and production is not updated. The self-hosted runner must also be able to pull and run `mcr.microsoft.com/playwright:v1.58.2-noble`; the required production MCP browser gate uses that pinned container instead of host-installed Chromium so Ubuntu 26.04 does not exceed Playwright's supported host matrix.

The workflow must run on a repository self-hosted runner with labels `self-hosted`, `Linux`, `X64`, and `jurisdigta-prod`. Keep this runner on the trusted server or trusted private network that can reach `jurisdigta-server` over SSH. Do not run the production deployment from a GitHub-hosted runner when `JURISDIGTA_SSH_HOST` is a private LAN address such as `192.168.1.25`.

The workflow does not store application runtime secrets in GitHub. Keep Azure OpenAI, PostgreSQL, SMTP, MCP JWT, and API secrets in the server-local file:

```text
/srv/jurisdigta/secrets/jurisdigta.env
```

Use `docs/ENV_SYNC.md` and `.\scripts\sync_jurisdigta_env.ps1` to keep the
server-local file aligned with `.env.example`. Missing keys are added to local
`.env` as `unknown-variable` until the real secret is known.

Required `prod` GitHub Environment variable:

| Variable | Purpose |
| --- | --- |
| `JURISDIGTA_SSH_HOST` | SSH host or DNS name for `jurisdigta-server`; production currently uses `192.168.1.25`, which is valid only when the self-hosted `jurisdigta-prod` runner can reach that private LAN address |

Optional `prod` GitHub Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `JURISDIGTA_SSH_PORT` | `22` | SSH port |
| `JURISDIGTA_SSH_USER` | `jurisdigta-admin` | Deployment user |
| `JURISDIGTA_DEPLOY_ROOT` | `/srv/jurisdigta` | Server deployment root |
| `JURISDIGTA_ENV_FILE` | `/srv/jurisdigta/secrets/jurisdigta.env` | Server-local runtime env file |
| `JURISDIGTA_WEB_API_BASE_URL` | `https://api.jurisdigta.eu` | API URL embedded into the frontend build |
| `JURISDIGTA_WEB_PUBLIC_BASE_URL` | `https://web.jurisdigta.eu` | Public frontend URL exercised by the required production post-deployment browser test |
| `JURISDIGTA_API_PORT` | `8080` | Server-local API bind port |
| `JURISDIGTA_MCP_PORT` | `8070` | Server-local MCP bind port |
| `JURISDIGTA_WEB_PORT` | `8090` | Server-local web bind port |
| `JURISDIGTA_COURT_DECISIONS_DATABASE_NAME` | `court_decisions_sk` | Dedicated PostgreSQL database name for the court-decision vector store used by MCP court-decision search |
| `JURISDIGTA_LAWS_COLLECTOR_RUN_MODE` | `continuous` | Self-managed laws collector runtime mode. `continuous` runs a restartable Docker container that sleeps between live polls; `scheduled` keeps the legacy daily cron wrapper |
| `JURISDIGTA_INSTALL_DOCUMENT_PROCESSOR_CRON` | `1` | Install/update the self-managed document processor cron wrapper; set `0` only for manual worker runs |
| `JURISDIGTA_DOCUMENT_PROCESSOR_CRON_EXPRESSION` | `*/15 * * * *` | Five-field server cron schedule for document processing |
| `JURISDIGTA_DOCUMENT_PROCESSOR_LIMIT` | `20` | Max pending documents processed per scheduled run |
| `JURISDIGTA_EMAIL_SCHEDULER_INTERVAL_SECONDS` | `5` | Email outbox poll interval in seconds for near-immediate self-managed delivery; minimum accepted value is `5` |
| `INSTALL_OLLAMA` | `1` | Self-managed deploy installs/configures Ollama and pulls the seeded free-plan model `qwen3:1.7b`; set `0` only for controlled rollback or prevalidated manual install |
| `OLLAMA_METRICS_PORT` | `9109` | Host-local Prometheus exporter port for Ollama runtime metrics |
| `OLLAMA_METRICS_TIMEOUT` | `5` | Timeout in seconds for Ollama exporter API probes |

The production runtime secret file referenced by `JURISDIGTA_ENV_FILE` must also contain
`LOCAL_LLM_REQUEST_TIMEOUT_SECONDS=600` and `LOCAL_LLM_REQUEST_VISIBLE_PROGRESS=15`.
The deploy script passes both values explicitly into the API and MCP containers. They are
runtime settings, not GitHub Environment variables or secrets.

Required `prod` GitHub Environment secret:

| Secret | Purpose |
| --- | --- |
| `JURISDIGTA_SSH_PRIVATE_KEY` | Private key for a deploy-only SSH key authorized on `jurisdigta-server` |

Recommended environment protection:

- Require reviewers for `prod`.
- Restrict deployment to `main` unless a hotfix ref is intentionally selected in manual dispatch.
- Rotate `JURISDIGTA_SSH_PRIVATE_KEY` if it is copied outside GitHub secrets or an approved operator vault.

Server-local `jurisdigta.env` must include at least:

- `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`
- `AZURE_OPENAI_EMBEDDINGS_MODEL`
- `AZURE_OPENAI_API_VERSION`
- `LOCAL_POSTGRES_DB`
- `LOCAL_POSTGRES_USER`
- `LOCAL_POSTGRES_PASSWORD`
- `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK=laws_sk`
- `MCP_API_JWT_SECRET`
- `MCP_PUBLIC_BASE_URL=https://mcp.jurisdigta.eu`
- `INTERNAL_MCP_BASE_URL=http://jurisdigta-mcp:8070` is injected by the self-managed deploy script for the API container; it normally does not need to be stored in the GitHub Environment.
- `MCP_OAUTH_ALLOWED_REDIRECT_HOSTS=chatgpt.com,chat.openai.com,claude.ai,vscode.dev,www.perplexity.ai,localhost,127.0.0.1,::1`
- `MCP_OTP_REUSE_WINDOW_HOURS=24`
- `MCP_OAUTH_TEST_MFA_BYPASS_ENABLED=false` except during explicit Claude/MCP connector validation
- `MCP_OAUTH_TEST_MFA_BYPASS_EMAILS=mcp-claude-test-free@jurisdigta.eu,mcp-claude-test-paid@jurisdigta.eu` only when the bypass is intentionally enabled
- `MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT=2030-01-01T00:00:00Z` for the approved synthetic-account validation window
- `JURISDIGTA_E2E_TEST_USER_PASSWORD=<secret>` for the two approved synthetic accounts. The post-deployment job reads it only on the trusted self-hosted runner and never stores it in a GitHub artifact or log.
- `JURISDIGTA_UNLIMITED_ACCESS_EMAILS=mmaideveloper@gmail.com`
- `JURISDIGTA_ADMIN_EMAILS=mmaideveloper@gmail.com`
- `DOCUMENT_PROCESSOR_OPTION=azure`
- `INSTALL_OLLAMA=1` so the self-managed deploy installs Ollama and pulls `qwen3:1.7b`
- `DOCUMENT_PROCESSOR_MAX_RUNNING_TIME=15` or another bounded runtime in minutes
- email/Turnstile settings when those production features are enabled

After the API database is initialized, configure chat routes in the database/admin API:

- `local_ollama_default`: provider `local_ollama`, model `qwen3:1.7b`, marked as free-plan default. On self-managed prod the deploy script stores the private Docker gateway URL, for example `http://172.18.0.1:11434/v1`, so API containers can reach the host-local Ollama service without exposing it publicly.
- `azure_foundry_gpt_4o_mini`: provider `azure_foundry`, EU data-zone capable, exact model/deployment `gpt-4o-mini`.
- Add the Azure Foundry endpoint to `ai_model_providers.base_url`.
- Add the Azure Foundry API key or token through `/v1/admin/ai-models/providers/{provider_id}/credentials` so it is stored encrypted in `ai_model_credentials`.

Optional server-local monitoring setting in `/srv/jurisdigta/app/Deployment/monitoring/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONITORING_APP_DOCKER_NETWORK` | `aijuristiction-api_default` | Docker network where Prometheus Blackbox Exporter and status-exporter resolve `jurisdigta-api` and `jurisdigta-mcp` by container name |
| `GRAFANA_DEFAULT_HOME_DASHBOARD_PATH` | `/var/lib/grafana/dashboards/jurisdigta-application-performance.json` | Grafana dashboard JSON shown as the default home dashboard after login |
| `OLLAMA_METRICS_PORT` | `9109` | Host-local Ollama Prometheus exporter port scraped by Prometheus through `host.docker.internal` |

The monitoring stack also loads `Deployment/monitoring/prometheus-rules/jurisdigta-ai-models.yml`
for Ollama red-state and high paid-model token/cost alerts. No extra GitHub
Environment secret is required for those default thresholds.

Minimal workflow validation after setup:

1. Run `Self-Managed Prod Deploy` with `repo_ref=main`.
2. Confirm the workflow summary lists the expected host, ref, and local ports.
3. Confirm the required `issue-646-prod-mcp-laws-<run_id>` artifact contains one Azure Foundry `gpt-5-mini` final-state screenshot and a sanitized result manifest. The workflow must fail if Azure Foundry `gpt-5-mini` fails, falls back, or lacks the matching MCP citation. Qwen is intentionally not invoked by this automatic gate.
4. Confirm `MCP_OAUTH_TEST_MFA_BYPASS_ENABLED=false` in `/srv/jurisdigta/secrets/jurisdigta.env` after the job and that `jurisdigta-mcp` is healthy. The cleanup trap must run on success, failure, timeout, and cancellation.
5. Confirm the document processor image and cron wrapper exist on the server:

```bash
docker image inspect jurisdigta-document-processor:local >/dev/null
test -x /srv/jurisdigta/ops/run_document_processor.sh
crontab -l | grep run_document_processor.sh
systemctl is-active --quiet ollama
curl -fsS http://127.0.0.1:11434/api/tags || curl -fsS "http://$(docker network inspect aijuristiction-api_default --format '{{(index .IPAM.Config 0).Gateway}}'):11434/api/tags"
curl -fsS http://127.0.0.1:11434/v1/models || curl -fsS "http://$(docker network inspect aijuristiction-api_default --format '{{(index .IPAM.Config 0).Gateway}}'):11434/v1/models"
```

6. From outside the server, validate the Cloudflare Tunnel routes:

```bash
curl -fsS https://api.jurisdigta.eu/health
curl -I https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/mcp
curl -fsS https://web.jurisdigta.eu/health
curl -fsS https://agent.jurisdigta.eu/health
curl -I https://agent.jurisdigta.eu/app/assistant
```

## 12. Populate `test` and `prod`

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
- `AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`
- `AZURE_OPENAI_ENDPOINT` for embeddings when cloud embeddings are enabled
- `AZURE_OPENAI_EMBEDDINGS_MODEL`
- `SYSTEM_EMBEDDING_MODEL_OPTION=local`
- `SYSTEM_EMBEDDING_MODEL=all-MiniLM-L6-v2`
- `SYSTEM_EMBEDDING_DEVICE=auto`
- `AZURE_POSTGRES_SERVER_NAME`
- `AZURE_STORAGE_ACCOUNT_NAME`
- `AZURE_APPLICATION_INSIGHTS_NAME`
- `AZURE_DOCUMENT_PROCESSOR_JOB_NAME`
- `DOCUMENT_PROCESSOR_MAX_RUNNING_TIME`
- `JURISDIGTA_LAWS_COLLECTOR_RUN_MODE=continuous` for self-managed prod; Azure laws collector jobs remain scheduled
- `JURISDIGTA_INSTALL_DOCUMENT_PROCESSOR_CRON=1` for self-managed prod
- `JURISDIGTA_DOCUMENT_PROCESSOR_CRON_EXPRESSION=*/15 * * * *` for self-managed prod
- `JURISDIGTA_DOCUMENT_PROCESSOR_LIMIT=20` for self-managed prod
- DB route/provider/profile rows for the self-managed prod local Ollama free route and Azure Foundry paid route
- `AZURE_LAWS_COLLECTOR_CONTAINER_APP_NAME`
- `AZURE_LAWS_COLLECTOR_MAX_PROBES`
- `AZURE_LAWS_STORAGE_CONTAINER_NAME=laws-collection-sk`
- `LAWS_COLLECTOR_MAX_RUNNING_TIME`
- `LAWS_COLLECTOR_IMPORT=zip`
- `LAWS_COLLECTOR_IMPORT_ZIP_MAX_THREADS=10`
- `LAWS_STORAGE_CLOUD` if you need a non-default blob container URL
- `AZURE_LAWS_POSTGRES_DATABASE_NAME_SK`
- `API_BASE_URL`
- `CORS_ALLOW_ORIGINS`
- `MCP_CORS_ALLOW_ORIGINS=https://mcp.jurisdigta.eu`
- `MCP_PORT=8070` for self-managed Docker Compose deployments
- `MCP_PUBLIC_BASE_URL=https://mcp.jurisdigta.eu` for self-managed MCP OAuth metadata and token audience binding
- `INTERNAL_MCP_BASE_URL=http://jurisdigta-mcp:8070` for API-to-MCP law-tool calls inside the Docker network; the self-managed deploy script injects this value automatically
- `MCP_OAUTH_ALLOWED_REDIRECT_HOSTS=chatgpt.com,chat.openai.com,claude.ai,vscode.dev,www.perplexity.ai,localhost,127.0.0.1,::1` for hosted remote connector OAuth callbacks including `https://vscode.dev/redirect`, `https://claude.ai/api/mcp/auth_callback`, and `https://www.perplexity.ai/rest/connections/oauth_callback`; loopback `http://localhost/...`, `http://127.0.0.1/...`, and `http://[::1]/...` redirects are accepted directly for local Claude/desktop OAuth proxies
- `MCP_OTP_REUSE_WINDOW_HOURS=24` for bounded repeat OTP suppression after successful MCP OTP verification
- `MCP_OAUTH_TEST_MFA_BYPASS_ENABLED=false` by default; when enabled for synthetic connector validation, also set `MCP_OAUTH_TEST_MFA_BYPASS_EMAILS` to the two approved test emails and `MCP_OAUTH_TEST_MFA_BYPASS_EXPIRES_AT=2030-01-01T00:00:00Z`
- `CONTACT_CAPTCHA_REQUIRED=true`
- `CONTACT_RATE_LIMIT_MAX_REQUESTS=5`
- `CONTACT_RATE_LIMIT_WINDOW_SECONDS=600`
- `TURNSTILE_SITE_KEY`
- secret `TURNSTILE_SECRET_KEY`
- `EMAIL_TRANSPORT=smtp`
- `EMAIL_SENDER=no-reply@jurisdigta.eu`
- `EMAIL_SMTP_HOST=mail.webhouse.sk`
- `EMAIL_SMTP_PORT=587`
- `EMAIL_SMTP_USE_TLS=true`
- `EMAIL_SMTP_USERNAME=no-reply@jurisdigta.eu`
- `AZURE_EMAIL_SCHEDULER_JOB_NAME=email-scheduler`
- `AZURE_EMAIL_SCHEDULER_CRON_EXPRESSION=*/5 * * * *`
- secret `EMAIL_SMTP_PASSWORD`
- `CAR_VALIDATION_API_BASE_URL` and secret `CAR_VALIDATION_API_KEY` when live vehicle checks should run in that environment

## 13. Run the Workflows Against the New Environment

Use manual workflow dispatch and set `github_environment` to `test` or `prod`.

The five ACR-backed application workflows expose the same safety controls:

| `create_image` | `deploy` | Result |
| --- | --- | --- |
| `false` | `false` | Run validation/tests only; do not authenticate to or upload to ACR |
| `true` | `false` | Build and upload the commit/image tag; do not mutate Container Apps or Jobs |
| `false` | `true` | Treat image creation as enabled, upload a new image, then deploy that image |
| `true` | `true` | Upload a new image, then deploy that image |

Both inputs default to `false`. This applies to `API Build and Deploy`,
`web_build_deploy`, `Laws Collector Build and Deploy`, `Email Scheduler Build and
Deploy`, and `Document Processor Build and Deploy`. Deployment always forces image
creation, so a deployment cannot silently reuse a stale tag. No new GitHub Environment
variables or secrets are required in `test` or `prod`.

Minimal build-only examples from an authenticated repository checkout:

```powershell
gh workflow run api_build_deploy.yml -f create_image=true -f deploy=false -f github_environment=test
gh workflow run web_build_deploy.yml -f create_image=true -f deploy=false -f github_environment=test
gh workflow run laws_collector_build_deploy.yml -f create_image=true -f deploy=false -f github_environment=test
gh workflow run email_build_deploy.yml -f create_image=true -f deploy=false -f github_environment=test
gh workflow run document_processor_build_deploy.yml -f create_image=true -f deploy=false -f github_environment=test
```

Run the offline workflow/build-only contract validation before pushing changes:

```powershell
.\scripts\validate_acr_workflow_controls.ps1
```

The validation replaces `az` and `python` with process-local test doubles and does not
authenticate to Azure, upload images, or mutate infrastructure.

For a deployment, set only `deploy=true` (and the target environment); the workflow
computes effective image creation as `create_image || deploy`:

```powershell
gh workflow run api_build_deploy.yml -f deploy=true -f github_environment=prod
```

Typical order:

1. `infra_deploy`
2. `Database Schema Upgrade` if needed
3. `API Build and Deploy` with `deploy=true`
4. `Document Processor Build and Deploy`
5. `Laws Collector Build and Deploy` with `deploy=true`
6. `Email Scheduler Build and Deploy` with `deploy=true`
7. `web_build_deploy`
8. `mobile_flutter_build`

For the self-managed production server path, use:

1. `Deployment/server/setup_jurisdigta_server.sh` once from the server console or SSH session.
2. `Self-Managed Prod Deploy` from GitHub Actions after `/srv/jurisdigta/secrets/jurisdigta.env` and Cloudflare Tunnel routing are ready.

Recommended deployed value:

- `DOCUMENT_PROCESSOR_OPTION=azure` for `dev`, `test`, and `prod`
- `SYSTEM_EMBEDDING_MODEL_OPTION=local` for `dev`, `test`, and `prod` unless you explicitly want Azure/OpenAI embeddings
- `SYSTEM_EMBEDDING_DEVICE=auto` for `dev`, `test`, and `prod` unless you need to force `cpu`
- Keep `DOCUMENT_PROCESSOR_OPTION=local` only in local workstation `.env` files when you want the API process to extract documents immediately without waiting for the ACA job
- When `Email Scheduler Build and Deploy` is used, set `EMAIL_SCHEDULER_ENABLED=false` on the API Container App so the API only queues emails and the ACA job delivers them on schedule

Observability note:

- The API observability endpoint reuses `AZURE_LOG_ANALYTICS_WORKSPACE_NAME` and `AZURE_MANAGED_IDENTITY_NAME` directly. Do not add separate `APPLICATIONINSIGHTS_*` runtime variables for that feature.

## 14. Current Workflow Defaults

Push and pull-request execution is validation-only for the five ACR-backed application workflows. It may build a local Docker image as a test artifact, but it does not authenticate to or upload to ACR. ACR image publication and Azure deployment require manual dispatch.

That means:

- `API Build and Deploy` runs tests and builds the Docker image on pull requests and pushes to `main`, but does not deploy by default.
- `API Build and Deploy` has manual boolean `create_image` and `deploy` inputs, both defaulting to `false`; `deploy=true` forces image creation before deployment.
- `API Build and Deploy` waits for Azure Container App provisioning to settle before applying secret and environment updates, which reduces transient `ContainerAppOperationInProgress` failures during deployment
- `API Build and Deploy` now fails during environment validation when `AZURE_OPENAI_API_KEY` is empty, because the deployed API always requires that secret for Azure OpenAI access
- `API Build and Deploy` injects `EMAIL_DB_OPTION=azure`, `EMAIL_DB_CLOUD=secretref:db-cloud`, and `EMAIL_DB_LOCAL=/tmp/email.sqlite3` automatically, so email outbox storage follows the API PostgreSQL deployment.
- `API Build and Deploy` injects SMTP settings and vehicle validation settings into the API Container App; `EMAIL_SMTP_PASSWORD` and `CAR_VALIDATION_API_KEY` are stored as Container App secrets.
- `API Build and Deploy` fails during environment validation when `EMAIL_TRANSPORT=smtp` and `EMAIL_SMTP_PASSWORD` is empty.
- `Laws Collector Build and Deploy` runs tests and builds the laws collector image on pull requests and pushes to `main`, but does not deploy by default.
- `Laws Collector Build and Deploy` has manual boolean `create_image` and `deploy` inputs, both defaulting to `false`; build-only mode does not open a PostgreSQL firewall rule or apply migrations.
- `Email Scheduler Build and Deploy` runs tests and builds the scheduler API image on pull requests and pushes to `main`, but does not deploy by default.
- `Email Scheduler Build and Deploy` has manual boolean `create_image` and `deploy` inputs, both defaulting to `false`; build-only mode does not open a PostgreSQL firewall rule or apply migrations.
- `Document Processor Build and Deploy` no longer publishes or deploys on push; its manual boolean `create_image` and `deploy` inputs both default to `false`.
- `web_build_deploy` uses the same two boolean inputs with safe `false` defaults and preserves its full lint/unit/E2E/build gate before image publication.
- `test` and `prod` remain manual `workflow_dispatch` targets unless a workflow is explicitly changed to auto-deploy them
- `Self-Managed Prod Deploy` is manual-only and always uses the protected `prod` GitHub Environment
- `Self-Managed Prod Deploy` configures Python 3.13 and installs the pinned `PyMuPDF==1.28.2`, `pypdf==6.16.1`, and `reportlab==5.0.0` packages before its Playwright gate; this keeps generated-PDF evidence validation aligned with `web_build_deploy`
- `Self-Managed Prod Deploy` runs the issue #646 Azure Foundry `gpt-5-mini` MCP law check after the server deploy, uploads seven-day evidence, and fails the workflow when that real-model route fails. Qwen is excluded from this automatic gate. There is no equivalent automatic test-environment step because this workflow targets only the protected self-managed `prod` Environment.
- `Self-Managed Prod Deploy` builds `jurisdigta-document-processor:local`, starts API with `DOCUMENT_PROCESSOR_OPTION=azure`, and installs `/srv/jurisdigta/ops/run_document_processor.sh` when `JURISDIGTA_INSTALL_DOCUMENT_PROCESSOR_CRON=1`

## 15. Quick Validation Checklist

After setup, verify:

- GitHub Environment `test` exists
- GitHub Environment `prod` exists
- OIDC federated credential exists for `test`
- OIDC federated credential exists for `prod`
- `API_BASE_URL` is set in both environments
- required Azure variables are set in both environments
- required secrets are set in both environments
- `EMAIL_SMTP_PASSWORD` is set when `EMAIL_TRANSPORT=smtp`
- `TURNSTILE_SITE_KEY` is set on the corporate web GitHub Environment and `TURNSTILE_SECRET_KEY` is set on the API GitHub Environment when `CONTACT_CAPTCHA_REQUIRED=true`
- `AZURE_EMAIL_SCHEDULER_JOB_NAME` and `AZURE_EMAIL_SCHEDULER_CRON_EXPRESSION` are set when the dedicated email ACA job should run
- self-managed prod document processor settings are set or accepted at defaults: `JURISDIGTA_INSTALL_DOCUMENT_PROCESSOR_CRON`, `JURISDIGTA_DOCUMENT_PROCESSOR_CRON_EXPRESSION`, and `JURISDIGTA_DOCUMENT_PROCESSOR_LIMIT`
- self-managed prod Ollama is installed as a separate localhost-only service and `curl -fsS http://127.0.0.1:11434/api/tags` succeeds
- optional `CAR_VALIDATION_API_BASE_URL` and `CAR_VALIDATION_API_KEY` are set together when live vehicle validation should be enabled
- the focused generated-PDF E2E example succeeds locally with `npm run test:e2e -- e2e/issue-623-purchase-law-citations.spec.ts` after installing the pinned PDF dependencies
- `workflow_dispatch` works with `github_environment=test`
- `workflow_dispatch` works with `github_environment=prod`
- `Self-Managed Prod Deploy` works against `prod` and the server-local health checks for API, MCP, web, email scheduler, and document processor pass
- `Self-Managed Prod Deploy` leaves the synthetic MCP OAuth MFA bypass disabled after its required post-deployment E2E, including when the E2E fails
