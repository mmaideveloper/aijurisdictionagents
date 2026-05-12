param(
    [switch]$SkipLint,
    [switch]$SkipTypeCheck
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "api\aijuristiction-api"
$PythonCandidates = @(
    (Join-Path $RepoRoot "conda\python.exe"),
    (Join-Path $RepoRoot ".conda\python.exe")
)

$Python = $null
foreach ($Candidate in $PythonCandidates) {
    if (Test-Path $Candidate) {
        $Python = (Resolve-Path $Candidate).Path
        break
    }
}
if (-not $Python) {
    $Python = "python"
}

Push-Location $ApiRoot
try {
    if (-not $SkipLint) {
        & $Python -m ruff check app tests
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    if (-not $SkipTypeCheck) {
        & $Python -m mypy app
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}
finally {
    Pop-Location
}
