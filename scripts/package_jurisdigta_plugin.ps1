param(
    [string]$OutputDirectory = "dist/plugin-release"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PluginRoot = Join-Path $RepoRoot "plugins/jurisdigta"
$ManifestPath = Join-Path $PluginRoot ".codex-plugin/plugin.json"
$MarketplacePath = Join-Path $RepoRoot ".agents/plugins/marketplace.json"

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Plugin manifest not found: $ManifestPath"
}
if (-not (Test-Path -LiteralPath $MarketplacePath)) {
    throw "Repository marketplace not found: $MarketplacePath"
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.name -ne "jurisdigta") {
    throw "Expected plugin name 'jurisdigta', found '$($Manifest.name)'."
}
if ($Manifest.version -notmatch "^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$") {
    throw "Plugin version must be release-safe semantic version without build metadata: '$($Manifest.version)'."
}

$Marketplace = Get-Content -LiteralPath $MarketplacePath -Raw | ConvertFrom-Json
$MarketplaceEntry = @($Marketplace.plugins | Where-Object { $_.name -eq "jurisdigta" })
if ($Marketplace.name -ne "jurisdigta" -or $MarketplaceEntry.Count -ne 1) {
    throw "Marketplace must be named 'jurisdigta' and contain exactly one Jurisdigta plugin entry."
}
if ($MarketplaceEntry[0].source.path -ne "./plugins/jurisdigta") {
    throw "Marketplace source must point to ./plugins/jurisdigta."
}

$SkillFiles = @(Get-ChildItem -LiteralPath (Join-Path $PluginRoot "skills") -Filter "SKILL.md" -File -Recurse)
if ($SkillFiles.Count -eq 0) {
    throw "No plugin skills were found."
}
foreach ($SkillFile in $SkillFiles) {
    $SkillText = Get-Content -LiteralPath $SkillFile.FullName -Raw
    if ($SkillText -notmatch "(?s)^---\r?\nname:\s*[a-z0-9-]+\r?\ndescription:\s*.+?\r?\n---") {
        throw "Invalid skill frontmatter: $($SkillFile.FullName)"
    }
    if ($SkillText.Contains("[TODO:")) {
        throw "Unresolved TODO placeholder: $($SkillFile.FullName)"
    }
}

$ResolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath(
    (Join-Path $RepoRoot $OutputDirectory)
)
if (-not (Test-Path -LiteralPath $ResolvedOutput)) {
    New-Item -ItemType Directory -Path $ResolvedOutput -Force | Out-Null
}

$Version = [string]$Manifest.version
$BundleName = "jurisdigta-plugin-$Version"
$BundleRoot = Join-Path $ResolvedOutput $BundleName
$ArchivePath = Join-Path $ResolvedOutput "$BundleName.zip"
$ChecksumPath = "$ArchivePath.sha256"

foreach ($Target in @($BundleRoot, $ArchivePath, $ChecksumPath)) {
    if (Test-Path -LiteralPath $Target) {
        throw "Refusing to overwrite existing release output: $Target"
    }
}

New-Item -ItemType Directory -Path (Join-Path $BundleRoot "plugins") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BundleRoot ".agents/plugins") -Force | Out-Null
Copy-Item -LiteralPath $PluginRoot -Destination (Join-Path $BundleRoot "plugins/jurisdigta") -Recurse
Copy-Item -LiteralPath $MarketplacePath -Destination (Join-Path $BundleRoot ".agents/plugins/marketplace.json")

Compress-Archive -LiteralPath $BundleRoot -DestinationPath $ArchivePath -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$ArchiveName = Split-Path -Leaf $ArchivePath
Set-Content -LiteralPath $ChecksumPath -Value "$Hash  $ArchiveName" -Encoding ascii

if ($env:GITHUB_OUTPUT) {
    $ArchiveOutput = [System.IO.Path]::GetRelativePath($RepoRoot, $ArchivePath).Replace("\", "/")
    $ChecksumOutput = [System.IO.Path]::GetRelativePath($RepoRoot, $ChecksumPath).Replace("\", "/")
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "version=$Version"
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "tag=jurisdigta-plugin-v$Version"
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "archive=$ArchiveOutput"
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "checksum=$ChecksumOutput"
}

Write-Output "Plugin version: $Version"
Write-Output "Skills validated: $($SkillFiles.Count)"
Write-Output "Archive: $ArchivePath"
Write-Output "Checksum: $ChecksumPath"
