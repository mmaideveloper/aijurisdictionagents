param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8090,
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 8080,
    [switch]$Background,
    [switch]$ConsoleWindow,
    [switch]$Reload,
    [switch]$Install,
    [switch]$SkipApiBootstrap
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$delegateScript = Join-Path $repoRoot "skills\chatsimulatr\scripts\start_chat_simulator.ps1"
if (-not (Test-Path $delegateScript)) {
    throw "Delegated chat simulator launcher not found: $delegateScript"
}

$shellPath = $null
$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwshCmd) {
    $shellPath = $pwshCmd.Source
} else {
    $powershellCmd = Get-Command powershell -ErrorAction SilentlyContinue
    if ($powershellCmd) {
        $shellPath = $powershellCmd.Source
    }
}
if (-not $shellPath) {
    throw "PowerShell executable not found."
}

$args = @(
    "-NoProfile",
    "-File", $delegateScript,
    "-BindHost", $BindHost,
    "-Port", "$Port",
    "-ApiHost", $ApiHost,
    "-ApiPort", "$ApiPort"
)
if ($Background) {
    $args += "-Background"
}
if ($ConsoleWindow) {
    $args += "-ConsoleWindow"
}
if ($Reload) {
    $args += "-Reload"
}
if ($Install) {
    $args += "-Install"
}
if ($SkipApiBootstrap) {
    $args += "-SkipApiBootstrap"
}

& $shellPath @args
exit $LASTEXITCODE
