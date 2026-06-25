param(
    [Parameter(Mandatory = $true)]
    [string]$Branch,

    [string]$WorktreePath,

    [string]$Base = "origin/main",

    [ValidateSet("conda", ".conda")]
    [string]$EnvDirectoryName = "conda",

    [string]$CondaExecutable,

    [string]$CloneEnvFrom,

    [switch]$SkipEnvCreate
)

$ErrorActionPreference = "Stop"

function Find-CondaExecutable {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path $ExplicitPath)) {
            throw "Conda executable was not found at '$ExplicitPath'."
        }
        return (Resolve-Path $ExplicitPath).Path
    }

    $command = Get-Command conda -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:ProgramData\miniconda3\Scripts\conda.exe",
        "$env:ProgramData\anaconda3\Scripts\conda.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Conda was not found. Install Miniconda/Anaconda or pass -CondaExecutable."
}

function Resolve-DefaultWorktreePath {
    param([string]$RepoRoot, [string]$BranchName)

    $slug = $BranchName -replace "^codex/", ""
    $slug = $slug -replace "[^A-Za-z0-9._-]+", "-"
    $slug = $slug.Trim("-")
    if (-not $slug) {
        $slug = "task-worktree"
    }

    $repoName = Split-Path -Leaf $RepoRoot
    $parent = Split-Path -Parent $RepoRoot
    if ((Split-Path -Leaf $parent) -eq "worktrees") {
        return Join-Path $parent $slug
    }
    return Join-Path (Join-Path $env:USERPROFILE ".codex\worktrees\$slug") $repoName
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $WorktreePath) {
    $WorktreePath = Resolve-DefaultWorktreePath -RepoRoot $RepoRoot -BranchName $Branch
}
$WorktreePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WorktreePath)

Push-Location $RepoRoot
try {
    git fetch origin main
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    git worktree add -b $Branch $WorktreePath $Base
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

if ($SkipEnvCreate) {
    Write-Host "Created worktree at $WorktreePath. Skipped conda environment creation."
    exit 0
}

$EnvironmentFile = Join-Path $WorktreePath "environment.yml"
if (-not (Test-Path $EnvironmentFile)) {
    throw "Cannot create conda environment because environment.yml was not found in $WorktreePath."
}

$Conda = Find-CondaExecutable -ExplicitPath $CondaExecutable
$EnvPath = Join-Path $WorktreePath $EnvDirectoryName
$PythonPath = Join-Path $EnvPath "python.exe"

if (Test-Path $PythonPath) {
    Write-Host "Conda environment already exists at $EnvPath."
}
elseif ($CloneEnvFrom) {
    $ResolvedCloneSource = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($CloneEnvFrom)
    if (-not (Test-Path (Join-Path $ResolvedCloneSource "python.exe"))) {
        throw "Clone source '$ResolvedCloneSource' does not look like a conda prefix with python.exe."
    }
    & $Conda create --prefix $EnvPath --clone $ResolvedCloneSource -y
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $PythonPath -m pip install -e "$WorktreePath[dev]" -e (Join-Path $WorktreePath "api\aijuristiction-api[dev]")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
else {
    & $Conda env create --prefix $EnvPath --file $EnvironmentFile
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not (Test-Path $PythonPath)) {
    throw "Conda environment creation finished, but python.exe was not found at $PythonPath."
}

Write-Host "Created worktree at $WorktreePath."
Write-Host "Conda environment ready at $EnvPath."
Write-Host "Python: $PythonPath"
Write-Host "Validate API with: .\scripts\validate_api.ps1"
