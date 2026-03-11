param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8090,
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$Reload,
    [switch]$Install
)

$ErrorActionPreference = "Stop"

function Resolve-PythonPath {
    param([string]$RepoRoot)

    foreach ($candidate in @(".conda\\python.exe", "conda\\python.exe")) {
        $pythonPath = Join-Path $RepoRoot $candidate
        if (Test-Path $pythonPath) {
            return $pythonPath
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python interpreter not found. Create a repo conda env or add python to PATH."
}

function Resolve-ShellPath {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwsh) {
        return $pwsh.Source
    }

    $powershell = Get-Command powershell -ErrorAction SilentlyContinue
    if ($powershell) {
        return $powershell.Source
    }

    throw "PowerShell executable not found."
}

function Test-UrlReady {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-SimulatorReady {
    param(
        [string]$TargetHost,
        [int]$TargetPort
    )

    $healthUrl = "http://$TargetHost`:$TargetPort/health"
    $uiUrl = "http://$TargetHost`:$TargetPort/chat-simulator"
    return (Test-UrlReady -Url $healthUrl) -and (Test-UrlReady -Url $uiUrl)
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\\..\\..")
$appDir = Join-Path $repoRoot "api\\chat-simulator-app"
$shellPath = Resolve-ShellPath

if (-not (Test-Path $appDir)) {
    throw "Chat simulator project folder not found: $appDir"
}

$python = Resolve-PythonPath -RepoRoot $repoRoot

if ($Install) {
    Push-Location $appDir
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
    $scriptPath = Join-Path $repoRoot "skills\chatsimulatr\scripts\start_chat_simulator.ps1"
    $command = "& '$scriptPath' -BindHost $BindHost -Port $Port"
    if ($Reload) {
        $command += " -Reload"
    }
    if ($Install) {
        $command += " -Install"
    }

    Start-Process -FilePath $shellPath -ArgumentList @("-NoExit", "-Command", $command) -WorkingDirectory $repoRoot | Out-Null
    Write-Output "Chat simulator console window started."
    Write-Output "URL: http://$BindHost`:$Port/chat-simulator"
    exit 0
}

if ($Background) {
    $runsDir = Join-Path $repoRoot "runs"
    if (-not (Test-Path $runsDir)) {
        New-Item -Path $runsDir -ItemType Directory | Out-Null
    }

    $stdoutLog = Join-Path $runsDir "chat-simulator.log"
    $stderrLog = Join-Path $runsDir "chat-simulator.err.log"
    $pidFile = Join-Path $runsDir "chat-simulator.pid"

    if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
    if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }

    $process = Start-Process `
        -FilePath $python `
        -ArgumentList $uvicornArgs `
        -WorkingDirectory $appDir `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    Start-Sleep -Seconds 3

    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        throw "Chat simulator process exited immediately. Check $stderrLog"
    }

    $process.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline

    if (Test-SimulatorReady -TargetHost $BindHost -TargetPort $Port) {
        Write-Output "Chat simulator started in background. PID: $($process.Id)"
        Write-Output "URL: http://$BindHost`:$Port/chat-simulator"
        Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
    } else {
        Write-Warning "Chat simulator started (PID $($process.Id)) but readiness checks are not complete yet."
        Write-Output "Check logs:"
        Write-Output "  $stdoutLog"
        Write-Output "  $stderrLog"
    }
    exit 0
}

Write-Output "Starting chat simulator in foreground on http://$BindHost`:$Port/chat-simulator"
Push-Location $appDir
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
