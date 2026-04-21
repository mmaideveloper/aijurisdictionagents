param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8080,
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$Reload,
    [switch]$Install,
    [switch]$SkipLogTail
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$delegateScript = Join-Path $repoRoot "skills\start-api\scripts\start_api.ps1"
if (-not (Test-Path $delegateScript)) {
    throw "Delegated API launcher not found: $delegateScript"
}

$shellPath = $null
$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwshCmd) {
    $shellPath = $pwshCmd.Source
} else {
    $powershellCmd = Get-Command powershell -ErrorAction SilentlyContinue
    if ($powershellCmd) {
        $shellPath = $powershellCmd.Source
    }
}
if (-not $shellPath) {
    throw "PowerShell executable not found."
}

$args = @(
    "-NoProfile",
    "-File", $delegateScript,
    "-LlmProvider", "azurefoundry",
    "-DatabaseOption", "postgres",
    "-BindHost", $BindHost,
    "-Port", "$Port"
)
if ($Background) {
    $args += "-Background"
}
if ($ConsoleWindow) {
    $args += "-ConsoleWindow"
}
if ($Reload) {
    $args += "-Reload"
}
if ($Install) {
    $args += "-Install"
}
if ($SkipLogTail) {
    $args += "-SkipLogTail"
}

& $shellPath @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($Background) {
    $apiPidFile = Join-Path $repoRoot "runs\api-local.pid"
    $jurisPidFile = Join-Path $repoRoot "runs\juris-api.pid"
    if (Test-Path $apiPidFile) {
        Copy-Item -Path $apiPidFile -Destination $jurisPidFile -Force
    }
}
