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

    [switch]$SetupEnvOnly,

    [switch]$RecreateEnv,

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
        if (Test-CondaPrefix -PrefixPath $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }
    return ""
}

function Test-CondaPrefix {
    param([string]$PrefixPath)

    if (-not $PrefixPath) {
        return $false
    }
    $python = Join-Path $PrefixPath "python.exe"
    if (-not (Test-Path $python)) {
        return $false
    }
    if (-not (Test-Path (Join-Path $PrefixPath "Lib\site-packages"))) {
        return $false
    }
    & $python -c "import pathlib, select, sqlite3, ssl, sys; pathlib.Path(sys.executable).resolve(); raise SystemExit(0)" 2>$null
    return $LASTEXITCODE -eq 0
}

function Remove-EnvironmentPrefix {
    param(
        [string]$PrefixPath,
        [string]$WorktreeRoot,
        [string]$StorageRoot
    )

    if (-not (Test-Path $PrefixPath)) {
        return
    }

    $resolvedPrefix = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PrefixPath)
    $resolvedWorktree = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WorktreeRoot)
    $resolvedStorage = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($StorageRoot)
    $allowedRoots = @($resolvedWorktree, $resolvedStorage) | Where-Object { $_ }
    $isAllowed = $false
    foreach ($root in $allowedRoots) {
        if ($resolvedPrefix.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
            $isAllowed = $true
            break
        }
    }
    if (-not $isAllowed) {
        throw "Refusing to remove environment prefix outside the worktree or env storage root: $resolvedPrefix"
    }

    $item = Get-Item -LiteralPath $resolvedPrefix -Force
    if ($item.LinkType -eq "Junction" -or $item.Attributes.ToString().Contains("ReparsePoint")) {
        Remove-Item -LiteralPath $resolvedPrefix -Force
    }
    else {
        Remove-Item -LiteralPath $resolvedPrefix -Recurse -Force
    }
}

function Invoke-EnvironmentTool {
    param(
        [pscustomobject]$Tool,
        [string[]]$Arguments
    )

    $effectiveArguments = $Arguments
    if ($Tool.Kind -eq "micromamba" -and $Arguments.Count -gt 0) {
        if ($Arguments[0] -eq "create") {
            $tail = @()
            if ($Arguments.Count -gt 1) {
                $tail = $Arguments[1..($Arguments.Count - 1)]
            }
            $effectiveArguments = @("create", "--ssl-no-revoke") + $tail
        }
        elseif ($Arguments.Count -gt 1 -and $Arguments[0] -eq "env" -and $Arguments[1] -eq "create") {
            $tail = @()
            if ($Arguments.Count -gt 2) {
                $tail = $Arguments[2..($Arguments.Count - 1)]
            }
            $effectiveArguments = @("env", "create", "--ssl-no-revoke") + $tail
        }
    }
    & $Tool.Path @effectiveArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Environment tool failed with exit code ${LASTEXITCODE}: $($Tool.Path) $($effectiveArguments -join ' ')"
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

    & $PythonPath -m pip install -e "$WorktreeRoot[dev]"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    $apiProject = Join-Path $WorktreeRoot "api\aijuristiction-api"
    & $PythonPath -m pip install -e "$apiProject[dev]"
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

if ($SkipEnvCreate -and $SetupEnvOnly) {
    throw "-SkipEnvCreate cannot be combined with -SetupEnvOnly."
}

if (-not $SetupEnvOnly) {
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
}
elseif (-not (Test-Path $WorktreePath)) {
    throw "Cannot set up environment because worktree path does not exist: $WorktreePath"
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
$UseExternalEnv = -not $InWorktreeEnv
if ($UseExternalEnv) {
    $ActualEnvPath = Join-Path $EnvStorageRoot "$BranchSlug-$EnvDirectoryName"
}
else {
    $ActualEnvPath = $LocalEnvPath
}
$ActualEnvPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ActualEnvPath)
$PythonPath = Join-Path $LocalEnvPath "python.exe"
$ActualPythonPath = Join-Path $ActualEnvPath "python.exe"

if ($RecreateEnv -and (Test-Path $ActualEnvPath)) {
    Write-Host "Removing existing conda environment at $ActualEnvPath because -RecreateEnv was specified."
    Remove-EnvironmentPrefix -PrefixPath $ActualEnvPath -WorktreeRoot $WorktreePath -StorageRoot $EnvStorageRoot
}

if ((Test-Path $ActualEnvPath) -and (-not (Test-CondaPrefix -PrefixPath $ActualEnvPath))) {
    Write-Host "Removing incomplete conda environment at $ActualEnvPath because python.exe validation failed."
    Remove-EnvironmentPrefix -PrefixPath $ActualEnvPath -WorktreeRoot $WorktreePath -StorageRoot $EnvStorageRoot
}

if ($UseExternalEnv -and (Test-Path $LocalEnvPath) -and (-not (Test-CondaPrefix -PrefixPath $LocalEnvPath))) {
    Write-Host "Removing incomplete local conda path at $LocalEnvPath because python.exe validation failed."
    Remove-EnvironmentPrefix -PrefixPath $LocalEnvPath -WorktreeRoot $WorktreePath -StorageRoot $EnvStorageRoot
}

if (Test-CondaPrefix -PrefixPath $LocalEnvPath) {
    Write-Host "Conda environment already exists at $LocalEnvPath."
}
elseif ($UseExternalEnv -and (Test-CondaPrefix -PrefixPath $ActualEnvPath)) {
    Refresh-EditableInstalls -PythonPath $ActualPythonPath -WorktreeRoot $WorktreePath
    New-DirectoryJunction -LinkPath $LocalEnvPath -TargetPath $ActualEnvPath
    Write-Host "Linked existing conda environment from $ActualEnvPath to $LocalEnvPath."
}
else {
    $actualParent = Split-Path -Parent $ActualEnvPath
    if (-not (Test-Path $actualParent)) {
        New-Item -ItemType Directory -Force -Path $actualParent | Out-Null
    }

    $ResolvedCloneSource = ""
    if ($CloneEnvFrom) {
        $ResolvedCloneSource = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($CloneEnvFrom)
        if (-not (Test-CondaPrefix -PrefixPath $ResolvedCloneSource)) {
            throw "Clone source '$ResolvedCloneSource' does not look like a conda prefix with python.exe."
        }
    }
    elseif (-not $FreshEnv) {
        $ResolvedCloneSource = Find-CloneSourceEnv -RepoRoot $RepoRoot
    }

    try {
        if ($ResolvedCloneSource -and $Tool.Kind -ne "micromamba") {
            Write-Host "Cloning conda environment from $ResolvedCloneSource."
            Invoke-EnvironmentTool -Tool $Tool -Arguments @("create", "--prefix", $ActualEnvPath, "--clone", $ResolvedCloneSource, "-y")
        }
        else {
            if ($ResolvedCloneSource -and $Tool.Kind -eq "micromamba") {
                Write-Host "Micromamba does not reliably clone pip-heavy prefixes; creating from environment.yml instead."
            }
            Write-Host "Creating fresh conda environment from environment.yml."
            Invoke-EnvironmentTool -Tool $Tool -Arguments @("env", "create", "--prefix", $ActualEnvPath, "--file", $EnvironmentFile)
        }
    }
    catch {
        if (Test-Path $ActualEnvPath) {
            Remove-EnvironmentPrefix -PrefixPath $ActualEnvPath -WorktreeRoot $WorktreePath -StorageRoot $EnvStorageRoot
        }
        throw
    }

    if (-not (Test-CondaPrefix -PrefixPath $ActualEnvPath)) {
        if (Test-Path $ActualEnvPath) {
            Remove-EnvironmentPrefix -PrefixPath $ActualEnvPath -WorktreeRoot $WorktreePath -StorageRoot $EnvStorageRoot
        }
        throw "Environment creation finished, but python.exe was not found at $ActualPythonPath."
    }

    Refresh-EditableInstalls -PythonPath $ActualPythonPath -WorktreeRoot $WorktreePath

    if ($UseExternalEnv) {
        New-DirectoryJunction -LinkPath $LocalEnvPath -TargetPath $ActualEnvPath
    }
}

if (-not (Test-CondaPrefix -PrefixPath $LocalEnvPath)) {
    throw "Conda environment setup finished, but python.exe was not found at $PythonPath."
}

if ($SetupEnvOnly) {
    Write-Host "Prepared conda environment for existing worktree at $WorktreePath."
}
else {
    Write-Host "Created worktree at $WorktreePath."
}
if ($UseExternalEnv) {
    Write-Host "Conda environment stored at $ActualEnvPath and linked as $LocalEnvPath."
}
else {
    Write-Host "Conda environment ready at $LocalEnvPath."
}
Write-Host "Python: $PythonPath"
Write-Host "Validate API with: .\scripts\validate_api.ps1"
