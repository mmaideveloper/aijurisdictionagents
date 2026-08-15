param(
    [string]$Endpoint = "https://ai-mmatonok4721ai562138909778.services.ai.azure.com/api/projects/documentprocessing",
    [string]$Model = "gpt-5-mini",
    [string]$EnvFilePath = ".env",
    [int]$ApiPort = 8080,
    [int]$FrontendPort = 5189,
    [string]$FinalScreenshotPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Import-SelectedDotEnvValues {
    param([string]$Path, [string[]]$Names)
    if (-not (Test-Path $Path)) {
        return
    }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        $name = $parts[0].Trim()
        if ($name -notin $Names -or [Environment]::GetEnvironmentVariable($name, "Process")) {
            continue
        }
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$resolvedEnvFilePath = if ([IO.Path]::IsPathRooted($EnvFilePath)) {
    $EnvFilePath
} else {
    Join-Path $repoRoot $EnvFilePath
}
Import-SelectedDotEnvValues -Path $resolvedEnvFilePath -Names @(
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_AD_TOKEN",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "AZURE_SUBSCRIPTION_ID"
)

if (-not $env:AZURE_OPENAI_API_KEY -and -not $env:AZURE_OPENAI_AD_TOKEN) {
    if (Get-Command az -ErrorAction SilentlyContinue) {
        & (Join-Path $repoRoot "infra\scripts\login_service_principal.ps1") -EnvFilePath $EnvFilePath
        if ($LASTEXITCODE -ne 0) {
            throw "Azure service-principal login failed."
        }
        $env:AZURE_OPENAI_AD_TOKEN = az account get-access-token `
            --resource https://cognitiveservices.azure.com `
            --query accessToken `
            --output tsv `
            --only-show-errors
    } else {
        foreach ($requiredName in @("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID")) {
            if (-not [Environment]::GetEnvironmentVariable($requiredName, "Process")) {
                throw "$requiredName is required to obtain a short-lived production Foundry token."
            }
        }
        $tokenResponse = Invoke-RestMethod `
            -Method Post `
            -Uri "https://login.microsoftonline.com/$env:AZURE_TENANT_ID/oauth2/v2.0/token" `
            -ContentType "application/x-www-form-urlencoded" `
            -Body @{
                client_id = $env:AZURE_CLIENT_ID
                client_secret = $env:AZURE_CLIENT_SECRET
                grant_type = "client_credentials"
                scope = "https://cognitiveservices.azure.com/.default"
            }
        $env:AZURE_OPENAI_AD_TOKEN = $tokenResponse.access_token
    }
    if (-not $env:AZURE_OPENAI_AD_TOKEN) {
        throw "A short-lived Azure Foundry access token could not be obtained."
    }
}

$pythonCandidates = @(
    (Join-Path $repoRoot "conda\python.exe"),
    (Join-Path $repoRoot ".conda\python.exe"),
    (Join-Path $repoRoot "conda\Scripts\python.exe"),
    (Join-Path $repoRoot ".conda\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    throw "Task conda Python was not found. Create the task worktree runtime first."
}
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "npx is required for the Playwright E2E."
}

try {
    Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2 | Out-Null
    throw "Port $ApiPort already hosts an API. Stop it so this test can use its isolated database."
} catch {
    if ($_.Exception.Message -like "Port $ApiPort already hosts*") {
        throw
    }
}

$runId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$runRoot = Join-Path $repoRoot "runs\e2e\issue-612-azure-foundry-v1\$runId"
$storageRoot = Join-Path $repoRoot "runs\storage\issue-612-azure-foundry-e2e\$runId"
$dbPath = Join-Path $storageRoot "sqlite\api.sqlite3"
$blobRoot = Join-Path $storageRoot "files"
$manifestPath = Join-Path $runRoot "manifest.json"
$screenshotPath = if ($FinalScreenshotPath) {
    if ([IO.Path]::IsPathRooted($FinalScreenshotPath)) {
        $FinalScreenshotPath
    } else {
        Join-Path $repoRoot $FinalScreenshotPath
    }
} else {
    Join-Path $runRoot "01-final-success.png"
}
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $screenshotPath) -Force | Out-Null

$env:DB_OPTION = "local"
$env:STORAGE_OPTION = "local"
$env:DB_LOCAL = $dbPath
$env:STORE_LOCAL = $blobRoot
$env:AZURE_OPENAI_ENDPOINT = $Endpoint.TrimEnd([char[]]",/")
$env:AZURE_OPENAI_DEPLOYMENT = $Model
$env:JURISDIGTA_ADMIN_EMAILS = "issue-612-foundry-e2e@example.test"
$env:JURISDIGTA_UNLIMITED_ACCESS_EMAILS = "issue-612-foundry-e2e@example.test"
$env:ISSUE_612_E2E_MANIFEST = $manifestPath
$env:ISSUE_612_E2E_SCREENSHOT = $screenshotPath
$env:VITE_API_BASE_URL = "http://127.0.0.1:$ApiPort"
$env:VITE_API_KEY = "aijuris"
$env:FRONTEND_E2E_PORT = "$FrontendPort"

$apiPid = $null
try {
    & $python (Join-Path $repoRoot "scripts\prepare_issue_612_azure_foundry_e2e.py") `
        --db-path $dbPath `
        --blob-root $blobRoot `
        --manifest $manifestPath `
        --endpoint $env:AZURE_OPENAI_ENDPOINT `
        --model $Model `
        --repo-root $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Synthetic E2E state preparation failed."
    }

    & (Join-Path $repoRoot "skills\start-api\scripts\start_api.ps1") `
        -LlmProvider azurefoundry `
        -Port $ApiPort `
        -DatabaseOption local `
        -StorageOption local `
        -DbLocal $dbPath `
        -StoreLocal $blobRoot `
        -Background `
        -SkipLogTail
    $pidFile = Join-Path $repoRoot "runs\api-local.pid"
    $apiPid = [int](Get-Content $pidFile -Raw)

    $apiReady = $false
    foreach ($attempt in 1..30) {
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                $apiReady = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $apiReady) {
        throw "Local issue #612 API did not become healthy on port $ApiPort."
    }

    $frontendDir = Join-Path $repoRoot "frontend\aijurisdictionfronend"
    if (-not (Test-Path (Join-Path $frontendDir "node_modules\.bin\playwright.cmd"))) {
        npm --prefix $frontendDir ci
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend npm install failed."
        }
    }
    Push-Location $frontendDir
    try {
        npx playwright test e2e/issue-612-azure-foundry-v1-live.spec.ts --project=chromium
        if ($LASTEXITCODE -ne 0) {
            throw "Issue #612 Azure Foundry E2E failed."
        }
    } finally {
        Pop-Location
    }

    Write-Output "Issue #612 production Azure Foundry E2E passed."
    Write-Output "Sanitized manifest: $manifestPath"
    Write-Output "Final screenshot: $screenshotPath"
    Write-Output "Retention: remove this synthetic run after at most 7 days."
} finally {
    if ($apiPid -and (Get-Process -Id $apiPid -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $apiPid -Force
    }
}
