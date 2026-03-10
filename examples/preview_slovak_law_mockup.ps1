param()

$mockupPath = Join-Path $PSScriptRoot "..\docs\mockups\slovak-law-corpus-dashboard.html"
$resolvedPath = Resolve-Path $mockupPath -ErrorAction Stop

Write-Host "Opening mockup:" $resolvedPath.Path
Start-Process $resolvedPath.Path
