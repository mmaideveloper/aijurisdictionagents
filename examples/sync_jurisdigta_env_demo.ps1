param(
    [string]$EnvExamplePath = ".env.example",
    [string]$EnvPath = ".env"
)

$repoRoot = Split-Path -Parent $PSScriptRoot

& (Join-Path $repoRoot "scripts\sync_jurisdigta_env.ps1") `
    -EnvExamplePath $EnvExamplePath `
    -EnvPath $EnvPath `
    -SkipSshKeySync `
    -SkipTransfer `
    -DryRun
