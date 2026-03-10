param(
    [string]$Device = "chrome",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 7357,
    [ValidateSet("localApi", "publicDevApi")]
    [string]$ApiMode = "",
    [string]$ApiBaseUrl = "",
    [string]$PublicDevApiBaseUrl = "",
    [string]$ApiKey = "aijuris",
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$PubGet,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

function Resolve-FlutterPath {
    $userFlutter = Join-Path $env:USERPROFILE "develop\flutter\bin\flutter.bat"
    if (Test-Path $userFlutter) {
        return $userFlutter
    }

    $flutterCmd = Get-Command flutter -ErrorAction SilentlyContinue
    if ($flutterCmd) {
        return $flutterCmd.Source
    }

    throw "Flutter SDK not found. Install Flutter or add flutter to PATH."
}

function Test-WebReady {
    param(
        [string]$TargetHost,
        [int]$TargetPort
    )

    $url = "http://$TargetHost`:$TargetPort"
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Open-AppUrl {
    param([string]$Url)

    if ($NoOpen) {
        return
    }

    Start-Process $Url | Out-Null
}

function Test-ApiReady {
    param([string]$Url)

    $healthUrl = $Url.TrimEnd("/") + "/health"
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Resolve-ApiMode {
    param([string]$RequestedMode)

    if ($RequestedMode) {
        return $RequestedMode
    }

    while ($true) {
        $answer = (Read-Host "Choose API mode [localApi/publicDevApi]").Trim()
        if ($answer -in @("localApi", "publicDevApi")) {
            return $answer
        }
        Write-Warning "Please answer with 'localApi' or 'publicDevApi'."
    }
}

function Resolve-ApiBaseUrl {
    param(
        [string]$Mode,
        [string]$RequestedApiBaseUrl,
        [string]$RequestedPublicDevApiBaseUrl
    )

    if ($RequestedApiBaseUrl) {
        return $RequestedApiBaseUrl
    }

    if ($Mode -eq "localApi") {
        return "http://127.0.0.1:8080"
    }

    if ($RequestedPublicDevApiBaseUrl) {
        return $RequestedPublicDevApiBaseUrl
    }

    foreach ($name in @("PUBLIC_DEV_API_BASE_URL", "AIJ_PUBLIC_DEV_API_URL")) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) {
            return $value
        }
    }

    while ($true) {
        $answer = (Read-Host "Enter public dev API base URL").Trim()
        if ($answer) {
            return $answer
        }
        Write-Warning "Public dev API base URL cannot be empty."
    }
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\..\..")
$appDir = Join-Path $repoRoot "mobile_app"
$runsDir = Join-Path $repoRoot "runs"
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source

if (-not (Test-Path $appDir)) {
    throw "Mobile app folder not found: $appDir"
}

$flutter = Resolve-FlutterPath
$ApiMode = Resolve-ApiMode -RequestedMode $ApiMode
$ApiBaseUrl = Resolve-ApiBaseUrl -Mode $ApiMode -RequestedApiBaseUrl $ApiBaseUrl -RequestedPublicDevApiBaseUrl $PublicDevApiBaseUrl

if ($ApiMode -eq "localApi") {
    if (-not (Test-ApiReady -Url $ApiBaseUrl)) {
        & (Join-Path $repoRoot "skills\start-api\scripts\start_api.ps1") -ConsoleWindow | Out-Null
        Start-Sleep -Seconds 4
    }
} elseif (-not (Test-ApiReady -Url $ApiBaseUrl)) {
    Write-Warning "Public dev API is not reachable at $ApiBaseUrl."
}

if ($ConsoleWindow) {
    if (-not $pwsh) {
        throw "PowerShell 7 (pwsh) was not found on PATH."
    }

    $scriptPath = Join-Path $repoRoot "skills\start-mobile-app\scripts\start_mobile_app.ps1"
    $command = "& '$scriptPath' -Device $Device -BindHost $BindHost -Port $Port -ApiMode $ApiMode -ApiBaseUrl $ApiBaseUrl -ApiKey $ApiKey"
    if ($PublicDevApiBaseUrl) {
        $command += " -PublicDevApiBaseUrl $PublicDevApiBaseUrl"
    }
    if ($PubGet) {
        $command += " -PubGet"
    }
    if ($NoOpen) {
        $command += " -NoOpen"
    }

    Start-Process -FilePath $pwsh -ArgumentList @("-NoExit", "-Command", $command) -WorkingDirectory $repoRoot | Out-Null
    Write-Output "Mobile app console window started."
    if ($Device -eq "chrome" -or $Device -eq "edge") {
        Write-Output "App URL: http://$BindHost`:$Port"
    }
    Write-Output "API URL: $ApiBaseUrl"
    exit 0
}

Push-Location $appDir
try {
    if ($PubGet) {
        & $flutter pub get
    }

    $flutterArgs = @(
        "run",
        "-d", $Device,
        "--dart-define=AIJ_API_BASE_URL=$ApiBaseUrl",
        "--dart-define=AIJ_API_KEY=$ApiKey"
    )

    if ($Device -eq "chrome" -or $Device -eq "edge") {
        $flutterArgs += @("--web-hostname", $BindHost, "--web-port", "$Port")
    }

    if ($Background) {
        if (-not (Test-Path $runsDir)) {
            New-Item -Path $runsDir -ItemType Directory | Out-Null
        }

        $stdoutLog = Join-Path $runsDir "mobile-app-$Port.log"
        $stderrLog = Join-Path $runsDir "mobile-app-$Port.err.log"
        $pidFile = Join-Path $runsDir "mobile-app.pid"

        if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
        if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }

        $process = Start-Process `
            -FilePath $flutter `
            -ArgumentList $flutterArgs `
            -WorkingDirectory $appDir `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog `
            -PassThru

        Start-Sleep -Seconds 25

        if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
            throw "Mobile app process exited immediately. Check $stderrLog"
        }

        $process.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline

        if ($Device -eq "chrome" -or $Device -eq "edge") {
            $isReady = Test-WebReady -TargetHost $BindHost -TargetPort $Port
            if ($isReady) {
                Open-AppUrl -Url "http://$BindHost`:$Port"
                Write-Output "Mobile app started in background. PID: $($process.Id)"
                Write-Output "App URL: http://$BindHost`:$Port"
                Write-Output "API URL: $ApiBaseUrl"
                Write-Output "Logs: $stdoutLog"
                Write-Output "Errors: $stderrLog"
                Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
            } else {
                Write-Warning "Mobile app process started (PID $($process.Id)) but web target is not ready yet."
                Write-Output "Check logs:"
                Write-Output "  $stdoutLog"
                Write-Output "  $stderrLog"
            }
        } else {
            Write-Output "Mobile app started in background. PID: $($process.Id)"
            Write-Output "Device: $Device"
            Write-Output "API URL: $ApiBaseUrl"
            Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
        }
        exit 0
    }

    Write-Output "Starting mobile app on device '$Device' (API=$ApiBaseUrl)"
    if ($Device -eq "chrome" -or $Device -eq "edge") {
        Write-Output "App URL: http://$BindHost`:$Port"
    }
    & $flutter @flutterArgs
} finally {
    Pop-Location
}
