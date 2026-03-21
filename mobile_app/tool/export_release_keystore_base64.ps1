[CmdletBinding()]
param(
    [string]$KeystorePath = "mobile_app/release.keystore",
    [string]$OutputPath = "mobile_app/release.keystore.base64.txt"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedKeystorePath = (Resolve-Path -Path $KeystorePath).Path
$resolvedOutputPath = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path -Path (Get-Location) -ChildPath $OutputPath
}

$outputDirectory = Split-Path -Path $resolvedOutputPath -Parent
if (-not [string]::IsNullOrWhiteSpace($outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$bytes = [System.IO.File]::ReadAllBytes($resolvedKeystorePath)
$base64 = [System.Convert]::ToBase64String($bytes)
[System.IO.File]::WriteAllText($resolvedOutputPath, $base64, [System.Text.Encoding]::ASCII)

Write-Host "Base64 keystore written to $resolvedOutputPath"
