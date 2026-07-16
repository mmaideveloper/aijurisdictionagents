param([string]$Profile = "local-core", [string]$EnvPath = ".env")

$repoRoot = Split-Path -Parent $PSScriptRoot

& (Join-Path $repoRoot "scripts\sync_env_profile.ps1") `
    -Mode Audit `
    -Profile $Profile `
    -EnvFilePath $EnvPath
