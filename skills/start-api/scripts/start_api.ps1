param(
    [ValidateSet("azurefoundry", "openai", "mock")]
    [string]$LlmProvider = "azurefoundry",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8080,
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$Reload,
    [switch]$Install
)

$ErrorActionPreference = "Stop"

function Resolve-PythonPath {
    param([string]$RepoRoot)

    $condaPython = Join-Path $RepoRoot ".conda\\python.exe"
    if (Test-Path $condaPython) {
        return $condaPython
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python interpreter not found. Create .conda env or add python to PATH."
}

function Test-ApiHealth {
    param(
        [string]$TargetHost,
        [int]$TargetPort
    )

    $url = "http://$TargetHost`:$TargetPort/health"
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\\..\\..")
$apiDir = Join-Path $repoRoot "api\\aijuristiction-api"
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source

if (-not (Test-Path $apiDir)) {
    throw "API project folder not found: $apiDir"
}

$python = Resolve-PythonPath -RepoRoot $repoRoot
$env:LLM_PROVIDER = $LlmProvider

if ($Install) {
    Push-Location $apiDir
    try {
        & $python -m pip install -e ".[dev]"
    } finally {
        Pop-Location
    }
}

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", "$Port")
if ($Reload) {
    $uvicornArgs += "--reload"
}

if ($ConsoleWindow) {
    if (-not $pwsh) {
        throw "PowerShell 7 (pwsh) was not found on PATH."
    }

    $scriptPath = Join-Path $repoRoot "skills\start-api\scripts\start_api.ps1"
    $consoleArgs = @(
        "-NoExit",
        "-Command",
        "& '$scriptPath' -LlmProvider $LlmProvider -BindHost $BindHost -Port $Port"
    )
    if ($Reload) {
        $consoleArgs[-1] += " -Reload"
    }
    if ($Install) {
        $consoleArgs[-1] += " -Install"
    }

    Start-Process -FilePath $pwsh -ArgumentList $consoleArgs -WorkingDirectory $repoRoot | Out-Null
    Write-Output "API console window started."
    Write-Output "Health: http://$BindHost`:$Port/health"
    Write-Output "Docs: http://$BindHost`:$Port/docs"
    exit 0
}

if ($Background) {
    $runsDir = Join-Path $repoRoot "runs"
    if (-not (Test-Path $runsDir)) {
        New-Item -Path $runsDir -ItemType Directory | Out-Null
    }

    $stdoutLog = Join-Path $runsDir "api-local.log"
    $stderrLog = Join-Path $runsDir "api-local.err.log"
    $pidFile = Join-Path $runsDir "api-local.pid"

    if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
    if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }

    $process = Start-Process `
        -FilePath $python `
        -ArgumentList $uvicornArgs `
        -WorkingDirectory $apiDir `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    Start-Sleep -Seconds 3

    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        throw "API process exited immediately. Check $stderrLog"
    }

    $process.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline

    $isHealthy = Test-ApiHealth -TargetHost $BindHost -TargetPort $Port
    if ($isHealthy) {
        Write-Output "API started in background. PID: $($process.Id)"
        Write-Output "Health: http://$BindHost`:$Port/health"
        Write-Output "Docs: http://$BindHost`:$Port/docs"
        Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
    } else {
        Write-Warning "API started (PID $($process.Id)) but health endpoint is not ready yet."
        Write-Output "Check logs:"
        Write-Output "  $stdoutLog"
        Write-Output "  $stderrLog"
    }
    exit 0
}

Write-Output "Starting API in foreground on http://$BindHost`:$Port (LLM_PROVIDER=$LlmProvider)"
Push-Location $apiDir
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
