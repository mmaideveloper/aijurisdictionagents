param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath
)

$ErrorActionPreference = "Stop"
$global:StartPostgresDockerCalls = @()

function global:docker {
    $global:StartPostgresDockerCalls += ,(@($args) -join "|")
    $global:LASTEXITCODE = 0
    switch ([string]$args[0]) {
        "ps" {
            Write-Output "fixture-id`taijurisdiction-postgres-local"
        }
        "inspect" {
            @{
                Name = "/aijurisdiction-postgres-local"
                State = @{ Status = "running"; Health = @{ Status = "healthy" } }
                Config = @{
                    Env = @(
                        "POSTGRES_DB=aijurisdiction",
                        "POSTGRES_USER=postgres",
                        "POSTGRES_PASSWORD=fixture-secret"
                    )
                }
                NetworkSettings = @{
                    Ports = @{ "5432/tcp" = @(@{ HostPort = "5432" }) }
                }
                Mounts = @()
            } | ConvertTo-Json -Depth 8
        }
        "exec" {
            # The database lookup intentionally returns no row so the launcher must create it.
        }
        default {
            throw "Unexpected docker invocation: $(@($args) -join ' ')"
        }
    }
}

$output = & $ScriptPath `
    -ProjectName api `
    -DatabaseName branch_specific_e2e `
    -DatabaseUser ignored_requested_user `
    -DatabasePassword ignored-requested-password `
    -DatabasePort 5999 `
    -SkipSchemaUpdate

$joined = @($output) -join "`n"
if ($joined -notmatch "Database: branch_specific_e2e") {
    throw "The explicit database name was not preserved.`n$joined"
}
if ($joined -notmatch "Port: 5432") {
    throw "The reused container host port was not preserved.`n$joined"
}
if ($joined -match "fixture-secret" -or $joined -match "ignored-requested-password") {
    throw "Launcher output exposed a database password."
}
$createCall = $global:StartPostgresDockerCalls | Where-Object {
    $_ -eq "exec|aijurisdiction-postgres-local|createdb|-U|postgres|branch_specific_e2e"
}
if (-not $createCall) {
    throw "The missing explicit database was not created. Calls: $($global:StartPostgresDockerCalls -join '; ')"
}

$unsafeNameRejected = $false
try {
    & $ScriptPath -ProjectName api -DatabaseName "unsafe-name;drop" -SkipSchemaUpdate
}
catch {
    $unsafeNameRejected = $_.Exception.Message -match "lowercase PostgreSQL identifier"
}
if (-not $unsafeNameRejected) {
    throw "An unsafe explicit database identifier was not rejected."
}

Write-Output "start_postgres reuse regression passed"
