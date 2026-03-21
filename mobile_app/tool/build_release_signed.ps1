[CmdletBinding()]
param(
    [string]$KeystorePath = "mobile_app/release.keystore",
    [string]$KeystorePassword,
    [string]$KeyAlias = "release",
    [string]$KeyPassword,
    [string]$ApiBaseUrl = "",
    [switch]$BuildAppBundle
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($KeystorePassword)) {
    throw "KeystorePassword is required."
}

if ([string]::IsNullOrWhiteSpace($KeyPassword)) {
    $KeyPassword = $KeystorePassword
}

$resolvedKeystorePath = (Resolve-Path -Path $KeystorePath).Path
$mobileAppDirectory = Join-Path -Path (Get-Location) -ChildPath "mobile_app"

$env:ORG_GRADLE_PROJECT_aijReleaseKeystorePath = $resolvedKeystorePath
$env:ORG_GRADLE_PROJECT_aijReleaseKeystorePassword = $KeystorePassword
$env:ORG_GRADLE_PROJECT_aijReleaseKeyAlias = $KeyAlias
$env:ORG_GRADLE_PROJECT_aijReleaseKeyPassword = $KeyPassword

$buildTarget = if ($BuildAppBundle) { "appbundle" } else { "apk" }
$arguments = @("build", $buildTarget, "--release")
if (-not [string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
    $arguments += "--dart-define=AIJ_API_BASE_URL=$ApiBaseUrl"
}

Push-Location $mobileAppDirectory
try {
    & flutter @arguments
} finally {
    Pop-Location
}
