param(
    [string]$Device = "chrome",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 7357,
    [ValidateSet("localApi", "publicDevApi")]
    [string]$ApiMode = "",
    [string]$ApiBaseUrl = "",
    [string]$PublicDevApiBaseUrl = "",
    [string]$ApiKey = "aijuris",
    [string]$DatabaseOption = "",
    [ValidateSet("local", "azure")]
    [string]$StorageOption = "",
    [string]$DbLocal = "",
    [string]$DbCloud = "",
    [string]$StoreLocal = "",
    [string]$StoreCloud = "",
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

function Get-ListeningProcessInfo {
    param(
        [string]$TargetHost,
        [int]$TargetPort
    )

    try {
        $connection = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop |
            Where-Object { $_.LocalAddress -in @($TargetHost, "0.0.0.0", "::", "::1") } |
            Select-Object -First 1
    } catch {
        return $null
    }

    if (-not $connection) {
        return $null
    }

    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }

    $path = ""
    try {
        $path = $process.Path
    } catch {
        $path = ""
    }

    return [pscustomobject]@{
        Id = $process.Id
        ProcessName = $process.ProcessName
        Path = $path
        LocalAddress = $connection.LocalAddress
        LocalPort = $connection.LocalPort
    }
}

function Stop-StaleFlutterWebServer {
    param(
        [string]$TargetHost,
        [int]$TargetPort
    )

    $listener = Get-ListeningProcessInfo -TargetHost $TargetHost -TargetPort $TargetPort
    if (-not $listener) {
        return $false
    }

    $processName = $listener.ProcessName.ToLowerInvariant()
    $path = [string]$listener.Path
    $isFlutterOwned = $processName -in @("dart", "dartvm", "flutter") -or $path -like "*flutter*"
    if (-not $isFlutterOwned) {
        throw "Port $TargetPort is already in use by process $($listener.ProcessName) (PID $($listener.Id))."
    }

    Stop-Process -Id $listener.Id -Force
    Start-Sleep -Seconds 2
    Write-Output "Stopped stale Flutter web server on port $TargetPort (PID $($listener.Id))."
    return $true
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

function Normalize-DatabaseOption {
    param([string]$Value)

    if (-not $Value) {
        return ""
    }

    $normalized = $Value.Trim().ToLowerInvariant()
    if ($normalized -eq "postgress") {
        return "postgres"
    }
    if ($normalized -in @("local", "postgres", "azure")) {
        return $normalized
    }

    throw "DatabaseOption must be one of: local, postgres, azure."
}

function Resolve-DatabaseOption {
    param([string]$RequestedOption)

    $normalized = Normalize-DatabaseOption -Value $RequestedOption
    if ($normalized) {
        return $normalized
    }

    while ($true) {
        $answer = Normalize-DatabaseOption -Value (Read-Host "Choose database [local/postgres/azure]")
        if ($answer) {
            return $answer
        }
        Write-Warning "Please answer with 'local', 'postgres', or 'azure'."
    }
}

function Resolve-StorageOption {
    param([string]$RequestedOption)

    if ($RequestedOption) {
        return $RequestedOption
    }

    while ($true) {
        $answer = (Read-Host "Choose storage [local/azure]").Trim().ToLowerInvariant()
        if ($answer -in @("local", "azure")) {
            return $answer
        }
        Write-Warning "Please answer with 'local' or 'azure'."
    }
}

function Resolve-RequiredConfigValue {
    param(
        [string]$ProvidedValue,
        [string]$EnvironmentVariable,
        [string]$Prompt
    )

    if ($ProvidedValue) {
        return $ProvidedValue
    }

    $existing = [Environment]::GetEnvironmentVariable($EnvironmentVariable)
    if ($existing) {
        return $existing
    }

    while ($true) {
        $answer = (Read-Host $Prompt).Trim()
        if ($answer) {
            return $answer
        }
        Write-Warning "$EnvironmentVariable cannot be empty."
    }
}

function Open-LogTailWindow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ShellPath,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$Paths,
        [Parameter(Mandatory = $true)]
        [string]$WindowTitle
    )

    $existing = @($Paths | Where-Object { Test-Path $_ })
    if (-not $existing) {
        return $false
    }

    $quotedPaths = $existing | ForEach-Object { "'$_'" }
    $tailCommand = @(
        '$Host.UI.RawUI.WindowTitle = ''' + $WindowTitle.Replace("'", "''") + '''',
        '$paths = @(' + ($quotedPaths -join ", ") + ')',
        'Write-Host "Tailing logs:"',
        '$paths | ForEach-Object { Write-Host "  $_" }',
        'Get-Content -Path $paths -Wait -Tail 20'
    ) -join '; '

    Start-Process -FilePath $ShellPath -ArgumentList @("-NoExit", "-Command", $tailCommand) -WorkingDirectory $RepoRoot | Out-Null
    return $true
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
$shellPath = Resolve-ShellPath

if (-not (Test-Path $appDir)) {
    throw "Mobile app folder not found: $appDir"
}

$flutter = Resolve-FlutterPath
$ApiMode = Resolve-ApiMode -RequestedMode $ApiMode
$ApiBaseUrl = Resolve-ApiBaseUrl -Mode $ApiMode -RequestedApiBaseUrl $ApiBaseUrl -RequestedPublicDevApiBaseUrl $PublicDevApiBaseUrl

if ($ApiMode -eq "localApi") {
    $DatabaseOption = Resolve-DatabaseOption -RequestedOption $DatabaseOption
    $StorageOption = Resolve-StorageOption -RequestedOption $StorageOption
    if ($DatabaseOption -eq "azure") {
        $DbCloud = Resolve-RequiredConfigValue -ProvidedValue $DbCloud -EnvironmentVariable "DB_CLOUD" -Prompt "Enter DB_CLOUD connection string"
    }
    if ($StorageOption -eq "azure") {
        $StoreCloud = Resolve-RequiredConfigValue -ProvidedValue $StoreCloud -EnvironmentVariable "STORE_CLOUD" -Prompt "Enter STORE_CLOUD connection string"
    }
}

if ($ApiMode -eq "localApi") {
    Write-Output "Starting local mobile app against local API."
    Write-Output "Requested database: $DatabaseOption"
    Write-Output "Requested storage: $StorageOption"
    if (-not (Test-ApiReady -Url $ApiBaseUrl)) {
        $apiStartArgs = @{
            ConsoleWindow = $true
            DatabaseOption = $DatabaseOption
            StorageOption = $StorageOption
        }
        if ($DbLocal) {
            $apiStartArgs["DbLocal"] = $DbLocal
        }
        if ($DbCloud) {
            $apiStartArgs["DbCloud"] = $DbCloud
        }
        if ($StoreLocal) {
            $apiStartArgs["StoreLocal"] = $StoreLocal
        }
        if ($StoreCloud) {
            $apiStartArgs["StoreCloud"] = $StoreCloud
        }
        Write-Output "Launching local API with visible console logs..."
        & (Join-Path $repoRoot "skills\start-api\scripts\start_api.ps1") @apiStartArgs
        Start-Sleep -Seconds 4
        Write-Output "Waiting for local API health at $ApiBaseUrl/health"
    } elseif ($ConsoleWindow -and (Test-IsLoopbackApiUrl -Url $ApiBaseUrl)) {
        $openedApiLogs = Open-LogTailWindow `
            -ShellPath $shellPath `
            -RepoRoot $repoRoot `
            -Paths @(
                (Join-Path $runsDir "api-local.log"),
                (Join-Path $runsDir "api-local.err.log")
            ) `
            -WindowTitle "AI Jurisdiction API Logs"
        if ($openedApiLogs) {
            Write-Output "API log tail window started."
        }
    }
    Write-Output "Local API URL: $ApiBaseUrl"
} elseif (-not (Test-ApiReady -Url $ApiBaseUrl)) {
    Write-Warning "Public dev API is not reachable at $ApiBaseUrl."
}

if ($ConsoleWindow) {
    $scriptPath = Join-Path $repoRoot "skills\start-mobile-app\scripts\start_mobile_app.ps1"
    $commandArgs = @("-NoExit", "-File", $scriptPath, "-Device", $Device, "-BindHost", $BindHost, "-Port", "$Port", "-ApiMode", $ApiMode, "-ApiBaseUrl", $ApiBaseUrl, "-ApiKey", $ApiKey)
    if ($PublicDevApiBaseUrl) {
        $commandArgs += @("-PublicDevApiBaseUrl", $PublicDevApiBaseUrl)
    }
    if ($DatabaseOption) {
        $commandArgs += @("-DatabaseOption", $DatabaseOption)
    }
    if ($StorageOption) {
        $commandArgs += @("-StorageOption", $StorageOption)
    }
    if ($DbLocal) {
        $commandArgs += @("-DbLocal", $DbLocal)
    }
    if ($DbCloud) {
        $commandArgs += @("-DbCloud", $DbCloud)
    }
    if ($StoreLocal) {
        $commandArgs += @("-StoreLocal", $StoreLocal)
    }
    if ($StoreCloud) {
        $commandArgs += @("-StoreCloud", $StoreCloud)
    }
    if ($PubGet) {
        $commandArgs += "-PubGet"
    }
    if ($NoOpen) {
        $commandArgs += "-NoOpen"
    }

    Start-Process -FilePath $shellPath -ArgumentList $commandArgs -WorkingDirectory $repoRoot | Out-Null
    Write-Output "Mobile app console window started."
    if ($Device -eq "chrome" -or $Device -eq "edge") {
        Write-Output "App URL: http://$BindHost`:$Port"
    }
    Write-Output "API URL: $ApiBaseUrl"
    if ($ApiMode -eq "localApi") {
        Write-Output "Database: $DatabaseOption"
        Write-Output "Storage: $StorageOption"
    }
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

        Stop-StaleFlutterWebServer -TargetHost $BindHost -TargetPort $Port | Out-Null

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
        $starterProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
        $listenerProcess = $null
        if ($Device -eq "chrome" -or $Device -eq "edge") {
            $listenerProcess = Get-ListeningProcessInfo -TargetHost $BindHost -TargetPort $Port
        }

        $pidToPersist = $null
        if ($starterProcess) {
            $pidToPersist = $process.Id
        } elseif ($listenerProcess) {
            $pidToPersist = $listenerProcess.Id
        }

        if ($pidToPersist) {
            $pidToPersist | Out-File -FilePath $pidFile -Encoding ascii -NoNewline
        }

        if ($Device -eq "chrome" -or $Device -eq "edge") {
            $isReady = Test-WebReady -TargetHost $BindHost -TargetPort $Port
            if ($isReady) {
                Open-AppUrl -Url "http://$BindHost`:$Port"
                Write-Output "Mobile app started in background. PID: $pidToPersist"
                Write-Output "App URL: http://$BindHost`:$Port"
                Write-Output "API URL: $ApiBaseUrl"
                if ($ApiMode -eq "localApi") {
                    Write-Output "Database: $DatabaseOption"
                    Write-Output "Storage: $StorageOption"
                }
                Write-Output "Logs: $stdoutLog"
                Write-Output "Errors: $stderrLog"
                Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
            } else {
                if (-not $starterProcess -and -not $listenerProcess) {
                    throw "Mobile app process exited immediately. Check $stderrLog"
                }
                Write-Warning "Mobile app process started (PID $($process.Id)) but web target is not ready yet."
                Write-Output "Check logs:"
                Write-Output "  $stdoutLog"
                Write-Output "  $stderrLog"
            }
        } else {
            if (-not $starterProcess) {
                throw "Mobile app process exited immediately. Check $stderrLog"
            }
            Write-Output "Mobile app started in background. PID: $($process.Id)"
            Write-Output "Device: $Device"
            Write-Output "API URL: $ApiBaseUrl"
            if ($ApiMode -eq "localApi") {
                Write-Output "Database: $DatabaseOption"
                Write-Output "Storage: $StorageOption"
            }
            Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
        }
        exit 0
    }

    Write-Output "Starting mobile app on device '$Device' (API=$ApiBaseUrl)"
    if ($Device -eq "chrome" -or $Device -eq "edge") {
        Write-Output "App URL: http://$BindHost`:$Port"
    }
    if ($ApiMode -eq "localApi") {
        Write-Output "Database: $DatabaseOption"
        Write-Output "Storage: $StorageOption"
        Write-Output "Flutter logs will stream in this console."
    }
    & $flutter @flutterArgs
} finally {
    Pop-Location
}
