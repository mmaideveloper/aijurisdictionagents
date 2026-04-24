param(
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$SkipLogTail
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

    foreach ($candidate in @(".conda\Scripts\python.exe", ".conda\python.exe", "conda\Scripts\python.exe", "conda\python.exe")) {
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
    $tailArgs = @("-NoExit", "-File", $quotedHelperPath, "-WindowTitle", $quotedWindowTitle, "-TailLines", "40", "-PathsJoined", $quotedPathsJoined)
    Start-Process -FilePath $ShellPath -ArgumentList $tailArgs -WorkingDirectory $RepoRoot | Out-Null
    return $true
}

function Normalize-DbOption {
    param([string]$Value)

    if (-not $Value) {
        return ""
    }

    $normalized = $Value.Trim().ToLowerInvariant()
    if ($normalized -eq "postgress") {
        return "postgres"
    }

    return $normalized
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
    $shellArgs = @("-NoProfile", "-File", $skillScript, "-ProjectName", "api")
    if ($ExistingDbCloud) {
        try {
            $uri = [System.Uri]$ExistingDbCloud
            $databaseName = $uri.AbsolutePath.Trim("/")
            if (-not $databaseName) {
                $databaseName = "aijurisdiction"
            }
            $shellArgs += @("-DatabaseName", $databaseName)
            if ($uri.Port -gt 0) {
                $shellArgs += @("-DatabasePort", "$($uri.Port)")
            }
        }
        catch {
        }
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

function Stop-ExistingSchedulerProcesses {
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match "python" -and
            $_.CommandLine -like "*app.email_scheduler_main*"
        }

    foreach ($process in @($processes)) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        }
        catch {
        }
    }
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\..\..")
$apiDir = Join-Path $repoRoot "api\aijuristiction-api"
$srcDir = Join-Path $repoRoot "src"
$runsDir = Join-Path $repoRoot "runs"
$shellPath = Resolve-PowerShellPath
$python = Resolve-PythonPath -RepoRoot $repoRoot

if (-not (Test-Path $apiDir)) {
    throw "API project folder not found: $apiDir"
}

Import-DotEnvDefaults -Path (Join-Path $repoRoot ".env")

$pythonPathEntries = @($apiDir, $srcDir)
if ($env:PYTHONPATH) {
    $pythonPathEntries += $env:PYTHONPATH
}
$env:PYTHONPATH = ($pythonPathEntries -join [IO.Path]::PathSeparator)
$env:PYTHONUNBUFFERED = "1"
$env:EMAIL_SCHEDULER_ENABLED = if ($env:EMAIL_SCHEDULER_ENABLED) { $env:EMAIL_SCHEDULER_ENABLED } else { "true" }

$resolvedEmailDbOption = Normalize-DbOption -Value $(if ($env:EMAIL_DB_OPTION) { $env:EMAIL_DB_OPTION } elseif ($env:DB_OPTION) { $env:DB_OPTION } else { "postgres" })
$env:EMAIL_DB_OPTION = $resolvedEmailDbOption

if ($resolvedEmailDbOption -eq "postgres") {
    $resolvedCloud = ""
    if ($env:EMAIL_DB_CLOUD) {
        $resolvedCloud = $env:EMAIL_DB_CLOUD.Trim()
    }
    elseif ($env:DB_CLOUD) {
        $resolvedCloud = $env:DB_CLOUD.Trim()
    }

    if (-not $resolvedCloud) {
        $resolvedCloud = Ensure-LocalPostgresReady -RepoRoot $repoRoot -ExistingDbCloud ""
    }

    $env:EMAIL_DB_CLOUD = $resolvedCloud
}

if ($ConsoleWindow) {
    $scriptPath = Join-Path $repoRoot "skills\start-email\scripts\start_email_scheduler.ps1"
    $consoleArgs = @("-NoExit", "-File", $scriptPath)
    if ($Background) {
        $consoleArgs += "-Background"
    }
    if ($SkipLogTail) {
        $consoleArgs += "-SkipLogTail"
    }

    Stop-ExistingSchedulerProcesses
    Start-Process -FilePath $shellPath -ArgumentList $consoleArgs -WorkingDirectory $repoRoot | Out-Null
    Write-Output "Email scheduler console window started."
    Write-Output "EMAIL_DB_OPTION: $($env:EMAIL_DB_OPTION)"
    if ($env:EMAIL_DB_CLOUD) {
        Write-Output "EMAIL_DB_CLOUD: $($env:EMAIL_DB_CLOUD)"
    }
    exit 0
}

if (-not (Test-Path $runsDir)) {
    New-Item -Path $runsDir -ItemType Directory | Out-Null
}

if ($Background) {
    $stdoutLog = Join-Path $runsDir "email-scheduler-local.log"
    $stderrLog = Join-Path $runsDir "email-scheduler-local.err.log"
    $pidFile = Join-Path $runsDir "email-scheduler-local.pid"

    Stop-ExistingSchedulerProcesses

    if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
    if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }

    $process = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "app.email_scheduler_main") `
        -WorkingDirectory $apiDir `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    Start-Sleep -Seconds 3

    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        throw "Email scheduler process exited immediately. Check $stderrLog"
    }

    $process.Id | Out-File -FilePath $pidFile -Encoding ascii -NoNewline

    Write-Output "Email scheduler started in background. PID: $($process.Id)"
    Write-Output "EMAIL_DB_OPTION: $($env:EMAIL_DB_OPTION)"
    if ($env:EMAIL_DB_CLOUD) {
        Write-Output "EMAIL_DB_CLOUD: $($env:EMAIL_DB_CLOUD)"
    }
    Write-Output "Logs: $stdoutLog"
    Write-Output "Errors: $stderrLog"
    Write-Output "Stop: Stop-Process -Id (Get-Content `"$pidFile`") -Force"

    if (-not $SkipLogTail) {
        $openedLogs = Open-LogTailWindow `
            -ShellPath $shellPath `
            -RepoRoot $repoRoot `
            -Paths @($stdoutLog, $stderrLog) `
            -WindowTitle "AI Jurisdiction Email Scheduler Logs"
        if ($openedLogs) {
            Write-Output "Email scheduler log tail window started."
        }
    }
    exit 0
}

Stop-ExistingSchedulerProcesses

Write-Output "Starting email scheduler in foreground (EMAIL_DB_OPTION=$($env:EMAIL_DB_OPTION))"
if ($env:EMAIL_DB_CLOUD) {
    Write-Output "EMAIL_DB_CLOUD: $($env:EMAIL_DB_CLOUD)"
}
Push-Location $apiDir
try {
    & $python -m app.email_scheduler_main
}
finally {
    Pop-Location
}
