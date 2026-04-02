param(
    [ValidateSet("api", "laws-collector")]
    [string]$ProjectName = "api",
    [string]$DatabaseName = "",
    [string]$DatabaseUser = "postgres",
    [string]$DatabasePassword = "postgres",
    [int]$DatabasePort = 0,
    [switch]$SkipSchemaUpdate
)

$ErrorActionPreference = "Stop"

function Resolve-PythonPath {
    param([string]$RepoRoot)

    foreach ($candidate in @(".conda\python.exe", "conda\python.exe")) {
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

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -ItemType Directory -Force | Out-Null
    }
}

function Get-ContainerDetails {
    param([string]$Name)

    $containerId = $null
    $containerRows = & docker ps -a --format "{{.ID}}`t{{.Names}}"
    foreach ($row in @($containerRows)) {
        $parts = ([string]$row).Split("`t", 2)
        if ($parts.Count -eq 2 -and $parts[1] -eq $Name) {
            $containerId = $parts[0]
            break
        }
    }
    if (-not $containerId) {
        return $null
    }

    $raw = & docker inspect $containerId
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

function Test-ContainerUsesStorageRoot {
    param(
        [Parameter(Mandatory = $true)]$Container,
        [Parameter(Mandatory = $true)][string]$RootPath
    )

    $normalizedRoot = [string](Resolve-Path -LiteralPath $RootPath -ErrorAction SilentlyContinue)
    if (-not $normalizedRoot) {
        $normalizedRoot = $RootPath
    }

    foreach ($mount in @($Container.Mounts)) {
        $source = [string]$mount.Source
        if ($source.StartsWith($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Get-ContainerStorageRootInUse {
    param(
        [Parameter(Mandatory = $true)]$Container,
        [Parameter(Mandatory = $true)][string[]]$RootPaths
    )

    foreach ($rootPath in $RootPaths) {
        if (Test-ContainerUsesStorageRoot -Container $Container -RootPath $rootPath) {
            return $rootPath
        }
    }

    return $null
}

function Get-ProjectPostgresContainer {
    param([hashtable]$ProjectSettings)

    $candidates = @()
    foreach ($name in $ProjectSettings.CandidateContainerNames) {
        $container = Get-ContainerDetails -Name $name
        if ($null -eq $container) {
            continue
        }
        $candidates += $container
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

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    return [bool](Get-ChildItem -Force -LiteralPath $Path | Select-Object -First 1)
}

function Copy-DirectoryContentsIfTargetEmpty {
    param(
        [string]$Source,
        [string]$Target
    )

    if (-not (Test-DirectoryHasContent -Path $Source)) {
        return $false
    }
    if (Test-DirectoryHasContent -Path $Target) {
        return $false
    }

    Ensure-Directory -Path $Target
    foreach ($item in Get-ChildItem -Force -LiteralPath $Source) {
        Copy-Item -LiteralPath $item.FullName -Destination $Target -Recurse -Force
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

function Resolve-ProjectSettings {
    param(
        [string]$RepoRoot,
        [string]$ProjectName
    )

    switch ($ProjectName) {
        "api" {
            return @{
                ProjectName = "api"
                DefaultDbName = "aijurisdiction"
                DefaultPort = 5432
                DedicatedContainerName = "aijurisdiction-postgres-local"
                CandidateContainerNames = @("aijurisdiction-postgres-local", "aijurisdiction-postgres")
                DataRoot = Join-Path $RepoRoot "runs\storage\api\postgres\data"
                InitdbRoot = Join-Path $RepoRoot "databases\api\initdb"
                LegacyDataRoots = @(
                    (Join-Path $RepoRoot "databases\storage\postgres\data"),
                    (Join-Path $RepoRoot "databases\postgres\data"),
                    (Join-Path $RepoRoot "databases\postgress\data")
                )
                LegacyInitdbRoots = @(
                    (Join-Path $RepoRoot "databases\storage\postgres\initdb"),
                    (Join-Path $RepoRoot "databases\postgres\initdb"),
                    (Join-Path $RepoRoot "databases\postgress\initdb")
                )
                SchemaCommand = @((Join-Path $RepoRoot "scripts\databases\apply_api_db_schema.py"))
            }
        }
        "laws-collector" {
            return @{
                ProjectName = "laws-collector"
                DefaultDbName = "laws_sk"
                DefaultPort = 5433
                DedicatedContainerName = "aijurisdiction-laws-collector-postgres-local"
                CandidateContainerNames = @(
                    "aijurisdiction-laws-collector-postgres-local",
                    "aijurisdiction-postgres-pgvector-5433"
                )
                DataRoot = Join-Path $RepoRoot "runs\storage\laws-collector\postgres\data"
                InitdbRoot = Join-Path $RepoRoot "databases\laws-collector\initdb"
                LegacyDataRoots = @(
                    (Join-Path $RepoRoot "databases\storage\postgres\data-pgvector-5433")
                )
                LegacyInitdbRoots = @()
                SchemaCommand = @(
                    (Join-Path $RepoRoot "scripts\databases\apply_db_migrations.py"),
                    "--project",
                    "laws"
                )
            }
        }
    }

    throw "Unsupported project name: $ProjectName"
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\..\..")
$python = Resolve-PythonPath -RepoRoot $repoRoot
Assert-DockerInstalled

$projectSettings = Resolve-ProjectSettings -RepoRoot $repoRoot -ProjectName $ProjectName
$effectiveDbName = if ($DatabaseName) { $DatabaseName } else { $projectSettings.DefaultDbName }
$effectivePort = if ($DatabasePort -gt 0) { $DatabasePort } else { [int]$projectSettings.DefaultPort }
$dataRoot = [string]$projectSettings.DataRoot
$initdbRoot = [string]$projectSettings.InitdbRoot
$legacyStorageRoots = @($projectSettings.LegacyDataRoots + $projectSettings.LegacyInitdbRoots)

$existing = Get-ProjectPostgresContainer -ProjectSettings $projectSettings
$migratedLegacyRoots = @()
$existingLegacyStorageRoot = $null

if ($null -ne $existing) {
    $existingLegacyStorageRoot = Get-ContainerStorageRootInUse -Container $existing -RootPaths $legacyStorageRoots
    if ($existingLegacyStorageRoot -and ([string]$existing.State.Status -ne "running")) {
        $runtimeName = Get-ContainerRuntimeName -Container $existing
        docker rm $runtimeName | Out-Null
        $existing = $null
        $existingLegacyStorageRoot = $null
    }
}

if ($null -eq $existing) {
    foreach ($legacyRoot in @($projectSettings.LegacyDataRoots)) {
        if (Copy-DirectoryContentsIfTargetEmpty -Source $legacyRoot -Target $dataRoot) {
            $migratedLegacyRoots += $legacyRoot
        }
    }
    foreach ($legacyRoot in @($projectSettings.LegacyInitdbRoots)) {
        if (Copy-DirectoryContentsIfTargetEmpty -Source $legacyRoot -Target $initdbRoot) {
            $migratedLegacyRoots += $legacyRoot
        }
    }

    Ensure-Directory -Path $dataRoot
    Ensure-Directory -Path $initdbRoot

    $runArgs = @(
        "run",
        "-d",
        "--name", [string]$projectSettings.DedicatedContainerName,
        "--restart", "unless-stopped",
        "-e", "PGDATA=/var/lib/postgresql/data/pgdata",
        "-e", "POSTGRES_DB=$effectiveDbName",
        "-e", "POSTGRES_USER=$DatabaseUser",
        "-e", "POSTGRES_PASSWORD=$DatabasePassword",
        "-p", "${effectivePort}:5432",
        "-v", "${dataRoot}:/var/lib/postgresql/data",
        "-v", "${initdbRoot}:/docker-entrypoint-initdb.d",
        "--health-cmd", "pg_isready -U $DatabaseUser -d $effectiveDbName",
        "--health-interval", "10s",
        "--health-timeout", "5s",
        "--health-retries", "5",
        "pgvector/pgvector:pg16"
    )

    & docker @runArgs | Out-Null
    $existing = Get-ContainerDetails -Name ([string]$projectSettings.DedicatedContainerName)
    if ($null -eq $existing) {
        throw "Expected container '$($projectSettings.DedicatedContainerName)' was not created."
    }
}
elseif ([string]$existing.State.Status -ne "running") {
    $runtimeName = Get-ContainerRuntimeName -Container $existing
    docker start $runtimeName | Out-Null
    $existing = Get-ContainerDetails -Name $runtimeName
}

$runtimeName = Get-ContainerRuntimeName -Container $existing
Wait-ContainerHealthy -ContainerName $runtimeName

if ($existingLegacyStorageRoot) {
    Write-Warning "Container '$runtimeName' is still using legacy storage under '$existingLegacyStorageRoot'. Stop and rerun this script to migrate it to '$dataRoot'."
}

$effectiveDbName = Get-ContainerEnvValue -Container $existing -Name "POSTGRES_DB" -DefaultValue $effectiveDbName
$effectiveDbUser = Get-ContainerEnvValue -Container $existing -Name "POSTGRES_USER" -DefaultValue $DatabaseUser
$effectiveDbPassword = Get-ContainerEnvValue -Container $existing -Name "POSTGRES_PASSWORD" -DefaultValue $DatabasePassword
$effectivePort = Get-ContainerHostPort -Container $existing -DefaultPort $effectivePort
$dbCloud = "postgresql://${effectiveDbUser}:${effectiveDbPassword}@127.0.0.1:${effectivePort}/${effectiveDbName}"

if (-not $SkipSchemaUpdate) {
    $previousDbOption = $env:DB_OPTION
    $previousDbCloud = $env:DB_CLOUD
    try {
        $env:DB_OPTION = "postgres"
        $env:DB_CLOUD = $dbCloud
        & $python @($projectSettings.SchemaCommand)
        if ($LASTEXITCODE -ne 0) {
            throw "Schema update failed."
        }
    }
    finally {
        Restore-EnvVar -Name "DB_OPTION" -PreviousValue $previousDbOption
        Restore-EnvVar -Name "DB_CLOUD" -PreviousValue $previousDbCloud
    }
}

Write-Output "Project: $ProjectName"
Write-Output "PostgreSQL container: $runtimeName"
Write-Output "Status: healthy"
Write-Output "Host: 127.0.0.1"
Write-Output "Port: $effectivePort"
Write-Output "Database: $effectiveDbName"
Write-Output "User: $effectiveDbUser"
Write-Output "Persistent storage: $dataRoot"
Write-Output "Init SQL: $initdbRoot"
Write-Output "Connection string: $dbCloud"
foreach ($legacyRoot in $migratedLegacyRoots) {
    Write-Output "Legacy data copied from: $legacyRoot"
}
