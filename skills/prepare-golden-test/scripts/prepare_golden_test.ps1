param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("prepare", "promote")]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = Join-Path $RepoRoot "conda\python.exe"
$Script = Join-Path $PSScriptRoot "prepare_golden_test.py"

if (-not (Test-Path $Python)) {
    throw "Repository conda runtime not found at $Python. Create the task worktree with scripts/new_task_worktree.ps1."
}

Push-Location $RepoRoot
try {
    & $Python $Script $Command @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
