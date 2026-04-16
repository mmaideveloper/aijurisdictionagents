param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8090,
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 8080,
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$Reload,
    [switch]$Install,
    [switch]$SkipApiBootstrap
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

function Stop-ProcessFromPidFile {
    param(
        [string]$PidFile,
        [string]$ExpectedProcessName = ""
    )

    if (-not (Test-Path $PidFile)) {
        return
    }

    $rawPid = (Get-Content -Path $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $rawPid) {
        return
    }

    [int]$pidValue = 0
    if (-not [int]::TryParse($rawPid.Trim(), [ref]$pidValue)) {
        return
    }

    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    if ($ExpectedProcessName -and ($process.ProcessName -ne $ExpectedProcessName)) {
        return
    }

    Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
}

function Assert-AzureFoundryProvider {
    param([string]$ApiErrLogPath)

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-Path $ApiErrLogPath) {
            $startupLine = Get-Content -Path $ApiErrLogPath -Tail 100 |
                Where-Object { $_ -like "*API Starting |*" } |
                Select-Object -Last 1
            if ($startupLine) {
                if ($startupLine -match "llm_provider=azurefoundry") {
                    return
                }
                throw "Local API did not start with azurefoundry. Startup line: $startupLine"
            }
        }
        Start-Sleep -Seconds 1
    }

    throw "Could not verify API provider from $ApiErrLogPath"
}

function Ensure-LocalApiForSimulator {
    param(
        [string]$RepoRoot,
        [string]$ShellPath,
        [string]$TargetHost,
        [int]$TargetPort
    )

    $apiHealthUrl = "http://$TargetHost`:$TargetPort/health"
    if (Test-UrlReady -Url $apiHealthUrl) {
        return
    }

    $apiLauncher = Join-Path $RepoRoot "skills\juris-api\scripts\start_juris_api.ps1"
    if (-not (Test-Path $apiLauncher)) {
        throw "Juris API start skill script not found: $apiLauncher"
    }

    $jurisApiPidFile = Join-Path $RepoRoot "runs\juris-api.pid"
    if (Test-Path $jurisApiPidFile) {
        if (Test-UrlReady -Url $apiHealthUrl) {
            return
        }
    }

    $apiArgs = @(
        "-NoProfile",
        "-File", $apiLauncher,
        "-Background",
        "-BindHost", $TargetHost,
        "-Port", "$TargetPort"
    )

    $apiStartOutput = & $ShellPath @apiArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start local API for simulator.`n$($apiStartOutput -join [Environment]::NewLine)"
    }

    $isHealthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-UrlReady -Url $apiHealthUrl) {
            $isHealthy = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $isHealthy) {
        throw "Local API health check failed: $apiHealthUrl"
    }

    $apiErrLogPath = Join-Path $RepoRoot "runs\api-local.err.log"
    Assert-AzureFoundryProvider -ApiErrLogPath $apiErrLogPath
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\\..\\..")
$appDir = Join-Path $repoRoot "api\\chat-simulator-app"
$shellPath = Resolve-ShellPath

if (-not (Test-Path $appDir)) {
    throw "Chat simulator project folder not found: $appDir"
}

$python = Resolve-PythonPath -RepoRoot $repoRoot

if (-not $SkipApiBootstrap) {
    Ensure-LocalApiForSimulator -RepoRoot $repoRoot -ShellPath $shellPath -TargetHost $ApiHost -TargetPort $ApiPort
}

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
    $command = "& '$scriptPath' -BindHost $BindHost -Port $Port -ApiHost $ApiHost -ApiPort $ApiPort -SkipApiBootstrap"
    if ($Reload) {
        $command += " -Reload"
    }
    if ($Install) {
        $command += " -Install"
    }

    Start-Process -FilePath $shellPath -ArgumentList @("-NoExit", "-Command", $command) -WorkingDirectory $repoRoot | Out-Null
    Write-Output "Chat simulator console window started."
    Write-Output "URL: http://$BindHost`:$Port/chat-simulator"
    Write-Output "Local API: http://$ApiHost`:$ApiPort (postgres + azurefoundry)"
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

    Stop-ProcessFromPidFile -PidFile $pidFile -ExpectedProcessName "python"

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
        Write-Output "Local API: http://$ApiHost`:$ApiPort (postgres + azurefoundry)"
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
Write-Output "Local API: http://$ApiHost`:$ApiPort (postgres + azurefoundry)"
Push-Location $appDir
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
