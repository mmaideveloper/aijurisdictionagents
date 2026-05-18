[CmdletBinding()]
param(
    [string[]]$AutomationId = @(),
    [string]$CodexHome = $env:CODEX_HOME,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceRoot = Join-Path $repoRoot ".codex\automations"

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    $CodexHome = Join-Path $HOME ".codex"
}

$targetRoot = Join-Path $CodexHome "automations"

function ConvertTo-TomlBasicStringContent {
    param([Parameter(Mandatory = $true)][string]$Value)

    return $Value.Replace('\', '\\').Replace('"', '\"')
}

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    throw "Automation source directory not found: $sourceRoot"
}

$repoRootForToml = ConvertTo-TomlBasicStringContent -Value $repoRoot
$wanted = @{}
foreach ($id in $AutomationId) {
    if (-not [string]::IsNullOrWhiteSpace($id)) {
        $wanted[$id] = $true
    }
}

$synced = 0
$sourceFiles = Get-ChildItem -LiteralPath $sourceRoot -Directory |
    ForEach-Object { Join-Path $_.FullName "automation.toml" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Sort-Object

foreach ($sourceFile in $sourceFiles) {
    $content = Get-Content -LiteralPath $sourceFile -Raw
    $idMatch = [regex]::Match($content, '(?m)^id\s*=\s*"([^"]+)"')
    if (-not $idMatch.Success) {
        throw "Automation file is missing an id field: $sourceFile"
    }

    $id = $idMatch.Groups[1].Value
    if ($wanted.Count -gt 0 -and -not $wanted.ContainsKey($id)) {
        continue
    }

    $rendered = $content.Replace("__REPO_ROOT__", $repoRootForToml)
    if ($rendered.Contains("__REPO_ROOT__")) {
        throw "Failed to replace __REPO_ROOT__ in automation: $id"
    }

    $targetDir = Join-Path $targetRoot $id
    $targetFile = Join-Path $targetDir "automation.toml"

    if ($DryRun) {
        Write-Host "Would sync $id -> $targetFile"
    } else {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($targetFile, $rendered, $utf8NoBom)
        Write-Host "Synced $id -> $targetFile"
    }

    $synced += 1
}

if ($synced -eq 0) {
    if ($wanted.Count -gt 0) {
        throw "No matching automations found for: $($AutomationId -join ', ')"
    }

    throw "No automation.toml files found under: $sourceRoot"
}

if ($DryRun) {
    Write-Host "Dry run complete. $synced automation(s) selected."
} else {
    Write-Host "Sync complete. $synced automation(s) installed or refreshed."
}
