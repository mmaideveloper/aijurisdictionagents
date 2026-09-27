[CmdletBinding()]
param(
    [ValidateSet("Audit", "Bootstrap", "Pull")]
    [string]$Mode = "Audit",
    [ValidateSet("local-core", "codex-agent", "laws-collector", "azure-dev", "mcp-local", "laws-tests-dev", "laws-tests-prod")]
    [string]$Profile = "local-core",
    [string]$EnvFilePath,
    [string]$ServerAlias = "jurisdigta-server",
    [string]$UsbProfileRoot = "/mnt/jurisdigta-backup/jurisdigta-env/profiles",
    [string]$PythonPath,
    [switch]$Strict
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $EnvFilePath) {
    $EnvFilePath = if ($Profile -like "laws-tests-*") { ".env-laws-test" } elseif ($Profile -eq "azure-dev") { ".env.dev" } else { ".env" }
}
if ($Profile -eq 'laws-tests-prod' -and $Mode -eq 'Pull') {
    throw 'Production secrets stay on the production host. Use the server provisioning tool.'
}
if (-not [System.IO.Path]::IsPathRooted($EnvFilePath)) {
    $EnvFilePath = Join-Path $repoRoot $EnvFilePath
}
if (-not $PythonPath) {
    $candidate = Join-Path $repoRoot "conda\python.exe"
    $PythonPath = if (Test-Path $candidate) { $candidate } else { "python" }
}
$tool = Join-Path $repoRoot "scripts\env_config.py"

function Invoke-EnvTool {
    param([string[]]$Arguments)
    & $PythonPath $tool --env-file $EnvFilePath --profile $Profile @Arguments |
        ForEach-Object { Write-Host $_ }
    return $LASTEXITCODE
}

if ($Mode -eq "Audit") {
    $arguments = @("audit")
    if ($Strict) { $arguments += "--strict" }
    exit (Invoke-EnvTool -Arguments $arguments)
}
if ($Mode -eq "Bootstrap") {
    $code = Invoke-EnvTool -Arguments @("bootstrap")
    if ($code -ne 0) { exit $code }
    $arguments = @("audit")
    if ($Strict) { $arguments += "--strict" }
    exit (Invoke-EnvTool -Arguments $arguments)
}

if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "scp is required for server profile synchronization."
}
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jurisdigta-env-" + [guid]::NewGuid().ToString("N"))
$download = Join-Path $temporaryRoot "$Profile.env"
$backup = Join-Path $temporaryRoot "local-backup.env"
New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
try {
    if (Test-Path $EnvFilePath) { Copy-Item -LiteralPath $EnvFilePath -Destination $backup -Force }
    if ($Profile -eq 'laws-tests-dev') {
        & ssh -o BatchMode=yes -o StrictHostKeyChecking=yes $ServerAlias 'test "$(findmnt -n -o TARGET --target /mnt/jurisdigta-backup)" = "/mnt/jurisdigta-backup" && test "$(lsblk -ndo TYPE "$(findmnt -n -o SOURCE --target /mnt/jurisdigta-backup)")" = crypt'
        if ($LASTEXITCODE -ne 0) { throw 'Verified encrypted USB mount is unavailable; use strict audit of a previously verified local profile.' }
    }
    $remotePath = if ($Profile -eq 'laws-tests-dev') { "$UsbProfileRoot/laws-tests/dev/.env-laws-test" } else { "$UsbProfileRoot/$Profile.env" }
    $remote = "${ServerAlias}:$remotePath"
    & scp -q -o BatchMode=yes -o StrictHostKeyChecking=yes $remote $download
    if ($LASTEXITCODE -ne 0) { throw "Secure profile download failed for $Profile." }
    $code = Invoke-EnvTool -Arguments @("merge", "--source", $download)
    if ($code -ne 0) { throw "Downloaded profile merge failed." }
    $code = Invoke-EnvTool -Arguments @("audit", "--strict")
    if ($code -ne 0) { throw "Downloaded profile did not satisfy the selected profile." }
    Write-Host "Environment profile pull completed. Values remain redacted."
}
catch {
    if (Test-Path $backup) { Copy-Item -LiteralPath $backup -Destination $EnvFilePath -Force }
    throw
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
