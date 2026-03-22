param(
    [Parameter(Mandatory = $true)]
    [string]$WindowTitle,
    [string[]]$Paths,
    [string]$PathsJoined,
    [int]$TailLines = 40
)

$ErrorActionPreference = "Stop"

$resolvedPaths = @()
if ($Paths) {
    $resolvedPaths += $Paths
}
if ($PathsJoined) {
    $resolvedPaths += ($PathsJoined -split '\|')
}

$existing = @($resolvedPaths | Where-Object { Test-Path $_ })
if (-not $existing) {
    Write-Host "No log files found to tail."
    exit 0
}

$Host.UI.RawUI.WindowTitle = $WindowTitle
Write-Host "Tailing logs:"
$existing | ForEach-Object { Write-Host "  $_" }
Get-Content -Path $existing -Wait -Tail $TailLines
