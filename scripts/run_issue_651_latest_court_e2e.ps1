param(
    [string]$Endpoint = "",
    [string]$Model = "gpt-5-mini",
    [string]$EnvFilePath = ".env",
    [string]$SshTarget = "jurisdigta-server",
    [string]$ServerApiContainer = "jurisdigta-api",
    [int]$ApiPort = 8082,
    [int]$McpPort = 8072,
    [int]$FrontendPort = 5191,
    [string]$FinalScreenshotPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$containerName = "aijurisdiction-postgres-local"

function Import-SelectedDotEnvValues {
    param([string]$Path, [string[]]$Names)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) { continue }
        $parts = $trimmed.Split("=", 2)
        $name = $parts[0].Trim()
        if ($name -notin $Names -or [Environment]::GetEnvironmentVariable($name, "Process")) { continue }
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Wait-ForUrl {
    param([string]$Url, [int]$TimeoutSeconds = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "Service did not become healthy at $Url."
}

function Assert-PortFree {
    param([int]$Port)
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 | Out-Null
        throw "Port $Port already hosts a healthy service; use an isolated port."
    } catch {
        if ($_.Exception.Message -like "Port $Port already hosts*") { throw }
    }
}

function Assert-SyntheticDatabaseName {
    param([string]$Name)
    if ($Name -notmatch '^issue651_(api|court)_[0-9]{14}$') {
        throw "Refusing database operation for non-synthetic name."
    }
}

function New-EphemeralSecret {
    param([int]$ByteCount)
    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    } finally {
        $generator.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Import-ApprovedServerModelCredential {
    param(
        [string]$Target,
        [string]$Container,
        [string]$RequiredModel
    )
    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        throw "OpenSSH is required to import the approved real-model E2E credential."
    }
    $serverScript = @'
import json
import os
from aijurisdictionagents.api_db import ApiDatabaseStore

required_model = os.environ["ISSUE_651_REQUIRED_MODEL"]
store = ApiDatabaseStore.from_env()
profiles = [
    item for item in store.list_ai_model_profiles()
    if item.enabled
    and item.model_code == required_model
    and item.deployment_name == required_model
]
if len(profiles) != 1:
    raise RuntimeError("Expected exactly one enabled profile for the required model.")
profile = profiles[0]
providers = [
    item for item in store.list_ai_model_providers()
    if item.enabled and item.provider_id == profile.provider_id
]
credentials = [
    item for item in store.list_ai_model_credentials(
        provider_id=profile.provider_id,
        reveal=True,
    )
    if item.enabled and item.secret_type in {"api_key", "azure_ad_token"}
]
if len(providers) != 1 or len(credentials) != 1:
    raise RuntimeError("Expected one enabled provider and credential for the required model.")
provider = providers[0]
credential = credentials[0]
if not provider.base_url or not credential.secret_value:
    raise RuntimeError("The approved server model configuration is incomplete.")
print(json.dumps({
    "endpoint": provider.base_url,
    "api_version": provider.api_version or "",
    "deployment": profile.deployment_name,
    "secret_type": credential.secret_type,
    "secret_value": credential.secret_value,
}))
'@
    $payloadJson = $null
    $payload = $null
    try {
        $remoteCommand = "docker exec -e ISSUE_651_REQUIRED_MODEL=$RequiredModel -i $Container python -"
        $payloadJson = $serverScript | & ssh -o BatchMode=yes $Target $remoteCommand
        if ($LASTEXITCODE -ne 0 -or -not $payloadJson) {
            throw "The approved $RequiredModel credential could not be imported from the server."
        }
        $payload = $payloadJson | ConvertFrom-Json
        if (-not $payload.endpoint -or $payload.deployment -ne $RequiredModel -or
            $payload.secret_type -notin @("api_key", "azure_ad_token") -or
            -not $payload.secret_value) {
            throw "The server returned incomplete or unexpected model configuration."
        }
        $script:Endpoint = ([string]$payload.endpoint).TrimEnd([char[]]",/")
        if ($payload.secret_type -eq "api_key") {
            $env:AZURE_OPENAI_API_KEY = [string]$payload.secret_value
        } else {
            $env:AZURE_OPENAI_AD_TOKEN = [string]$payload.secret_value
        }
        $env:AZURE_OPENAI_API_VERSION = [string]$payload.api_version
        Write-Output "Imported approved Azure Foundry $RequiredModel credential; secret value was not displayed."
    } finally {
        $payloadJson = $null
        if ($null -ne $payload) { $payload.secret_value = "" }
        $payload = $null
        Remove-Variable serverScript -ErrorAction SilentlyContinue
    }
}

$resolvedEnvFilePath = if ([IO.Path]::IsPathRooted($EnvFilePath)) {
    $EnvFilePath
} else {
    Join-Path $repoRoot $EnvFilePath
}
Import-SelectedDotEnvValues -Path $resolvedEnvFilePath -Names @(
    "E2E_AZURE_FOUNDRY_ENDPOINT",
    "E2E_AZURE_FOUNDRY_API_VERSION",
    "E2E_AZURE_FOUNDRY_DEPLOYMENT",
    "E2E_AZURE_FOUNDRY_API_KEY",
    "E2E_AZURE_FOUNDRY_AD_TOKEN",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_AD_TOKEN",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "AZURE_SUBSCRIPTION_ID",
    "AI_MODEL_CREDENTIAL_ENCRYPTION_KEY",
    "INTERNAL_MCP_SHARED_SECRET",
    "MCP_API_JWT_SECRET"
)

if (-not $Endpoint -and $env:E2E_AZURE_FOUNDRY_ENDPOINT) {
    $Endpoint = $env:E2E_AZURE_FOUNDRY_ENDPOINT
}
if (-not $env:AZURE_OPENAI_API_KEY -and $env:E2E_AZURE_FOUNDRY_API_KEY -ne "unknown-variable") {
    $env:AZURE_OPENAI_API_KEY = $env:E2E_AZURE_FOUNDRY_API_KEY
}
if (-not $env:AZURE_OPENAI_AD_TOKEN -and $env:E2E_AZURE_FOUNDRY_AD_TOKEN -ne "unknown-variable") {
    $env:AZURE_OPENAI_AD_TOKEN = $env:E2E_AZURE_FOUNDRY_AD_TOKEN
}
if ($env:E2E_AZURE_FOUNDRY_API_VERSION) {
    $env:AZURE_OPENAI_API_VERSION = $env:E2E_AZURE_FOUNDRY_API_VERSION
}
if (($env:E2E_AZURE_FOUNDRY_DEPLOYMENT) -and $env:E2E_AZURE_FOUNDRY_DEPLOYMENT -ne $Model) {
    throw "Configured E2E deployment does not match the required model '$Model'."
}

if (-not $env:AZURE_OPENAI_API_KEY -and -not $env:AZURE_OPENAI_AD_TOKEN) {
    Import-ApprovedServerModelCredential `
        -Target $SshTarget `
        -Container $ServerApiContainer `
        -RequiredModel $Model
}

if (-not $env:AZURE_OPENAI_API_KEY -and -not $env:AZURE_OPENAI_AD_TOKEN) {
    & (Join-Path $repoRoot "infra\scripts\login_service_principal.ps1") -EnvFilePath $EnvFilePath
    if ($LASTEXITCODE -ne 0) { throw "Azure service-principal login failed." }
    $env:AZURE_OPENAI_AD_TOKEN = az account get-access-token `
        --resource https://cognitiveservices.azure.com `
        --query accessToken `
        --output tsv `
        --only-show-errors
}
if (-not $env:AZURE_OPENAI_API_KEY -and -not $env:AZURE_OPENAI_AD_TOKEN) {
    throw "Azure Foundry credential is unavailable; mock fallback is forbidden."
}
if (-not $Endpoint) {
    throw "Azure Foundry endpoint is unavailable."
}
if (-not $env:AI_MODEL_CREDENTIAL_ENCRYPTION_KEY -or
    $env:AI_MODEL_CREDENTIAL_ENCRYPTION_KEY -eq "unknown-variable") {
    $env:AI_MODEL_CREDENTIAL_ENCRYPTION_KEY = New-EphemeralSecret -ByteCount 48
}
$internalSecret = $env:INTERNAL_MCP_SHARED_SECRET
if (-not $internalSecret -or $internalSecret -eq "unknown-variable") {
    $internalSecret = $env:MCP_API_JWT_SECRET
}
if (-not $internalSecret -or $internalSecret -eq "unknown-variable") {
    $internalSecret = New-EphemeralSecret -ByteCount 32
}

$python = Join-Path $repoRoot "conda\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Task conda Python is missing." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required." }
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) { throw "npx is required." }

Assert-PortFree -Port $ApiPort
Assert-PortFree -Port $McpPort
& (Join-Path $repoRoot "skills\start-postgres\scripts\start_postgres.ps1") | Out-Null
if ((docker inspect -f '{{.State.Health.Status}}' $containerName) -ne "healthy") {
    throw "Local PostgreSQL container is not healthy."
}

$utcStamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
$runId = "issue-651-$utcStamp"
$apiDatabase = "issue651_api_$utcStamp"
$courtDatabase = "issue651_court_$utcStamp"
Assert-SyntheticDatabaseName -Name $apiDatabase
Assert-SyntheticDatabaseName -Name $courtDatabase
$apiDbCloud = "postgresql://postgres:postgres@127.0.0.1:5432/$apiDatabase"
$courtDbCloud = "postgresql://postgres:postgres@127.0.0.1:5432/$courtDatabase"
$runRoot = Join-Path $repoRoot "runs\e2e\issue-651-latest-court-decisions\$runId"
$blobRoot = Join-Path $repoRoot "runs\storage\issue-651\$runId\files"
$manifestPath = Join-Path $runRoot "manifest.json"
$screenshotPath = if ($FinalScreenshotPath) {
    if ([IO.Path]::IsPathRooted($FinalScreenshotPath)) { $FinalScreenshotPath }
    else { Join-Path $repoRoot $FinalScreenshotPath }
} else {
    Join-Path $runRoot "01-final-state.png"
}
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $screenshotPath) | Out-Null
if (Test-Path -LiteralPath $screenshotPath) {
    Remove-Item -LiteralPath $screenshotPath -Force
}
$mcpStdoutPath = Join-Path $runRoot "mcp.log"
$mcpStderrPath = Join-Path $runRoot "mcp.err.log"
$apiStdoutPath = Join-Path $runRoot "api.log"
$apiStderrPath = Join-Path $runRoot "api.err.log"

$apiProcess = $null
$mcpProcess = $null
$databasesCreated = $false
$envNamesToClear = @(
    "DB_OPTION", "DB_CLOUD", "STORAGE_OPTION", "STORE_LOCAL", "LLM_PROVIDER",
    "COURT_DECISIONS_DB_BACKEND", "COURT_DECISIONS_DB_CLOUD",
    "INTERNAL_MCP_BASE_URL", "INTERNAL_MCP_SHARED_SECRET", "MCP_PUBLIC_BASE_URL",
    "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "JURISDIGTA_ADMIN_EMAILS",
    "JURISDIGTA_UNLIMITED_ACCESS_EMAILS", "VITE_API_BASE_URL", "VITE_API_KEY",
    "FRONTEND_E2E_PORT", "ISSUE_651_E2E_MANIFEST", "ISSUE_651_E2E_SCREENSHOT",
    "ISSUE_651_MCP_BASE_URL", "ISSUE_651_INTERNAL_MCP_SECRET",
    "AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION"
)

try {
    docker exec $containerName createdb -U postgres $apiDatabase
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the synthetic API database." }
    docker exec $containerName createdb -U postgres $courtDatabase
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the synthetic court database." }
    $databasesCreated = $true

    $env:DB_OPTION = "postgres"
    $env:DB_CLOUD = $apiDbCloud
    $env:STORAGE_OPTION = "local"
    $env:STORE_LOCAL = $blobRoot
    $env:COURT_DECISIONS_DB_BACKEND = "postgres"
    $env:COURT_DECISIONS_DB_CLOUD = $courtDbCloud
    $env:INTERNAL_MCP_BASE_URL = "http://127.0.0.1:$McpPort"
    $env:INTERNAL_MCP_SHARED_SECRET = $internalSecret
    $env:MCP_PUBLIC_BASE_URL = "http://127.0.0.1:$McpPort"
    $env:AZURE_OPENAI_ENDPOINT = $Endpoint.TrimEnd([char[]]",/")
    $env:AZURE_OPENAI_DEPLOYMENT = $Model
    $env:JURISDIGTA_ADMIN_EMAILS = "issue-651-latest-court-e2e@example.test"
    $env:JURISDIGTA_UNLIMITED_ACCESS_EMAILS = "issue-651-latest-court-e2e@example.test"

    & $python (Join-Path $repoRoot "scripts\databases\apply_api_db_schema.py")
    if ($LASTEXITCODE -ne 0) { throw "Synthetic API database migration failed." }

    & $python (Join-Path $repoRoot "scripts\prepare_issue_651_latest_court_e2e.py") `
        --api-db-cloud $apiDbCloud `
        --court-db-cloud $courtDbCloud `
        --blob-root $blobRoot `
        --manifest $manifestPath `
        --endpoint $env:AZURE_OPENAI_ENDPOINT `
        --model $Model `
        --run-id $runId `
        --repo-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Synthetic E2E preparation failed." }
    $preparedManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

    $apiRoot = Join-Path $repoRoot "api\aijuristiction-api"
    $mcpProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.mcp_main:app", "--host", "127.0.0.1", "--port", "$McpPort") `
        -WorkingDirectory $apiRoot `
        -RedirectStandardOutput $mcpStdoutPath `
        -RedirectStandardError $mcpStderrPath `
        -WindowStyle Hidden `
        -PassThru
    Wait-ForUrl -Url "http://127.0.0.1:$McpPort/health"

    $env:LLM_PROVIDER = "azurefoundry"
    $apiProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
        -WorkingDirectory $apiRoot `
        -RedirectStandardOutput $apiStdoutPath `
        -RedirectStandardError $apiStderrPath `
        -WindowStyle Hidden `
        -PassThru
    Wait-ForUrl -Url "http://127.0.0.1:$ApiPort/health"

    $apiHeaders = @{ "x-api-key" = "aijuris" }
    $caseUrl = "http://127.0.0.1:$ApiPort/v1/cases?user_id=$([Uri]::EscapeDataString([string]$preparedManifest.user.userId))"
    $apiCases = Invoke-RestMethod -Method Get -Uri $caseUrl -Headers $apiHeaders
    if (@($apiCases).case_id -notcontains $preparedManifest.case_id) {
        throw "API preflight did not find the prepared synthetic case in the selected PostgreSQL database."
    }
    $routeUrl = "http://127.0.0.1:$ApiPort/v1/model-routing/effective?task_type=chat_reply&user_id=$([Uri]::EscapeDataString([string]$preparedManifest.user.userId))"
    $apiRoute = Invoke-RestMethod -Method Get -Uri $routeUrl -Headers $apiHeaders
    if ($apiRoute.model -ne $Model -or ([string]$apiRoute.route_type) -match "fallback") {
        throw "API preflight did not select the required real model '$Model'."
    }

    $env:VITE_API_BASE_URL = "http://127.0.0.1:$ApiPort"
    $env:VITE_API_KEY = "aijuris"
    $env:FRONTEND_E2E_PORT = "$FrontendPort"
    $env:ISSUE_651_E2E_MANIFEST = $manifestPath
    $env:ISSUE_651_E2E_SCREENSHOT = $screenshotPath
    $env:ISSUE_651_MCP_BASE_URL = "http://127.0.0.1:$McpPort"
    $env:ISSUE_651_INTERNAL_MCP_SECRET = $internalSecret

    $frontendRoot = Join-Path $repoRoot "frontend\aijurisdictionfronend"
    if (-not (Test-Path (Join-Path $frontendRoot "node_modules\.bin\playwright.cmd"))) {
        $previousNodeUseSystemCa = $env:NODE_USE_SYSTEM_CA
        try {
            $env:NODE_USE_SYSTEM_CA = "1"
            npm --prefix $frontendRoot ci --no-audit --prefer-offline
            if ($LASTEXITCODE -ne 0) { throw "Frontend npm install failed." }
        } finally {
            if ($null -eq $previousNodeUseSystemCa) {
                Remove-Item Env:NODE_USE_SYSTEM_CA -ErrorAction SilentlyContinue
            } else {
                $env:NODE_USE_SYSTEM_CA = $previousNodeUseSystemCa
            }
        }
    }
    Push-Location $frontendRoot
    try {
        npx playwright test e2e/issue-651-latest-court-decisions-live.spec.ts --project=chromium
        if ($LASTEXITCODE -ne 0) { throw "Issue #651 real-model E2E failed." }
    } finally {
        Pop-Location
    }

    Write-Output "Issue #651 real Azure gpt-5-mini E2E passed."
    Write-Output "Sanitized manifest: $manifestPath"
    Write-Output "Final screenshot: $screenshotPath"
    Write-Output "Retention: delete this synthetic evidence within 7 days."
} finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
    }
    if ($mcpProcess -and -not $mcpProcess.HasExited) {
        Stop-Process -Id $mcpProcess.Id -Force
    }
    Start-Sleep -Seconds 1
    if ($databasesCreated) {
        Assert-SyntheticDatabaseName -Name $apiDatabase
        Assert-SyntheticDatabaseName -Name $courtDatabase
        docker exec $containerName dropdb -U postgres --if-exists --force $apiDatabase | Out-Null
        docker exec $containerName dropdb -U postgres --if-exists --force $courtDatabase | Out-Null
    }
    foreach ($name in $envNamesToClear) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    Remove-Item Env:AZURE_OPENAI_AD_TOKEN -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $mcpStdoutPath, $mcpStderrPath, $apiStdoutPath, $apiStderrPath `
        -Force -ErrorAction SilentlyContinue
}
