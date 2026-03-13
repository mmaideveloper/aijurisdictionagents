param(
    [string]$DatabaseName = "aijurisdiction",
    [string]$DatabaseUser = "postgres",
    [string]$DatabasePassword = "postgres",
    [int]$DatabasePort = 5432,
    [switch]$SkipSchemaUpdate
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

    throw "Python interpreter not found. Create .conda env or add python to PATH."
}

function Assert-DockerInstalled {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI was not found on PATH."
    }
}

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        New-Item -Path $Path -ItemType Directory -Force | Out-Null
    }
}

function Get-ContainerDetails {
    param([string]$Name)

    $raw = docker inspect $Name 2>$null
    if (-not $raw) {
        return $null
    }

    $parsed = $raw | ConvertFrom-Json
    if ($parsed -is [System.Array]) {
        return $parsed[0]
    }
    return $parsed
}

function Get-ContainerRuntimeName {
    param([Parameter(Mandatory = $true)]$Container)

    return ([string]$Container.Name).TrimStart("/")
}

function Get-ProjectPostgresContainer {
    param([string]$RepoRoot)

    $candidates = @()
    foreach ($name in @("aijurisdiction-postgres-local", "aijurisdiction-postgres")) {
        $container = Get-ContainerDetails -Name $name
        if ($null -eq $container) {
            continue
        }

        $sources = @($container.Mounts | ForEach-Object { [string]$_.Source })
        if ($sources | Where-Object { $_ -like (Join-Path $RepoRoot "databases*") }) {
            $candidates += $container
            continue
        }
        if ([string]$container.Config.Image -like "pgvector/pgvector:*") {
            $candidates += $container
        }
    }

    if (-not $candidates) {
        return $null
    }

    $running = $candidates | Where-Object { [string]$_.State.Status -eq "running" }
    if ($running) {
        return ($running | Select-Object -First 1)
    }

    return ($candidates | Select-Object -First 1)
}

function Get-ContainerEnvValue {
    param(
        [Parameter(Mandatory = $true)]$Container,
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$DefaultValue = ""
    )

    foreach ($item in @($Container.Config.Env)) {
        if ($item -like "$Name=*") {
            return $item.Substring($Name.Length + 1)
        }
    }

    return $DefaultValue
}

function Get-ContainerHostPort {
    param(
        [Parameter(Mandatory = $true)]$Container,
        [int]$DefaultPort = 5432
    )

    $binding = $Container.NetworkSettings.Ports.'5432/tcp'
    if ($binding -and $binding.Count -gt 0 -and $binding[0].HostPort) {
        return [int]$binding[0].HostPort
    }
    return $DefaultPort
}

function Wait-ContainerHealthy {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $container = Get-ContainerDetails -Name $ContainerName
        if ($null -eq $container) {
            throw "Container '$ContainerName' no longer exists."
        }

        $state = [string]$container.State.Status
        $health = ""
        if ($container.State.Health) {
            $health = [string]$container.State.Health.Status
        }

        if ($state -eq "running" -and ($health -eq "" -or $health -eq "healthy")) {
            return
        }

        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "Container '$ContainerName' did not become healthy within $TimeoutSeconds seconds."
}

function Test-DirectoryHasContent {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $false
    }

    return [bool](Get-ChildItem -Force -Path $Path | Select-Object -First 1)
}

function Copy-LegacyPostgresDataIfNeeded {
    param(
        [string]$LegacyRoot,
        [string]$TargetRoot
    )

    $legacyData = Join-Path $LegacyRoot "data"
    $targetData = Join-Path $TargetRoot "data"

    if (-not (Test-DirectoryHasContent -Path $legacyData)) {
        return $false
    }
    if (Test-DirectoryHasContent -Path $targetData) {
        return $false
    }

    Ensure-Directory -Path $targetData

    foreach ($item in Get-ChildItem -Force -Path $legacyData) {
        Copy-Item -Path $item.FullName -Destination $targetData -Recurse -Force
    }

    return $true
}

function Restore-EnvVar {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$PreviousValue
    )

    if ($null -eq $PreviousValue) {
        Remove-Item -Path "Env:$Name" -ErrorAction SilentlyContinue
        return
    }

    Set-Item -Path "Env:$Name" -Value $PreviousValue
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\\..\\..")
$databasesDir = Join-Path $repoRoot "databases"
$persistentRoot = Join-Path $databasesDir "postgress"
$legacyRoot = Join-Path $databasesDir "postgres"
$dataRoot = Join-Path $persistentRoot "data"
$initdbRoot = Join-Path $persistentRoot "initdb"

Assert-DockerInstalled
$python = Resolve-PythonPath -RepoRoot $repoRoot
Ensure-Directory -Path $dataRoot
Ensure-Directory -Path $initdbRoot

$existing = Get-ProjectPostgresContainer -RepoRoot $repoRoot
$migratedLegacyData = $false

if ($null -eq $existing) {
    $migratedLegacyData = Copy-LegacyPostgresDataIfNeeded -LegacyRoot $legacyRoot -TargetRoot $persistentRoot

    Push-Location $databasesDir
    $previousLocalDb = $env:LOCAL_POSTGRES_DB
    $previousLocalUser = $env:LOCAL_POSTGRES_USER
    $previousLocalPassword = $env:LOCAL_POSTGRES_PASSWORD
    $previousLocalPort = $env:LOCAL_POSTGRES_PORT
    try {
        $env:LOCAL_POSTGRES_DB = $DatabaseName
        $env:LOCAL_POSTGRES_USER = $DatabaseUser
        $env:LOCAL_POSTGRES_PASSWORD = $DatabasePassword
        $env:LOCAL_POSTGRES_PORT = "$DatabasePort"
        docker compose up -d postgres | Out-Null
    }
    finally {
        Restore-EnvVar -Name "LOCAL_POSTGRES_DB" -PreviousValue $previousLocalDb
        Restore-EnvVar -Name "LOCAL_POSTGRES_USER" -PreviousValue $previousLocalUser
        Restore-EnvVar -Name "LOCAL_POSTGRES_PASSWORD" -PreviousValue $previousLocalPassword
        Restore-EnvVar -Name "LOCAL_POSTGRES_PORT" -PreviousValue $previousLocalPort
        Pop-Location
    }

    $existing = Get-ContainerDetails -Name "aijurisdiction-postgres-local"
    if ($null -eq $existing) {
        throw "Expected container 'aijurisdiction-postgres-local' was not created."
    }
}
elseif ([string]$existing.State.Status -ne "running") {
    $runtimeName = Get-ContainerRuntimeName -Container $existing
    docker start $runtimeName | Out-Null
    $existing = Get-ContainerDetails -Name $runtimeName
}

$runtimeName = Get-ContainerRuntimeName -Container $existing
Wait-ContainerHealthy -ContainerName $runtimeName

$effectiveDbName = Get-ContainerEnvValue -Container $existing -Name "POSTGRES_DB" -DefaultValue $DatabaseName
$effectiveDbUser = Get-ContainerEnvValue -Container $existing -Name "POSTGRES_USER" -DefaultValue $DatabaseUser
$effectiveDbPassword = Get-ContainerEnvValue -Container $existing -Name "POSTGRES_PASSWORD" -DefaultValue $DatabasePassword
$effectivePort = Get-ContainerHostPort -Container $existing -DefaultPort $DatabasePort
$dbCloud = "postgresql://${effectiveDbUser}:${effectiveDbPassword}@127.0.0.1:${effectivePort}/${effectiveDbName}"

if (-not $SkipSchemaUpdate) {
    $previousDbOption = $env:DB_OPTION
    $previousDbCloud = $env:DB_CLOUD
    try {
        $env:DB_OPTION = "postgres"
        $env:DB_CLOUD = $dbCloud
        & $python (Join-Path $repoRoot "databases\scripts\apply_api_db_schema.py")
        if ($LASTEXITCODE -ne 0) {
            throw "Schema update failed."
        }
    }
    finally {
        Restore-EnvVar -Name "DB_OPTION" -PreviousValue $previousDbOption
        Restore-EnvVar -Name "DB_CLOUD" -PreviousValue $previousDbCloud
    }
}

Write-Output "PostgreSQL container: $runtimeName"
Write-Output "Status: healthy"
Write-Output "Host: 127.0.0.1"
Write-Output "Port: $effectivePort"
Write-Output "Database: $effectiveDbName"
Write-Output "User: $effectiveDbUser"
Write-Output "Persistent storage: $dataRoot"
Write-Output "Connection string: $dbCloud"
if ($migratedLegacyData) {
    Write-Output "Legacy data copied from: $(Join-Path $legacyRoot 'data')"
}
