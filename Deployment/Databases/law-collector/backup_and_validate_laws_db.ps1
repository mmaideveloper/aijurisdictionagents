[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ConnectionString = $env:LAWS_DB_CLOUD,

    [Parameter(Mandatory = $false)]
    [string]$BackupRoot = "runs/storage/laws-collector/postgres/backups",

    [Parameter(Mandatory = $false)]
    [int]$StartYear = 1995,

    [Parameter(Mandatory = $false)]
    [int]$EndYear = (Get-Date).Year,

    [Parameter(Mandatory = $false)]
    [string]$CountryCode = "SK"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ConnectionString)) {
    throw "Connection string is empty. Pass -ConnectionString or set LAWS_DB_CLOUD."
}

$null = New-Item -ItemType Directory -Path $BackupRoot -Force
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFile = Join-Path $BackupRoot ("laws-collector-{0}.dump" -f $timestamp)
$reportFile = Join-Path $BackupRoot ("laws-validation-{0}.json" -f $timestamp)

Write-Host "Creating PostgreSQL backup: $backupFile"
pg_dump --format=custom --file "$backupFile" "$ConnectionString"

Write-Host "Running validation checks (country=$CountryCode, years=$StartYear..$EndYear)"
$validationSql = @"
WITH years AS (
  SELECT generate_series($StartYear, $EndYear) AS law_year
),
coverage AS (
  SELECT y.law_year,
         EXISTS (
            SELECT 1
            FROM law_documents d
            WHERE d.country_code = '$CountryCode'
              AND d.law_year = y.law_year
         ) AS has_law
  FROM years y
),
version_checks AS (
  SELECT
      COUNT(*) FILTER (WHERE vector_dims(v.embedding_vector) > 0) AS versions_with_embeddings,
      COUNT(*) AS total_versions,
      COUNT(m.version_id) AS versions_with_metadata
  FROM law_versions v
  LEFT JOIN law_metadata m ON m.version_id = v.version_id
  JOIN law_documents d ON d.document_id = v.document_id
  WHERE d.country_code = '$CountryCode'
    AND d.law_year BETWEEN $StartYear AND $EndYear
)
SELECT json_build_object(
  'country_code', '$CountryCode',
  'start_year', $StartYear,
  'end_year', $EndYear,
  'missing_years', COALESCE((SELECT json_agg(law_year) FROM coverage WHERE has_law = false), '[]'::json),
  'versions_with_embeddings', (SELECT versions_with_embeddings FROM version_checks),
  'versions_with_metadata', (SELECT versions_with_metadata FROM version_checks),
  'total_versions', (SELECT total_versions FROM version_checks)
) AS report;
"@

$reportJson = psql "$ConnectionString" -X -A -t -v ON_ERROR_STOP=1 -c "$validationSql"
$reportJson | Set-Content -Encoding UTF8 $reportFile

$report = $reportJson | ConvertFrom-Json
$missingYearsCount = @($report.missing_years).Count
$embeddingComplete = [int]$report.versions_with_embeddings -eq [int]$report.total_versions
$metadataComplete = [int]$report.versions_with_metadata -eq [int]$report.total_versions

if ($missingYearsCount -gt 0) {
    throw "Validation failed: missing laws for years: $($report.missing_years -join ', '). Report: $reportFile"
}
if (-not $embeddingComplete) {
    throw "Validation failed: embeddings incomplete ($($report.versions_with_embeddings)/$($report.total_versions)). Report: $reportFile"
}
if (-not $metadataComplete) {
    throw "Validation failed: metadata incomplete ($($report.versions_with_metadata)/$($report.total_versions)). Report: $reportFile"
}

Write-Host "Validation passed."
Write-Host "Backup: $backupFile"
Write-Host "Validation report: $reportFile"
