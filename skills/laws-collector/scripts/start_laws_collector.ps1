param(
    [ValidateSet("baseline", "delta", "live")]
    [string]$Fixture = "baseline",
    [int]$PollSeconds = 30,
    [int]$MaxCycles = 1,
    [int]$MaxProbes = 1,
    [ValidateSet("postgres", "sqlite")]
    [string]$DatabaseOption = "postgres",
    [string]$DbLocal = "",
    [string]$DbCloud = "",
    [switch]$Background,
    [switch]$ConsoleWindow
)

$ErrorActionPreference = "Stop"

function Import-DotEnvDefaults {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = [string]$rawLine
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $trimmed = $line.Trim()
        if ($trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) {
            continue
        }

        $name = $parts[0].Trim()
        if (-not $name) {
            continue
        }

        $existing = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($existing)) {
            continue
        }

        $value = $parts[1].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path "Env:$name" -Value $value
    }
}

function Resolve-PythonPath {
    param([string]$RepoRoot)

    foreach ($candidate in @("conda/python.exe", "conda/Scripts/python.exe", ".conda/python.exe", ".conda/Scripts/python.exe")) {
        $pythonPath = Join-Path $RepoRoot $candidate
        if (Test-Path $pythonPath) {
            return $pythonPath
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    throw "Python interpreter not found."
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
            }
            catch {
            }
        }

    $tailHelperPath = Join-Path $RepoRoot "skills\shared\scripts\tail_logs.ps1"
    if (-not (Test-Path $tailHelperPath)) {
        throw "Log tail helper not found: $tailHelperPath"
    }

    $quotedHelperPath = '"{0}"' -f $tailHelperPath
    $quotedWindowTitle = '"{0}"' -f $WindowTitle.Replace('"', '\"')
    $quotedPathsJoined = '"{0}"' -f (($existing -join '|').Replace('"', '\"'))
    $tailArgs = @(
        "-NoExit",
        "-File",
        $quotedHelperPath,
        "-WindowTitle",
        $quotedWindowTitle,
        "-TailLines",
        "40",
        "-PathsJoined",
        $quotedPathsJoined
    )
    Start-Process -FilePath $ShellPath -ArgumentList $tailArgs -WorkingDirectory $RepoRoot | Out-Null
    return $true
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
        $databaseName = "laws_sk"
    }

    return @{
        DatabaseName = $databaseName
        DatabaseUser = $user
        DatabasePassword = $password
        DatabasePort = $(if ($uri.Port -gt 0) { $uri.Port } else { 5433 })
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
    $shellArgs = @("-NoProfile", "-File", $skillScript, "-ProjectName", "laws-collector")
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

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$python = Resolve-PythonPath -RepoRoot $repoRoot
$shellPath = Resolve-PowerShellPath
$workerCommand = 'from services.laws_collector.worker import run_worker; run_worker()'

Import-DotEnvDefaults -Path (Join-Path $repoRoot ".env")

$env:PYTHONPATH = Join-Path $repoRoot "src"
$env:PYTHONUNBUFFERED = "1"
$env:LAWS_COUNTRY = "SK"
$env:LAWS_WORKER_FIXTURE = $Fixture
$env:LAWS_WORKER_POLL_SECONDS = "$PollSeconds"
$env:LAWS_WORKER_MAX_CYCLES = "$MaxCycles"
$env:LAWS_WORKER_MAX_PROBES = "$MaxProbes"
$env:LAWS_STORAGE_LOCAL = "./runs/storage/laws-collector/files/sk"

if ($DatabaseOption -eq "sqlite") {
    $env:LAWS_DB_BACKEND = "sqlite"
    $env:LAWS_DB_LOCAL = $(if ($DbLocal) { $DbLocal } else { "./runs/storage/laws-collector/sqlite/sk_laws.sqlite3" })
    Remove-Item -Path "Env:LAWS_DB_CLOUD" -ErrorAction SilentlyContinue
}
else {
    $env:LAWS_DB_BACKEND = "postgres"
    $env:LAWS_DB_CLOUD = Ensure-LocalPostgresReady -RepoRoot $repoRoot -ExistingDbCloud $DbCloud
    Remove-Item -Path "Env:LAWS_DB_LOCAL" -ErrorAction SilentlyContinue
}

if ($ConsoleWindow) {
    $scriptPath = Join-Path $repoRoot "skills\laws-collector\scripts\start_laws_collector.ps1"
    $consoleArgs = @(
        "-NoExit",
        "-File",
        $scriptPath,
        "-Fixture",
        $Fixture,
        "-PollSeconds",
        "$PollSeconds",
        "-MaxCycles",
        "$MaxCycles",
        "-MaxProbes",
        "$MaxProbes",
        "-DatabaseOption",
        $DatabaseOption
    )
    if ($DbLocal) {
        $consoleArgs += @("-DbLocal", $DbLocal)
    }
    if ($DbCloud) {
        $consoleArgs += @("-DbCloud", $DbCloud)
    }

    Start-Process -FilePath $shellPath -ArgumentList $consoleArgs -WorkingDirectory $repoRoot | Out-Null
    Write-Output "Laws collector console window started."
    Write-Output "Database: $($env:LAWS_DB_BACKEND)"
    if ($env:LAWS_DB_CLOUD) {
        Write-Output "DB_CLOUD: $($env:LAWS_DB_CLOUD)"
    }
    exit 0
}

if ($Background) {
    $runsDir = Join-Path $repoRoot "runs"
    if (-not (Test-Path $runsDir)) {
        New-Item -Path $runsDir -ItemType Directory | Out-Null
    }

    $stdoutLog = Join-Path $runsDir "laws-collector-local.log"
    $stderrLog = Join-Path $runsDir "laws-collector-local.err.log"
    $pidFile = Join-Path $runsDir "laws-collector-local.pid"

    if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
    if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }

    $process = Start-Process `
        -FilePath $python `
        -ArgumentList ('-c "{0}"' -f $workerCommand.Replace('"', '\"')) `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    Start-Sleep -Seconds 3

    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        throw "Laws collector process exited immediately. Check $stderrLog"
    }

    $process.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline

    Write-Output "Laws collector started in background. PID: $($process.Id)"
    Write-Output "Database: $($env:LAWS_DB_BACKEND)"
    if ($env:LAWS_DB_CLOUD) {
        Write-Output "DB_CLOUD: $($env:LAWS_DB_CLOUD)"
    }
    Write-Output "Fixture: $Fixture"
    Write-Output "Max probes per cycle: $MaxProbes"
    Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"
    $openedLogs = Open-LogTailWindow `
        -ShellPath $shellPath `
        -RepoRoot $repoRoot `
        -Paths @($stdoutLog, $stderrLog) `
        -WindowTitle "AI Jurisdiction Laws Collector Logs"
    if ($openedLogs) {
        Write-Output "Log tail window started."
    }
    exit 0
}

Write-Output "Starting laws collector in foreground (fixture=$Fixture, DB=$($env:LAWS_DB_BACKEND), max_probes=$MaxProbes)"
if ($env:LAWS_DB_CLOUD) {
    Write-Output "DB_CLOUD: $($env:LAWS_DB_CLOUD)"
}
Push-Location $repoRoot
try {
    & $python -c $workerCommand
}
finally {
    Pop-Location
}
