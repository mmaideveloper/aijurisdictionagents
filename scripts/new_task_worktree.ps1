param(
    [Parameter(Mandatory = $true)]
    [string]$Branch,

    [string]$WorktreePath,

    [string]$Base = "origin/main",

    [ValidateSet("conda", ".conda")]
    [string]$EnvDirectoryName = "conda",

    [string]$CondaExecutable,

    [string]$CloneEnvFrom,

    [string]$EnvStorageRoot = "$env:USERPROFILE\.codex-envs",

    [switch]$FreshEnv,

    [switch]$InWorktreeEnv,

    [switch]$SkipEnvCreate
)

$ErrorActionPreference = "Stop"

function Get-BranchSlug {
    param([string]$BranchName)

    $slug = $BranchName -replace "^codex/", ""
    $slug = $slug -replace "[^A-Za-z0-9._-]+", "-"
    $slug = $slug.Trim("-")
    if (-not $slug) {
        return "task-worktree"
    }
    return $slug
}

function Resolve-DefaultWorktreePath {
    param([string]$RepoRoot, [string]$BranchName)

    $slug = Get-BranchSlug -BranchName $BranchName
    $repoName = Split-Path -Leaf $RepoRoot
    $parent = Split-Path -Parent $RepoRoot
    if ((Split-Path -Leaf $parent) -eq "worktrees") {
        return Join-Path $parent $slug
    }
    return Join-Path (Join-Path $env:USERPROFILE ".codex\worktrees\$slug") $repoName
}

function Find-EnvironmentTool {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path $ExplicitPath)) {
            throw "Conda/micromamba executable was not found at '$ExplicitPath'."
        }
        $resolved = (Resolve-Path $ExplicitPath).Path
        $kind = if ((Split-Path -Leaf $resolved) -match "micromamba") { "micromamba" } else { "conda" }
        return [pscustomobject]@{ Kind = $kind; Path = $resolved }
    }

    foreach ($name in @("conda", "micromamba")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return [pscustomobject]@{ Kind = $name; Path = $command.Source }
        }
    }

    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:ProgramData\miniconda3\Scripts\conda.exe",
        "$env:ProgramData\anaconda3\Scripts\conda.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Mamba.Micromamba_Microsoft.Winget.Source_8wekyb3d8bbwe\micromamba.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $resolved = (Resolve-Path $candidate).Path
            $kind = if ((Split-Path -Leaf $resolved) -match "micromamba") { "micromamba" } else { "conda" }
            return [pscustomobject]@{ Kind = $kind; Path = $resolved }
        }
    }

    throw "Conda or micromamba was not found. Install one or pass -CondaExecutable."
}

function Find-CloneSourceEnv {
    param([string]$RepoRoot)

    $candidates = @(
        (Join-Path $RepoRoot "conda"),
        (Join-Path $RepoRoot ".conda"),
        "$env:USERPROFILE\Projects\aijurisdictionagents\conda",
        "$env:USERPROFILE\Projects\aijurisdictionagents\.conda",
        "C:\projects\aijurisdictionagents\conda",
        "C:\projects\aijurisdictionagents\.conda"
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path (Join-Path $candidate "python.exe")) -and (Test-Path (Join-Path $candidate "Lib\site-packages"))) {
            return (Resolve-Path $candidate).Path
        }
    }
    return ""
}

function Invoke-EnvironmentTool {
    param(
        [pscustomobject]$Tool,
        [string[]]$Arguments
    )

    $effectiveArguments = @()
    if ($Tool.Kind -eq "micromamba") {
        $effectiveArguments += "--ssl-no-revoke"
    }
    $effectiveArguments += $Arguments
    & $Tool.Path @effectiveArguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function New-DirectoryJunction {
    param([string]$LinkPath, [string]$TargetPath)

    if (Test-Path $LinkPath) {
        $existing = Get-Item -LiteralPath $LinkPath -Force
        if ($existing.LinkType -eq "Junction" -or $existing.Attributes.ToString().Contains("ReparsePoint")) {
            Remove-Item -LiteralPath $LinkPath -Force
        }
        else {
            throw "Cannot create junction because '$LinkPath' already exists and is not a junction."
        }
    }
    $parent = Split-Path -Parent $LinkPath
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    cmd /c mklink /J "$LinkPath" "$TargetPath" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Refresh-EditableInstalls {
    param([string]$PythonPath, [string]$WorktreeRoot)

    & $PythonPath -m pip install -e $WorktreeRoot --no-deps
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $PythonPath -m pip install -e (Join-Path $WorktreeRoot "api\aijuristiction-api") --no-deps
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BranchSlug = Get-BranchSlug -BranchName $Branch
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

$Tool = Find-EnvironmentTool -ExplicitPath $CondaExecutable
$LocalEnvPath = Join-Path $WorktreePath $EnvDirectoryName
$UseExternalEnv = (-not $InWorktreeEnv) -and ($WorktreePath -like "*\.codex\worktrees\*")
if ($UseExternalEnv) {
    $ActualEnvPath = Join-Path $EnvStorageRoot "$BranchSlug-$EnvDirectoryName"
}
else {
    $ActualEnvPath = $LocalEnvPath
}
$ActualEnvPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ActualEnvPath)
$PythonPath = Join-Path $LocalEnvPath "python.exe"
$ActualPythonPath = Join-Path $ActualEnvPath "python.exe"

if (Test-Path $PythonPath) {
    Write-Host "Conda environment already exists at $LocalEnvPath."
}
else {
    if (Test-Path $ActualEnvPath) {
        Remove-Item -LiteralPath $ActualEnvPath -Recurse -Force
    }
    $actualParent = Split-Path -Parent $ActualEnvPath
    if (-not (Test-Path $actualParent)) {
        New-Item -ItemType Directory -Force -Path $actualParent | Out-Null
    }

    $ResolvedCloneSource = ""
    if ($CloneEnvFrom) {
        $ResolvedCloneSource = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($CloneEnvFrom)
        if (-not (Test-Path (Join-Path $ResolvedCloneSource "python.exe"))) {
            throw "Clone source '$ResolvedCloneSource' does not look like a conda prefix with python.exe."
        }
    }
    elseif (-not $FreshEnv) {
        $ResolvedCloneSource = Find-CloneSourceEnv -RepoRoot $RepoRoot
    }

    if ($ResolvedCloneSource) {
        Write-Host "Cloning conda environment from $ResolvedCloneSource."
        Invoke-EnvironmentTool -Tool $Tool -Arguments @("create", "--prefix", $ActualEnvPath, "--clone", $ResolvedCloneSource, "-y")
    }
    else {
        Write-Host "Creating fresh conda environment from environment.yml."
        if ($Tool.Kind -eq "micromamba") {
            Invoke-EnvironmentTool -Tool $Tool -Arguments @("env", "create", "--prefix", $ActualEnvPath, "--file", $EnvironmentFile)
        }
        else {
            Invoke-EnvironmentTool -Tool $Tool -Arguments @("env", "create", "--prefix", $ActualEnvPath, "--file", $EnvironmentFile)
        }
    }

    if (-not (Test-Path $ActualPythonPath)) {
        throw "Environment creation finished, but python.exe was not found at $ActualPythonPath."
    }

    if ($UseExternalEnv) {
        New-DirectoryJunction -LinkPath $LocalEnvPath -TargetPath $ActualEnvPath
    }

    Refresh-EditableInstalls -PythonPath $PythonPath -WorktreeRoot $WorktreePath
}

if (-not (Test-Path $PythonPath)) {
    throw "Conda environment setup finished, but python.exe was not found at $PythonPath."
}

Write-Host "Created worktree at $WorktreePath."
if ($UseExternalEnv) {
    Write-Host "Conda environment stored at $ActualEnvPath and linked as $LocalEnvPath."
}
else {
    Write-Host "Conda environment ready at $LocalEnvPath."
}
Write-Host "Python: $PythonPath"
Write-Host "Validate API with: .\scripts\validate_api.ps1"
