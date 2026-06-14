# Azure PostgreSQL Migration Runbook

This runbook covers backing up the existing local PostgreSQL database, restoring it into Azure Database for PostgreSQL Flexible Server, and deploying the laws collector Azure Container Apps Job so it resumes from completed archive/monthly ZIP state, checks laws sequentially one by one, and stops when there is no new law.

## Scope

- Source database: local PostgreSQL, usually `laws_sk` on `127.0.0.1:5433`.
- Target database: Azure PostgreSQL Flexible Server database, usually `laws_sk`.
- Workload: Slovak laws collector (`LAWS_COUNTRY=SK`).
- Storage: ZIP source bundles should remain in Azure Blob through `LAWS_STORAGE_CLOUD`.

Do not move local PostgreSQL runtime files into `databases/`. Local database files stay under `runs/storage/laws-collector/postgres/data`; SQL schema assets stay under `databases/laws-collector/`.

## Compliance Baseline

The laws corpus is public legal data, but the database may include operational metadata, errors, traces, embeddings, and access credentials in connection strings. Apply these controls before migration:

- Do not put passwords, dump files, or connection strings into git.
- Store the dump under `runs/storage/laws-collector/backups/` or another ignored operator-controlled path.
- Encrypt or access-control the backup if it leaves the local machine.
- Grant Azure access only to the deployment service principal and managed identities that need it.
- Keep `collector_progress`, `collector_import_state`, and `archive_import_assets` so collector behavior is traceable and replay-safe.
- Validate the restored database before enabling scheduled jobs to avoid duplicate or uncontrolled collection.
- For GDPR and EU AI Act alignment, log operational status only; do not add personal data or legal-risk user outputs to collector logs.

## Required Tools

- Azure CLI with `containerapp`, `postgres flexible-server`, and `acr` support.
- `pg_dump`, `pg_restore`, and `psql` matching the local PostgreSQL major version where possible.
- Docker Desktop if starting the local database through repository scripts.
- Repository `.env` populated with Azure service principal and target Azure resource names.

Authenticate with the repository service principal, not the currently signed-in Azure user:

```powershell
.\infra\scripts\login_service_principal.ps1 -EnvFilePath .env
```

Confirm the target subscription after login:

```powershell
az account show --query "{name:name, id:id, tenantId:tenantId}" --output table
```

## Variables

Set operator variables in the current PowerShell session. Replace placeholders with test or production values.

```powershell
$ResourceGroupName = $env:AZURE_RESOURCE_GROUP
$Location = $env:AZURE_LOCATION
$PostgresServerName = $env:AZURE_POSTGRES_SERVER_NAME
$PostgresDatabaseName = $env:AZURE_LAWS_POSTGRES_DATABASE_NAME_SK
$PostgresAdminUsername = $env:AZURE_POSTGRES_ADMIN_USERNAME
$PostgresAdminPassword = $env:AZURE_POSTGRES_ADMIN_PASSWORD

$LocalHost = "127.0.0.1"
$LocalPort = "5433"
$LocalDatabaseName = "laws_sk"
$LocalUsername = "postgres"
$LocalPassword = "postgres"

$BackupDir = "runs/storage/laws-collector/backups"
$BackupFile = "$BackupDir/laws_sk_$(Get-Date -Format yyyyMMdd_HHmmss).dump"
```

Create the local backup folder:

```powershell
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
```

## Pre-Migration Checks

Start or reuse local PostgreSQL if needed:

```powershell
.\skills\start-postgres\scripts\start_postgres.ps1 -ProjectName laws-collector -SkipSchemaUpdate
```

Check source database state:

```powershell
$env:PGPASSWORD = $LocalPassword
psql -h $LocalHost -p $LocalPort -U $LocalUsername -d $LocalDatabaseName -c "SELECT count(*) AS laws FROM law_documents;"
psql -h $LocalHost -p $LocalPort -U $LocalUsername -d $LocalDatabaseName -c "SELECT country_code, status, import_key, completed_at FROM collector_import_state ORDER BY updated_at DESC LIMIT 20;"
psql -h $LocalHost -p $LocalPort -U $LocalUsername -d $LocalDatabaseName -c "SELECT country_code, last_processed_law_year, last_processed_law_number, next_probe_law_year, next_probe_law_number FROM collector_progress;"
```

Expected maintenance-ready source state:

- `collector_import_state` has completed archive state for `slov-lex:zip:archive-seed`.
- Latest monthly ZIP state is completed or no newer monthly import is pending.
- `collector_progress` has the latest imported law and next law cursor.

## Backup Local PostgreSQL

Create a custom-format dump:

```powershell
$env:PGPASSWORD = $LocalPassword
pg_dump `
  --host $LocalHost `
  --port $LocalPort `
  --username $LocalUsername `
  --format custom `
  --blobs `
  --verbose `
  --file $BackupFile `
  $LocalDatabaseName
```

Verify that the dump can be listed:

```powershell
pg_restore --list $BackupFile | Select-Object -First 20
```

Optional plain SQL metadata check:

```powershell
Get-Item $BackupFile | Select-Object FullName, Length, LastWriteTime
```

## Prepare Azure PostgreSQL

Create the Azure PostgreSQL Flexible Server if it does not already exist. Use the SKU, storage, networking, and backup retention approved for the environment.

```powershell
az postgres flexible-server create `
  --resource-group $ResourceGroupName `
  --location $Location `
  --name $PostgresServerName `
  --admin-user $PostgresAdminUsername `
  --admin-password $PostgresAdminPassword `
  --version 16 `
  --sku-name Standard_B2s `
  --tier Burstable `
  --storage-size 128 `
  --public-access None `
  --yes
```

For a locked-down production network, replace broad public access with approved private networking or explicit firewall rules. For a temporary operator restore from your current public IP:

```powershell
$MyIp = (Invoke-RestMethod -Uri "https://api.ipify.org").Trim()
az postgres flexible-server firewall-rule create `
  --resource-group $ResourceGroupName `
  --name $PostgresServerName `
  --rule-name "temporary-operator-restore" `
  --start-ip-address $MyIp `
  --end-ip-address $MyIp
```

Create or recreate the target database. Use the destructive drop only when you intentionally replace the target.

```powershell
az postgres flexible-server db create `
  --resource-group $ResourceGroupName `
  --server-name $PostgresServerName `
  --database-name $PostgresDatabaseName
```

Enable required extensions:

```powershell
$env:PGPASSWORD = $PostgresAdminPassword
psql `
  "host=$PostgresServerName.postgres.database.azure.com port=5432 dbname=$PostgresDatabaseName user=$PostgresAdminUsername password=$PostgresAdminPassword sslmode=require" `
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

If `vector` is unavailable, stop and enable pgvector support on the Azure server before restoring laws embeddings.

## Restore Into Azure PostgreSQL

Restore into a newly created or intentionally replaceable target database:

```powershell
$env:PGPASSWORD = $PostgresAdminPassword
pg_restore `
  --host "$PostgresServerName.postgres.database.azure.com" `
  --port 5432 `
  --username $PostgresAdminUsername `
  --dbname $PostgresDatabaseName `
  --clean `
  --if-exists `
  --no-owner `
  --no-privileges `
  --verbose `
  $BackupFile
```

Apply current repository migrations after restore:

```powershell
$env:LAWS_DB_BACKEND = "postgres"
$env:LAWS_DB_CLOUD = "postgresql://${PostgresAdminUsername}:${PostgresAdminPassword}@${PostgresServerName}.postgres.database.azure.com:5432/${PostgresDatabaseName}?sslmode=require"
python scripts/databases/apply_laws_db_schema.py
```

Validate restored state:

```powershell
psql `
  "host=$PostgresServerName.postgres.database.azure.com port=5432 dbname=$PostgresDatabaseName user=$PostgresAdminUsername password=$PostgresAdminPassword sslmode=require" `
  -c "SELECT count(*) AS laws FROM law_documents;"

psql `
  "host=$PostgresServerName.postgres.database.azure.com port=5432 dbname=$PostgresDatabaseName user=$PostgresAdminUsername password=$PostgresAdminPassword sslmode=require" `
  -c "SELECT country_code, status, import_key, completed_at FROM collector_import_state ORDER BY updated_at DESC LIMIT 20;"

psql `
  "host=$PostgresServerName.postgres.database.azure.com port=5432 dbname=$PostgresDatabaseName user=$PostgresAdminUsername password=$PostgresAdminPassword sslmode=require" `
  -c "SELECT country_code, last_processed_law_year, last_processed_law_number, next_probe_law_year, next_probe_law_number FROM collector_progress;"
```

## Laws Collector Azure Job Parameters

For the requested behavior, deploy the laws collector as an Azure Container Apps Job with this maintenance profile:

| Setting | Value | Reason |
| --- | --- | --- |
| `LAWS_COUNTRY` | `SK` | Uses Slovak collector implementation. |
| `LAWS_DB_BACKEND` | `postgres` | Uses restored Azure PostgreSQL state. |
| `LAWS_DB_CLOUD` | secret connection string | Keeps database credentials out of plain env output. |
| `LAWS_COLLECTOR_IMPORT` | `zip` | Checks archive/monthly ZIP state first, then sequential live cursor. |
| `LAWS_WORKER_FIXTURE` | `live` | Runs real Slov-Lex collection path. |
| `LAWS_WORKER_MAX_CYCLES` | `1` | A scheduled run exits after one collector cycle. |
| `AZURE_LAWS_COLLECTOR_MAX_PROBES` / `LAWS_WORKER_MAX_PROBES` | `1` | Probes one sequential law per run. |
| `LAWS_COLLECTOR_MAX_RUNNING_TIME` | `60` | Caps a stuck run; use `0` only for explicit bootstrap/repair. |
| `LAWS_STORAGE_CLOUD` | `https://<storage-account>.blob.core.windows.net/laws-collection-sk` | Stores ZIP source bundles durably in Azure Blob. |
| `LAWS_COLLECTOR_IMPORT_ZIP_MAX_THREADS` | `2` or `4` | Only used if a ZIP import is still pending; keep low for small plans. |
| Cron | e.g. `0 * * * *` | Hourly maintenance; choose environment-approved cadence. |
| Parallelism/completions | `1` / `1` | Prevents concurrent cursor updates. |
| Retry limit | `1` | Avoids repeated writes during transient external failures. |

With the restored archive/monthly state in PostgreSQL, `LAWS_COLLECTOR_IMPORT=zip` does not replay completed archive work. The worker should log that archive or ZIP import is skipped because the live sequential cursor is active, then check `next_probe_law_*`. When no new law exists, the expected terminal log is:

```text
No new laws for SK, last processed law ... at ...
```

## Deploy Laws Collector Job

Preferred deployment path:

```powershell
.\infra\scripts\login_service_principal.ps1 -EnvFilePath .env

.\infra\scripts\deploy_laws_collector.ps1 `
  -ContainerAppName "laws-collector" `
  -LawsCollectorImport "zip" `
  -WorkerMaxProbes "1" `
  -LawsCollectorMaxRunningTime "60" `
  -CronExpression "0 * * * *" `
  -ImageTag "latest"
```

Equivalent direct Bicep deployment:

```powershell
$DbCloud = "postgresql://${PostgresAdminUsername}:${PostgresAdminPassword}@${PostgresServerName}.postgres.database.azure.com:5432/${PostgresDatabaseName}?sslmode=require"

az deployment group create `
  --resource-group $ResourceGroupName `
  --template-file "infra/bicep/laws_collector.job.bicep" `
  --parameters `
    location=$Location `
    managedEnvironmentName=$env:AZURE_CONTAINERAPPS_ENVIRONMENT `
    jobName="laws-collector" `
    acrName=$env:AZURE_CONTAINER_REGISTRY `
    managedIdentityName=$env:AZURE_MANAGED_IDENTITY_NAME `
    image="$($env:AZURE_CONTAINER_REGISTRY).azurecr.io/laws-collector:latest" `
    storageAccountName=$env:AZURE_STORAGE_ACCOUNT_NAME `
    storageContainerName=$env:AZURE_LAWS_STORAGE_CONTAINER_NAME `
    postgresServerName=$PostgresServerName `
    postgresDatabaseName=$PostgresDatabaseName `
    postgresAdminUsername=$PostgresAdminUsername `
    postgresAdminPassword=$PostgresAdminPassword `
    postgresConnectionString=$DbCloud `
    lawsCollectorImport="zip" `
    workerMaxProbes=1 `
    lawsCollectorMaxRunningTime=60 `
    cronExpression="0 * * * *" `
    parallelism=1 `
    completions=1 `
    replicaRetryLimit=1
```

## Start And Validate A Single Azure Run

Start one manual execution after deployment:

```powershell
az containerapp job start `
  --resource-group $ResourceGroupName `
  --name "laws-collector"
```

List executions:

```powershell
az containerapp job execution list `
  --resource-group $ResourceGroupName `
  --name "laws-collector" `
  --output table
```

Inspect logs:

```powershell
az containerapp job logs show `
  --resource-group $ResourceGroupName `
  --name "laws-collector" `
  --follow
```

Database validation after the run:

```powershell
psql `
  "host=$PostgresServerName.postgres.database.azure.com port=5432 dbname=$PostgresDatabaseName user=$PostgresAdminUsername password=$PostgresAdminPassword sslmode=require" `
  -c "SELECT country_code, last_processed_law_year, last_processed_law_number, next_probe_law_year, next_probe_law_number, updated_at FROM collector_progress;"
```

Expected outcomes:

- If one new law exists, one law is imported and the cursor advances.
- If no new law exists, the job exits normally after logging `No new laws for SK`.
- Completed archive/monthly ZIP imports are not replayed.
- No concurrent executions update the same cursor.

## Rollback

Stop scheduled execution while investigating by deleting the scheduled job. Recreate it from the Bicep deployment after rollback validation:

```powershell
az containerapp job delete `
  --resource-group $ResourceGroupName `
  --name "laws-collector" `
  --yes
```

Restore the pre-migration Azure database backup if one exists, or restore the local dump into a replacement Azure database:

```powershell
az postgres flexible-server db create `
  --resource-group $ResourceGroupName `
  --server-name $PostgresServerName `
  --database-name "${PostgresDatabaseName}_rollback"

pg_restore `
  --host "$PostgresServerName.postgres.database.azure.com" `
  --port 5432 `
  --username $PostgresAdminUsername `
  --dbname "${PostgresDatabaseName}_rollback" `
  --no-owner `
  --no-privileges `
  --verbose `
  $BackupFile
```

Remove temporary operator firewall access after restore:

```powershell
az postgres flexible-server firewall-rule delete `
  --resource-group $ResourceGroupName `
  --name $PostgresServerName `
  --rule-name "temporary-operator-restore" `
  --yes
```

Keep the local dump until the Azure job has completed at least one successful scheduled run and the database has been validated.

## References

- Azure CLI reference for PostgreSQL Flexible Server: https://learn.microsoft.com/en-us/cli/azure/postgres/flexible-server
- Azure PostgreSQL public access networking: https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-public
- Azure Container Apps Jobs CLI reference: https://learn.microsoft.com/en-us/cli/azure/containerapp/job
- Azure Container Apps job logs CLI reference: https://learn.microsoft.com/en-us/cli/azure/containerapp/job/logs
