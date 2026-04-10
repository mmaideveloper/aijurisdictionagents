param(
    [ValidateSet("azurefoundry", "openai", "mock")]
    [string]$LlmProvider = "azurefoundry",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8080,
    [string]$DatabaseOption = "",
    [ValidateSet("local", "azure")]
    [string]$StorageOption = "",
    [string]$DbLocal = "",
    [string]$DbCloud = "",
    [string]$StoreLocal = "",
    [string]$StoreCloud = "",
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$Reload,
    [switch]$Install
)

$ErrorActionPreference = "Stop"

function Resolve-EffectiveLlmProvider {
    param([string]$RequestedProvider)

    $normalized = $RequestedProvider.Trim().ToLowerInvariant()
    if ($normalized -ne "azurefoundry") {
        return $normalized
    }

    $hasEndpoint = -not [string]::IsNullOrWhiteSpace($env:AZURE_OPENAI_ENDPOINT)
    $hasDeployment = -not [string]::IsNullOrWhiteSpace($env:AZURE_OPENAI_DEPLOYMENT)
    $hasApiKey = -not [string]::IsNullOrWhiteSpace($env:AZURE_OPENAI_API_KEY)
    $hasAdToken = -not [string]::IsNullOrWhiteSpace($env:AZURE_OPENAI_AD_TOKEN)

    if ($hasEndpoint -and $hasDeployment -and ($hasApiKey -or $hasAdToken)) {
        return "azurefoundry"
    }

    Write-Warning "AZURE_OPENAI_* settings are incomplete for local Azure Foundry use. Falling back to LLM_PROVIDER=mock."
    return "mock"
}

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

    throw "Python interpreter not found. Create .conda env or add python to PATH."
}

function Resolve-PowerShellPath {
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

    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -eq $WindowTitle } |
        ForEach-Object {
            try {
                Stop-Process -Id $_.Id -Force -ErrorAction Stop
            } catch {
            }
        }

    $tailHelperPath = Join-Path $RepoRoot "skills\shared\scripts\tail_logs.ps1"
    if (-not (Test-Path $tailHelperPath)) {
        throw "Log tail helper not found: $tailHelperPath"
    }

    $quotedHelperPath = '"{0}"' -f $tailHelperPath
    $quotedWindowTitle = '"{0}"' -f $WindowTitle.Replace('"', '\"')
    $quotedPathsJoined = '"{0}"' -f (($existing -join '|').Replace('"', '\"'))
    $tailArgs = @("-NoExit", "-File", $quotedHelperPath, "-WindowTitle", $quotedWindowTitle, "-TailLines", "40", "-PathsJoined", $quotedPathsJoined)
    Start-Process -FilePath $ShellPath -ArgumentList $tailArgs -WorkingDirectory $RepoRoot | Out-Null
    return $true
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

function Resolve-RequiredSetting {
    param(
        [string]$Value,
        [string]$EnvironmentVariable,
        [string]$Prompt
    )

    if ($Value) {
        return $Value
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

function Get-LocalPostgresSettingsFromConnectionString {
    param([string]$ConnectionString)

    if (-not $ConnectionString) {
        return $null
    }

    try {
        $uri = [System.Uri]$ConnectionString
    }
    catch {
        return $null
    }

    if ($uri.Scheme -ne "postgresql") {
        return $null
    }
    if ($uri.Host -notin @("127.0.0.1", "localhost")) {
        return $null
    }

    $userInfo = [System.Uri]::UnescapeDataString($uri.UserInfo)
    $user = "postgres"
    $password = "postgres"
    if ($userInfo) {
        $parts = $userInfo.Split(":", 2)
        if ($parts[0]) {
            $user = $parts[0]
        }
        if ($parts.Count -gt 1 -and $parts[1]) {
            $password = $parts[1]
        }
    }

    $databaseName = $uri.AbsolutePath.Trim("/")
    if (-not $databaseName) {
        $databaseName = "aijurisdiction"
    }

    return @{
        DatabaseName = $databaseName
        DatabaseUser = $user
        DatabasePassword = $password
        DatabasePort = $(if ($uri.Port -gt 0) { $uri.Port } else { 5432 })
    }
}

function Ensure-LocalPostgresReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$ExistingDbCloud
    )

    $skillScript = Join-Path $RepoRoot "skills\start-postgres\scripts\start_postgres.ps1"
    if (-not (Test-Path $skillScript)) {
        throw "PostgreSQL start skill not found: $skillScript"
    }
    $shellPath = Resolve-PowerShellPath

    $parsed = Get-LocalPostgresSettingsFromConnectionString -ConnectionString $ExistingDbCloud
    $shellArgs = @("-NoProfile", "-File", $skillScript, "-ProjectName", "api")
    if ($parsed) {
        $shellArgs += @(
            "-DatabaseName", $parsed.DatabaseName,
            "-DatabaseUser", $parsed.DatabaseUser,
            "-DatabasePassword", $parsed.DatabasePassword,
            "-DatabasePort", "$($parsed.DatabasePort)"
        )
    }
    $output = & $shellPath @shellArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Local PostgreSQL startup failed."
    }

    $connectionLine = $output | Where-Object { $_ -like "Connection string:*" } | Select-Object -Last 1
    if (-not $connectionLine) {
        throw "Local PostgreSQL startup did not return a connection string."
    }

    return $connectionLine.Substring("Connection string:".Length).Trim()
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\\..\\..")
$apiDir = Join-Path $repoRoot "api\\aijuristiction-api"
$srcDir = Join-Path $repoRoot "src"
$shellPath = Resolve-PowerShellPath

if (-not (Test-Path $apiDir)) {
    throw "API project folder not found: $apiDir"
}
if (-not (Test-Path $srcDir)) {
    throw "Core source folder not found: $srcDir"
}

$python = Resolve-PythonPath -RepoRoot $repoRoot
$LlmProvider = Resolve-EffectiveLlmProvider -RequestedProvider $LlmProvider
$env:LLM_PROVIDER = $LlmProvider
if (-not $env:LOCAL_LLM_IO_LOGGING) {
    $env:LOCAL_LLM_IO_LOGGING = "1"
}
$pythonPathEntries = @($apiDir, $srcDir)
if ($env:PYTHONPATH) {
    $pythonPathEntries += $env:PYTHONPATH
}
$env:PYTHONPATH = ($pythonPathEntries -join [IO.Path]::PathSeparator)

$DatabaseOption = Normalize-DatabaseOption -Value $DatabaseOption
if ($DatabaseOption) {
    $env:DB_OPTION = $DatabaseOption
}
if ($StorageOption) {
    $env:STORAGE_OPTION = $StorageOption
}
if ($env:DB_OPTION) {
    $env:DB_OPTION = Normalize-DatabaseOption -Value $env:DB_OPTION
} else {
    $env:DB_OPTION = "local"
}
if ($env:STORAGE_OPTION) {
    $env:STORAGE_OPTION = $env:STORAGE_OPTION.Trim().ToLowerInvariant()
    if ($env:STORAGE_OPTION -notin @("local", "azure")) {
        throw "STORAGE_OPTION must be one of: local, azure."
    }
} else {
    $env:STORAGE_OPTION = "local"
}
if ($DbLocal) {
    $env:DB_LOCAL = $DbLocal
}
if ($StoreLocal) {
    $env:STORE_LOCAL = $StoreLocal
}
if ($env:DB_OPTION -eq "postgres") {
    $DbCloud = Ensure-LocalPostgresReady -RepoRoot $repoRoot -ExistingDbCloud $DbCloud
}
elseif (($env:DB_OPTION -eq "azure") -and -not $DbCloud) {
    $DbCloud = Resolve-RequiredSetting -Value $DbCloud -EnvironmentVariable "DB_CLOUD" -Prompt "Enter DB_CLOUD connection string"
}
if ($DbCloud) {
    $env:DB_CLOUD = $DbCloud
}
if ($env:STORAGE_OPTION -eq "azure" -and -not $StoreCloud) {
    $StoreCloud = Resolve-RequiredSetting -Value $StoreCloud -EnvironmentVariable "STORE_CLOUD" -Prompt "Enter STORE_CLOUD connection string"
}
if ($StoreCloud) {
    $env:STORE_CLOUD = $StoreCloud
}

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
    $scriptPath = Join-Path $repoRoot "skills\start-api\scripts\start_api.ps1"
    $consoleArgs = @("-NoExit", "-File", $scriptPath, "-LlmProvider", $LlmProvider, "-BindHost", $BindHost, "-Port", "$Port")
    if ($DatabaseOption) {
        $consoleArgs += @("-DatabaseOption", $DatabaseOption)
    }
    if ($StorageOption) {
        $consoleArgs += @("-StorageOption", $StorageOption)
    }
    if ($DbLocal) {
        $consoleArgs += @("-DbLocal", $DbLocal)
    }
    if ($DbCloud) {
        $consoleArgs += @("-DbCloud", $DbCloud)
    }
    if ($StoreLocal) {
        $consoleArgs += @("-StoreLocal", $StoreLocal)
    }
    if ($StoreCloud) {
        $consoleArgs += @("-StoreCloud", $StoreCloud)
    }
    if ($Reload) {
        $consoleArgs += "-Reload"
    }
    if ($Install) {
        $consoleArgs += "-Install"
    }

    Start-Process -FilePath $shellPath -ArgumentList $consoleArgs -WorkingDirectory $repoRoot | Out-Null
    Write-Output "API console window started."
    Write-Output "Health: http://$BindHost`:$Port/health"
    Write-Output "Docs: http://$BindHost`:$Port/docs"
    Write-Output "Database: $($env:DB_OPTION)"
    Write-Output "Storage: $($env:STORAGE_OPTION)"
    Write-Output "LLM I/O logging: $($env:LOCAL_LLM_IO_LOGGING)"
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
        Write-Output "Database: $($env:DB_OPTION)"
        Write-Output "Storage: $($env:STORAGE_OPTION)"
        Write-Output "LLM I/O logging: $($env:LOCAL_LLM_IO_LOGGING)"
        $openedLogs = Open-LogTailWindow `
            -ShellPath $shellPath `
            -RepoRoot $repoRoot `
            -Paths @($stdoutLog, $stderrLog) `
            -WindowTitle "AI Jurisdiction API Logs"
        if ($openedLogs) {
            Write-Output "API log tail window started."
        }
        Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
    } else {
        Write-Warning "API started (PID $($process.Id)) but health endpoint is not ready yet."
        Write-Output "Check logs:"
        Write-Output "  $stdoutLog"
        Write-Output "  $stderrLog"
    }
    exit 0
}

Write-Output "Starting API in foreground on http://$BindHost`:$Port (LLM_PROVIDER=$LlmProvider, DB_OPTION=$($env:DB_OPTION), STORAGE_OPTION=$($env:STORAGE_OPTION))"
Push-Location $apiDir
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
