param(
    [string]$SshTarget = "jurisdigta-server",
    [string]$ServerApiContainer = "jurisdigta-api",
    [string]$EnvFilePath = ".env",
    [string]$DatabaseUrl = "",
    [string]$LocalPostgresContainer = "aijurisdiction-postgres-local",
    [switch]$VerifyModel
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resolvedEnvPath = if ([IO.Path]::IsPathRooted($EnvFilePath)) {
    $EnvFilePath
} else {
    Join-Path $repoRoot $EnvFilePath
}

function Set-DotEnvValue {
    param([string]$Path, [string]$Name, [string]$Value)

    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $Path) {
        $lines.AddRange([string[]][IO.File]::ReadAllLines($Path))
    }
    $replacement = "$Name=$Value"
    $replaced = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^\s*$([regex]::Escape($Name))=") {
            $lines[$index] = $replacement
            $replaced = $true
            break
        }
    }
    if (-not $replaced) {
        $lines.Add($replacement)
    }
    [IO.File]::WriteAllLines($Path, $lines, [Text.UTF8Encoding]::new($false))
}

function Get-DotEnvValue {
    param([string]$Path, [string]$Name)

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -match "^\s*$([regex]::Escape($Name))=(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function New-LocalEncryptionKey {
    $bytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    } finally {
        $generator.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "OpenSSH client is required."
}
if (-not (Test-Path (Join-Path $repoRoot "conda\python.exe"))) {
    throw "Task conda Python was not found at .\conda\python.exe."
}
if (-not (Test-Path -LiteralPath $resolvedEnvPath)) {
    throw "Ignored local env file was not found: $resolvedEnvPath"
}

Push-Location $repoRoot
try {
    & git check-ignore --quiet -- $resolvedEnvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Refusing to write credentials because the env file is not Git-ignored."
    }
} finally {
    Pop-Location
}

& (Join-Path $repoRoot "skills\start-postgres\scripts\start_postgres.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Local PostgreSQL startup or base migration failed."
}

if (-not $DatabaseUrl) {
    Push-Location $repoRoot
    try {
        $branchName = ([string](& git branch --show-current)).Trim()
    } finally {
        Pop-Location
    }
    $branchSlug = (($branchName -replace "^codex/", "") -replace "[^A-Za-z0-9]+", "_").Trim("_").ToLowerInvariant()
    if (-not $branchSlug) {
        $branchSlug = "worktree"
    }
    if ($branchSlug.Length -gt 48) {
        $branchSlug = $branchSlug.Substring(0, 48)
    }
    $databaseName = "aij_e2e_$branchSlug"
    $DatabaseUrl = "postgresql://postgres:postgres@127.0.0.1:5432/$databaseName"
}

$parsedDatabaseUrl = [Uri]$DatabaseUrl
if ($parsedDatabaseUrl.Scheme -notin @("postgres", "postgresql") -or
    $parsedDatabaseUrl.Host -notin @("127.0.0.1", "localhost", "::1")) {
    throw "The E2E destination must be a loopback PostgreSQL URL."
}
$databaseName = $parsedDatabaseUrl.AbsolutePath.Trim("/")
if ($databaseName -notmatch "^[a-z_][a-z0-9_]{0,62}$") {
    throw "The branch-local E2E database name is invalid."
}
$databaseExists = & docker exec $LocalPostgresContainer `
    psql -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$databaseName'"
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the local PostgreSQL databases."
}
$databaseExistsText = (@($databaseExists) -join "").Trim()
if ($databaseExistsText -ne "1") {
    & docker exec $LocalPostgresContainer createdb -U postgres $databaseName
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create branch-local PostgreSQL database '$databaseName'."
    }
}

$serverScript = @'
import json
from aijurisdictionagents.api_db import ApiDatabaseStore

store = ApiDatabaseStore.from_env()
providers = [item for item in store.list_ai_model_providers() if item.provider_id == "azure_foundry"]
profiles = [item for item in store.list_ai_model_profiles(provider_id="azure_foundry") if item.model_profile_id == "azure_foundry_gpt_4o_mini"]
credentials = [item for item in store.list_ai_model_credentials(provider_id="azure_foundry", reveal=True) if item.enabled and item.secret_type == "api_key"]
if len(providers) != 1 or len(profiles) != 1 or len(credentials) != 1:
    raise RuntimeError("Expected one enabled Azure Foundry provider, gpt-4o-mini profile, and API-key credential.")
provider = providers[0]
profile = profiles[0]
credential = credentials[0]
if profile.model_code != "gpt-4o-mini" or profile.deployment_name != "gpt-4o-mini":
    raise RuntimeError("The approved server profile is not gpt-4o-mini.")
if not credential.secret_value:
    raise RuntimeError("The approved server credential could not be revealed.")
print(json.dumps({
    "endpoint": provider.base_url,
    "api_version": provider.api_version,
    "deployment": profile.deployment_name,
    "secret_value": credential.secret_value,
}))
'@

$payloadJson = $null
$payload = $null
try {
    $payloadJson = $serverScript | & ssh -o BatchMode=yes $SshTarget "docker exec -i $ServerApiContainer python -"
    if ($LASTEXITCODE -ne 0 -or -not $payloadJson) {
        throw "The approved server credential could not be imported."
    }
    $payload = $payloadJson | ConvertFrom-Json
    if (-not $payload.endpoint -or -not $payload.api_version -or
        $payload.deployment -ne "gpt-4o-mini" -or -not $payload.secret_value) {
        throw "The server returned incomplete or unexpected model configuration."
    }

    Set-DotEnvValue -Path $resolvedEnvPath -Name "E2E_AZURE_FOUNDRY_ENDPOINT" -Value ([string]$payload.endpoint)
    Set-DotEnvValue -Path $resolvedEnvPath -Name "E2E_AZURE_FOUNDRY_API_VERSION" -Value ([string]$payload.api_version)
    Set-DotEnvValue -Path $resolvedEnvPath -Name "E2E_AZURE_FOUNDRY_DEPLOYMENT" -Value "gpt-4o-mini"
    Set-DotEnvValue -Path $resolvedEnvPath -Name "E2E_AZURE_FOUNDRY_API_KEY" -Value ([string]$payload.secret_value)
    Set-DotEnvValue -Path $resolvedEnvPath -Name "E2E_AZURE_FOUNDRY_AD_TOKEN" -Value "unknown-variable"
    $localEncryptionKey = Get-DotEnvValue -Path $resolvedEnvPath -Name "AI_MODEL_CREDENTIAL_ENCRYPTION_KEY"
    if (-not $localEncryptionKey -or $localEncryptionKey -eq "unknown-variable" -or $localEncryptionKey.Length -lt 24) {
        $localEncryptionKey = New-LocalEncryptionKey
        Set-DotEnvValue -Path $resolvedEnvPath -Name "AI_MODEL_CREDENTIAL_ENCRYPTION_KEY" -Value $localEncryptionKey
    }

    $previousDbOption = $env:DB_OPTION
    $previousDbCloud = $env:DB_CLOUD
    $previousLlmProvider = $env:LLM_PROVIDER
    try {
        $env:DB_OPTION = "postgres"
        $env:DB_CLOUD = $DatabaseUrl
        Remove-Item Env:LLM_PROVIDER -ErrorAction SilentlyContinue
        & (Join-Path $repoRoot "conda\python.exe") `
            (Join-Path $repoRoot "scripts\databases\apply_api_db_schema.py")
        if ($LASTEXITCODE -ne 0) {
            throw "Branch-local PostgreSQL schema migration failed."
        }
        $arguments = @(
            (Join-Path $repoRoot "scripts\bootstrap_e2e_model_credentials.py"),
            "--env-file",
            $resolvedEnvPath
        )
        if ($VerifyModel) {
            $arguments += "--verify-model"
        }
        & (Join-Path $repoRoot "conda\python.exe") @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Local E2E model credential bootstrap failed."
        }
    } finally {
        if ($null -eq $previousDbOption) { Remove-Item Env:DB_OPTION -ErrorAction SilentlyContinue } else { $env:DB_OPTION = $previousDbOption }
        if ($null -eq $previousDbCloud) { Remove-Item Env:DB_CLOUD -ErrorAction SilentlyContinue } else { $env:DB_CLOUD = $previousDbCloud }
        if ($null -eq $previousLlmProvider) { Remove-Item Env:LLM_PROVIDER -ErrorAction SilentlyContinue } else { $env:LLM_PROVIDER = $previousLlmProvider }
    }
    Write-Output "Imported approved Azure Foundry gpt-4o-mini credential into branch-local PostgreSQL."
    Write-Output "Database: $databaseName"
    Write-Output "Secret values were not displayed."
} finally {
    $payloadJson = $null
    if ($null -ne $payload) {
        $payload.secret_value = ""
    }
    $payload = $null
    $localEncryptionKey = $null
    Remove-Variable serverScript -ErrorAction SilentlyContinue
}
