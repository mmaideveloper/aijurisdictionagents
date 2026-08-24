param(
    [string]$ApiBaseUrl = "https://api.jurisdigta.eu",
    [string]$FrontendBaseUrl = "https://web.jurisdigta.eu",
    [string]$McpBaseUrl = "https://mcp.jurisdigta.eu",
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9a-fA-F]{40}$")]
    [string]$DeployedCommitSha,
    [int]$TimeoutMs = 300000,
    [string]$EnvFilePath = ".env"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$e2eRoot = Join-Path $repoRoot "api\aijuristiction-api\e2e-playwright"
$resolvedEnvPath = if ([System.IO.Path]::IsPathRooted($EnvFilePath)) {
    $EnvFilePath
} else {
    Join-Path $repoRoot $EnvFilePath
}

function Read-EnvValue {
    param([string]$Path, [string]$Name)

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

if (-not $env:JURISDIGTA_E2E_TEST_USER_PASSWORD) {
    $env:JURISDIGTA_E2E_TEST_USER_PASSWORD = Read-EnvValue `
        -Path $resolvedEnvPath `
        -Name "JURISDIGTA_E2E_TEST_USER_PASSWORD"
}
if (
    -not $env:JURISDIGTA_E2E_TEST_USER_PASSWORD -or
    $env:JURISDIGTA_E2E_TEST_USER_PASSWORD -eq "unknown-variable"
) {
    throw (
        "Production E2E credentials are unavailable. Pull the approved codex-agent profile or " +
        "provide JURISDIGTA_E2E_TEST_USER_PASSWORD without printing it. Mock fallback is forbidden."
    )
}

$utcStamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$evidenceRoot = Join-Path $repoRoot "runs\e2e\issue-646-prod-mcp-laws\$utcStamp"
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null

$env:API_BASE_URL = $ApiBaseUrl.TrimEnd('/')
$env:FRONTEND_BASE_URL = $FrontendBaseUrl.TrimEnd('/')
$env:MCP_PUBLIC_BASE_URL = $McpBaseUrl.TrimEnd('/')
$env:ISSUE_646_DEPLOYED_COMMIT_SHA = $DeployedCommitSha.ToLowerInvariant()
$env:ISSUE_646_TIMEOUT_MS = [string]$TimeoutMs
$env:PW_START_API = "0"
$previousNodeOptions = $env:NODE_OPTIONS
if ($env:NODE_OPTIONS -notmatch "(?:^|\s)--use-system-ca(?:\s|$)") {
    $env:NODE_OPTIONS = ("$($env:NODE_OPTIONS) --use-system-ca").Trim()
}

Push-Location $e2eRoot
try {
    if (-not (Test-Path "node_modules\@playwright\test")) {
        npm ci
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    node node_modules/@playwright/test/cli.js test `
        tests/issue-646-prod-mcp-laws.spec.ts `
        --reporter=list `
        --output=$evidenceRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Issue #646 production E2E failed. Review the sanitized evidence in $evidenceRoot."
    }
} finally {
    Pop-Location
    if ($null -eq $previousNodeOptions) {
        Remove-Item Env:NODE_OPTIONS -ErrorAction SilentlyContinue
    } else {
        $env:NODE_OPTIONS = $previousNodeOptions
    }
    Remove-Item Env:JURISDIGTA_E2E_TEST_USER_PASSWORD -ErrorAction SilentlyContinue
}

Write-Output "Issue #646 production MCP law E2E passed."
Write-Output "Evidence: $evidenceRoot"
Write-Output "Retention: delete this synthetic evidence within 7 days."
