param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5173,
    [string]$ApiBaseUrl = "https://api-juris-dev.victoriousdesert-e45eec11.westeurope.azurecontainerapps.io",
    [string]$ApiKey = "aijuris",
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$Install,
    [switch]$NoOpen,
    [switch]$SkipApiStart
)

$ErrorActionPreference = "Stop"

function Resolve-ShellPath {
    $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwshCmd) {
        return $pwshCmd.Source
    }

    $powershellCmd = Get-Command powershell -ErrorAction SilentlyContinue
    if ($powershellCmd) {
        return $powershellCmd.Source
    }

    throw "PowerShell executable not found."
}

function Resolve-NpmPath {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($npmCmd) {
        return $npmCmd.Source
    }

    $npmCmdWin = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCmdWin) {
        return $npmCmdWin.Source
    }

    throw "npm not found. Install Node.js and ensure npm is available on PATH."
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

function Wait-ForUrl {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-UrlReady -Url $Url) {
            return $true
        }
        Start-Sleep -Seconds 2
    }

    return $false
}

function Escape-SingleQuotes {
    param([string]$Value)
    return $Value.Replace("'", "''")
}

function Test-IsLoopbackApiUrl {
    param([string]$Url)

    try {
        $uri = [System.Uri]$Url
    } catch {
        return $false
    }

    return $uri.Host -in @("127.0.0.1", "localhost")
}

function Reset-LogFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    try {
        Remove-Item $Path -Force -ErrorAction Stop
        return
    } catch {
    }

    try {
        Set-Content -Path $Path -Value @() -Encoding ascii -ErrorAction Stop
    } catch {
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$frontendDir = Join-Path $repoRoot "frontend\aijurisdictionfronend"
$apiSkillScript = Join-Path $repoRoot "skills\start-api\scripts\start_api.ps1"
$scriptPath = Join-Path $repoRoot "skills\start-frontend-api\scripts\start_frontend_api.ps1"
$shellPath = Resolve-ShellPath
$npmPath = Resolve-NpmPath
$frontendUrl = "http://$BindHost`:$Port"
$apiHealthUrl = $ApiBaseUrl.TrimEnd("/") + "/health"

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

if (-not (Test-UrlReady -Url $apiHealthUrl)) {
    $isLoopbackApi = Test-IsLoopbackApiUrl -Url $ApiBaseUrl

    if (-not $isLoopbackApi) {
        throw "API is not reachable at $apiHealthUrl. This URL is remote, so local API auto-start is skipped. Provide -ApiBaseUrl http://127.0.0.1:8080 to use local API."
    }

    if ($SkipApiStart) {
        throw "API is not reachable at $apiHealthUrl and -SkipApiStart is set."
    }

    if (-not (Test-Path $apiSkillScript)) {
        throw "API start skill script not found: $apiSkillScript"
    }

    Write-Output "API is not reachable at $apiHealthUrl. Starting local API..."
    & $apiSkillScript -Background | Write-Output
}

if (-not (Wait-ForUrl -Url $apiHealthUrl -TimeoutSeconds 90)) {
    throw "API is still not healthy at $apiHealthUrl. Check .\runs\api-local.err.log"
}

Write-Output "API health OK: $apiHealthUrl"

if ($ConsoleWindow) {
    $args = @(
        "-NoExit",
        "-File",
        $scriptPath,
        "-BindHost",
        $BindHost,
        "-Port",
        "$Port",
        "-ApiBaseUrl",
        $ApiBaseUrl,
        "-ApiKey",
        $ApiKey
    )
    if ($Install) { $args += "-Install" }
    if ($NoOpen) { $args += "-NoOpen" }
    if ($SkipApiStart) { $args += "-SkipApiStart" }

    Start-Process -FilePath $shellPath -ArgumentList $args -WorkingDirectory $repoRoot | Out-Null
    Write-Output "Frontend console window started."
    Write-Output "Frontend URL: $frontendUrl"
    exit 0
}

Push-Location $frontendDir
try {
    if ($Install -or -not (Test-Path "node_modules")) {
        Write-Output "Installing frontend dependencies..."
        & $npmPath install
    }

    if ($Background) {
        $runsDir = Join-Path $repoRoot "runs"
        if (-not (Test-Path $runsDir)) {
            New-Item -Path $runsDir -ItemType Directory | Out-Null
        }

        $stdoutLog = Join-Path $runsDir "frontend-local.log"
        $stderrLog = Join-Path $runsDir "frontend-local.err.log"
        $pidFile = Join-Path $runsDir "frontend-local.pid"

        $existingPidRaw = ""
        $existingProcess = $null
        if (Test-Path $pidFile) {
            $existingPidRaw = (Get-Content $pidFile -Raw).Trim()
            if ($existingPidRaw -match "^\d+$") {
                $existingProcess = Get-Process -Id ([int]$existingPidRaw) -ErrorAction SilentlyContinue
            }
        }

        if (Test-UrlReady -Url $frontendUrl) {
            if ($existingProcess) {
                Write-Output "Frontend is already running at $frontendUrl (PID $existingPidRaw)."
                Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
            } else {
                Write-Output "Frontend is already reachable at $frontendUrl."
            }
            exit 0
        }

        if ((-not $existingProcess) -and (Test-Path $pidFile)) {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }

        Reset-LogFile -Path $stdoutLog
        Reset-LogFile -Path $stderrLog

        $escapedFrontendDir = Escape-SingleQuotes -Value ([string]$frontendDir)
        $escapedApiBaseUrl = Escape-SingleQuotes -Value $ApiBaseUrl
        $escapedApiKey = Escape-SingleQuotes -Value $ApiKey
        $escapedNpmPath = Escape-SingleQuotes -Value $npmPath
        $escapedBindHost = Escape-SingleQuotes -Value $BindHost

        $command = @"
`$ErrorActionPreference = 'Stop'
Set-Location '$escapedFrontendDir'
`$env:VITE_API_BASE_URL = '$escapedApiBaseUrl'
`$env:VITE_API_KEY = '$escapedApiKey'
& '$escapedNpmPath' run dev -- --host '$escapedBindHost' --port $Port --strictPort
"@

        $process = Start-Process `
            -FilePath $shellPath `
            -ArgumentList @("-NoProfile", "-Command", $command) `
            -WorkingDirectory $frontendDir `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog `
            -PassThru

        $process.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline

        if (Wait-ForUrl -Url $frontendUrl -TimeoutSeconds 60) {
            Write-Output "Frontend started in background. PID: $($process.Id)"
            Write-Output "Frontend URL: $frontendUrl"
            Write-Output "API URL: $ApiBaseUrl"
            Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
            if (-not $NoOpen) {
                Start-Process $frontendUrl | Out-Null
            }
        } else {
            Write-Warning "Frontend process started (PID $($process.Id)) but URL is not ready yet."
            Write-Output "Check logs:"
            Write-Output "  $stdoutLog"
            Write-Output "  $stderrLog"
        }

        exit 0
    }

    $env:VITE_API_BASE_URL = $ApiBaseUrl
    $env:VITE_API_KEY = $ApiKey

    if (-not $NoOpen) {
        Start-Process $frontendUrl | Out-Null
    }

    Write-Output "Starting frontend in foreground on $frontendUrl"
    Write-Output "Using VITE_API_BASE_URL=$ApiBaseUrl"
    & $npmPath run dev -- --host $BindHost --port "$Port" --strictPort
} finally {
    Pop-Location
}
