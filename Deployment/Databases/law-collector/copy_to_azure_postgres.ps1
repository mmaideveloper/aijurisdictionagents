[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceConnectionString,

    [Parameter(Mandatory = $true)]
    [string]$TargetConnectionString,

    [Parameter(Mandatory = $false)]
    [string]$TempRoot = "runs/storage/laws-collector/postgres/transfers"
)

$ErrorActionPreference = "Stop"
$null = New-Item -ItemType Directory -Path $TempRoot -Force

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpFile = Join-Path $TempRoot ("laws-collector-transfer-{0}.dump" -f $timestamp)

Write-Host "Exporting source database to $dumpFile"
pg_dump --format=custom --file "$dumpFile" "$SourceConnectionString"

Write-Host "Restoring dump to target PostgreSQL"
pg_restore --clean --if-exists --no-owner --no-privileges --dbname "$TargetConnectionString" "$dumpFile"

Write-Host "Running post-restore sanity checks"
$sanitySql = @"
SELECT
  (SELECT COUNT(*) FROM law_documents) AS law_documents_count,
  (SELECT COUNT(*) FROM law_versions) AS law_versions_count,
  (SELECT COUNT(*) FROM law_metadata) AS law_metadata_count;
"@
psql "$TargetConnectionString" -X -v ON_ERROR_STOP=1 -c "$sanitySql"

Write-Host "Deployment to target PostgreSQL completed successfully."
Write-Host "Transfer dump: $dumpFile"
