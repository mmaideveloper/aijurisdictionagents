param(
    [ValidateSet("baseline", "delta")]
    [string]$Fixture = "baseline",
    [int]$PollSeconds = 30,
    [int]$MaxCycles = 1
)

$ErrorActionPreference = "Stop"

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

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$python = Resolve-PythonPath -RepoRoot $repoRoot

$env:PYTHONPATH = Join-Path $repoRoot "src"
$env:LAWS_COUNTRY = "SK"
$env:LAWS_DB_BACKEND = "sqlite"
$env:LAWS_DB_LOCAL = "./databases/laws-collector/sk_laws.sqlite3"
$env:LAWS_WORKER_FIXTURE = $Fixture
$env:LAWS_WORKER_POLL_SECONDS = "$PollSeconds"
$env:LAWS_WORKER_MAX_CYCLES = "$MaxCycles"

Push-Location $repoRoot
try {
    & $python -c "from services.laws_collector.worker import run_worker; run_worker()"
}
finally {
    Pop-Location
}
