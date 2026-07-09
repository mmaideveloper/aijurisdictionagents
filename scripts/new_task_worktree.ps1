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

    [string]$EnvExamplePath = ".env.example",

    [string]$LocalEnvFileName = ".env",

    [string]$EnvSeedPath,

    [string]$SharedEnvSeedPath = "$env:USERPROFILE\.jurisdigta\aijurisdictionagents.env",

    [string]$UnknownValue = "unknown-variable",

    [switch]$FreshEnv,

    [switch]$InWorktreeEnv,

    [switch]$SetupEnvOnly,

    [switch]$RecreateEnv,

    [switch]$SkipEnvCreate,

    [switch]$SkipEnvSync
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

function Get-EnvKeysFromExample {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Env example file not found: $Path"
    }

    $keys = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=.*$") {
            $key = $Matches[1]
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $keys.Add($key)
            }
        }
    }
    return $keys
}

function Get-EnvDefaultsFromExample {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Env example file not found: $Path"
    }

    $defaults = @{}
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $key = $Matches[1]
            if (-not $defaults.ContainsKey($key)) {
                $defaults[$key] = $Matches[2].Trim()
            }
        }
    }
    return $defaults
}

function Remove-UnsafeEnvEntries {
    param(
        [string]$Path,
        [string[]]$Keys
    )

    if (-not (Test-Path $Path)) {
        return 0
    }

    $keyLookup = @{}
    foreach ($key in $Keys) {
        $keyLookup[$key] = $true
    }

    $keptLines = [System.Collections.Generic.List[string]]::new()
    $removedCount = 0
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=" -and $keyLookup.ContainsKey($Matches[1])) {
            $removedCount++
            continue
        }
        $keptLines.Add($line)
    }

    if ($removedCount -gt 0) {
        Set-Content -Path $Path -Value $keptLines -Encoding utf8
    }
    return $removedCount
}

function Test-SafeEnvDefaultValue {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    $lowerValue = $Value.ToLowerInvariant()
    $unsafeMarkers = @(
        "unknown-variable",
        "your_",
        "your-",
        "your ",
        "changeit",
        "change-this",
        "replace-with",
        "optional_",
        "ghp_",
        "github_pat",
        "instrumentationkey=",
        "<",
        ">",
        "`$("
    )
    foreach ($marker in $unsafeMarkers) {
        if ($lowerValue.Contains($marker)) {
            return $false
        }
    }
    return $true
}

function Resolve-EnvBootstrapValue {
    param(
        [hashtable]$Defaults,
        [string]$Key,
        [string]$PlaceholderValue
    )

    if ($Defaults.ContainsKey($Key) -and (Test-SafeEnvDefaultValue -Value $Defaults[$Key])) {
        return $Defaults[$Key]
    }
    return $PlaceholderValue
}

function Repair-UnknownEnvDefaults {
    param(
        [string]$Path,
        [hashtable]$Defaults,
        [string]$PlaceholderValue
    )

    if (-not (Test-Path $Path)) {
        return 0
    }

    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in Get-Content -Path $Path) {
        $lines.Add($line)
    }

    $repairedCount = 0
    for ($index = 0; $index -lt $lines.Count; $index++) {
        $line = $lines[$index]
        if ($line -match "^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$") {
            $key = $Matches[2]
            $value = $Matches[4].Trim()
            if ($value -eq $PlaceholderValue -and $Defaults.ContainsKey($key) -and (Test-SafeEnvDefaultValue -Value $Defaults[$key])) {
                $lines[$index] = "$($Matches[1])$key$($Matches[3])$($Defaults[$key])"
                $repairedCount++
            }
        }
    }

    if ($repairedCount -gt 0) {
        Set-Content -Path $Path -Value $lines -Encoding utf8
    }
    return $repairedCount
}

function Get-ActiveEnvValues {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $values[$Matches[1]] = $Matches[2].Trim()
        }
    }
    return $values
}

function Protect-LocalSecretFile {
    param([string]$Path)

    if (-not (Test-Path $Path) -or -not (Get-Command icacls -ErrorAction SilentlyContinue)) {
        return
    }

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls $Path /inheritance:r /grant:r "${identity}:F" | Out-Null
    $parent = Split-Path -Parent $Path
    if ($parent -and (Test-Path $parent)) {
        & icacls $parent /inheritance:r /grant:r "${identity}:(OI)(CI)F" | Out-Null
    }
}

function Sync-WorktreeEnv {
    param(
        [string]$SourceRepoRoot,
        [string]$TargetWorktreeRoot,
        [string]$ExamplePath,
        [string]$TargetEnvName,
        [string]$ExplicitSeedPath,
        [string]$SharedSeedPath,
        [string]$PlaceholderValue
    )

    $resolvedExamplePath = $ExamplePath
    if (-not [System.IO.Path]::IsPathRooted($resolvedExamplePath)) {
        $resolvedExamplePath = Join-Path $TargetWorktreeRoot $resolvedExamplePath
    }
    $resolvedExamplePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($resolvedExamplePath)

    $targetEnvPath = $TargetEnvName
    if (-not [System.IO.Path]::IsPathRooted($targetEnvPath)) {
        $targetEnvPath = Join-Path $TargetWorktreeRoot $targetEnvPath
    }
    $targetEnvPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($targetEnvPath)

    $seedCandidates = New-Object System.Collections.Generic.List[string]
    if ($ExplicitSeedPath) {
        $seedCandidates.Add($ExplicitSeedPath)
    }
    $sourceRepoEnv = Join-Path $SourceRepoRoot ".env"
    if (Test-Path $sourceRepoEnv) {
        $seedCandidates.Add($sourceRepoEnv)
    }
    if ($SharedSeedPath) {
        $seedCandidates.Add($SharedSeedPath)
    }

    $selectedSeedPath = ""
    foreach ($candidate in $seedCandidates) {
        if (-not $candidate) {
            continue
        }
        $candidatePath = $candidate
        if (-not [System.IO.Path]::IsPathRooted($candidatePath)) {
            $candidatePath = Join-Path $SourceRepoRoot $candidatePath
        }
        if ((Test-Path $candidatePath) -and ((Resolve-Path $candidatePath).Path -ne $targetEnvPath)) {
            $selectedSeedPath = (Resolve-Path $candidatePath).Path
            break
        }
    }

    if ((-not (Test-Path $targetEnvPath)) -and $selectedSeedPath) {
        $targetParent = Split-Path -Parent $targetEnvPath
        if (-not (Test-Path $targetParent)) {
            New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
        }
        Copy-Item -Path $selectedSeedPath -Destination $targetEnvPath -Force
        Write-Host "Seeded $targetEnvPath from $selectedSeedPath."
    }
    elseif (-not (Test-Path $targetEnvPath)) {
        New-Item -ItemType File -Path $targetEnvPath -Force | Out-Null
        Write-Host "Created local env file at $targetEnvPath."
    }

    $removedUnsafeCount = Remove-UnsafeEnvEntries -Path $targetEnvPath -Keys @(
        "INTERNAL_MCP_BASE_URL",
        "LLM_PROVIDER",
        "MODEL_KNOWLEDGE_CUTOFF_DATE",
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    if ($removedUnsafeCount -gt 0) {
        Write-Host "Removed $removedUnsafeCount unsafe optional env entry/entries from $targetEnvPath."
    }

    $exampleKeys = Get-EnvKeysFromExample -Path $resolvedExamplePath
    $exampleDefaults = Get-EnvDefaultsFromExample -Path $resolvedExamplePath
    $activeValues = Get-ActiveEnvValues -Path $targetEnvPath
    $missingKeys = @($exampleKeys | Where-Object { -not $activeValues.ContainsKey($_) })

    if ($missingKeys.Count -gt 0) {
        $existingContent = Get-Content -Path $targetEnvPath -Raw
        $separator = ""
        if (-not [string]::IsNullOrEmpty($existingContent) -and -not $existingContent.EndsWith("`n")) {
            $separator = "`r`n"
        }

        $linesToAppend = New-Object System.Collections.Generic.List[string]
        $linesToAppend.Add("")
        $linesToAppend.Add("# Added from .env.example by scripts/new_task_worktree.ps1.")
        foreach ($key in $missingKeys) {
            $value = Resolve-EnvBootstrapValue -Defaults $exampleDefaults -Key $key -PlaceholderValue $PlaceholderValue
            $linesToAppend.Add("$key=$value")
        }

        Add-Content -Path $targetEnvPath -Value ($separator + ($linesToAppend -join "`r`n"))
        Write-Host "Added $($missingKeys.Count) missing key(s) to $targetEnvPath from .env.example."
    }
    else {
        Write-Host "$targetEnvPath already contains every key from .env.example."
    }

    $repairedCount = Repair-UnknownEnvDefaults -Path $targetEnvPath -Defaults $exampleDefaults -PlaceholderValue $PlaceholderValue
    if ($repairedCount -gt 0) {
        Write-Host "Replaced $repairedCount placeholder value(s) in $targetEnvPath with safe .env.example defaults."
    }

    Protect-LocalSecretFile -Path $targetEnvPath

    if ($SharedSeedPath) {
        $resolvedSharedSeedPath = $SharedSeedPath
        if (-not [System.IO.Path]::IsPathRooted($resolvedSharedSeedPath)) {
            $resolvedSharedSeedPath = Join-Path $SourceRepoRoot $resolvedSharedSeedPath
        }
        $resolvedSharedSeedPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($resolvedSharedSeedPath)
        if ($resolvedSharedSeedPath -ne $targetEnvPath) {
            $sharedParent = Split-Path -Parent $resolvedSharedSeedPath
            if (-not (Test-Path $sharedParent)) {
                New-Item -ItemType Directory -Force -Path $sharedParent | Out-Null
            }
            Copy-Item -Path $targetEnvPath -Destination $resolvedSharedSeedPath -Force
            Protect-LocalSecretFile -Path $resolvedSharedSeedPath
            Write-Host "Updated shared local env seed at $resolvedSharedSeedPath."
        }
    }

    $finalValues = Get-ActiveEnvValues -Path $targetEnvPath
    $unknownKeys = @($finalValues.Keys | Sort-Object | Where-Object { $finalValues[$_] -eq $PlaceholderValue })
    if ($unknownKeys.Count -gt 0) {
        Write-Warning ("$targetEnvPath still contains '$PlaceholderValue' for: " + ($unknownKeys -join ", "))
    }
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

if (-not $SkipEnvSync) {
    Sync-WorktreeEnv `
        -SourceRepoRoot $RepoRoot `
        -TargetWorktreeRoot $WorktreePath `
        -ExamplePath $EnvExamplePath `
        -TargetEnvName $LocalEnvFileName `
        -ExplicitSeedPath $EnvSeedPath `
        -SharedSeedPath $SharedEnvSeedPath `
        -PlaceholderValue $UnknownValue
}
else {
    Write-Host "Skipped local .env bootstrap because -SkipEnvSync was specified."
}

if ($SkipEnvCreate) {
    if ($SetupEnvOnly) {
        Write-Host "Prepared local env file for existing worktree at $WorktreePath. Skipped conda environment creation."
    }
    else {
        Write-Host "Created worktree at $WorktreePath. Skipped conda environment creation."
    }
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
