param(
    [string]$DemoRoot = "runs\new-task-worktree-bootstrap-demo"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$demoRootPath = Join-Path $repoRoot $DemoRoot
$demoWorktreePath = Join-Path $demoRootPath "aijurisdictionagents"
$demoSeedPath = Join-Path $demoRootPath "shared\aijurisdictionagents.env"

New-Item -ItemType Directory -Force -Path $demoWorktreePath | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $demoSeedPath) | Out-Null

$demoEnvPath = Join-Path $demoWorktreePath ".env"
if (Test-Path $demoEnvPath) {
    Remove-Item -LiteralPath $demoEnvPath -Force
}
if (Test-Path $demoSeedPath) {
    Remove-Item -LiteralPath $demoSeedPath -Force
}

Copy-Item `
    -Path (Join-Path $repoRoot ".env.example") `
    -Destination (Join-Path $demoWorktreePath ".env.example") `
    -Force

@"
DB_OPTION=local
STORE_OPTION=local
"@ | Set-Content -Path $demoSeedPath -Encoding utf8

& (Join-Path $repoRoot "scripts\new_task_worktree.ps1") `
    -Branch codex/demo-new-task-worktree-bootstrap `
    -WorktreePath $demoWorktreePath `
    -SetupEnvOnly `
    -SkipEnvCreate `
    -EnvSeedPath $demoSeedPath `
    -SharedEnvSeedPath $demoSeedPath

Write-Host "Demo worktree env: $demoEnvPath"
