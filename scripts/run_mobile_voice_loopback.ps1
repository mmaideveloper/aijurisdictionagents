param(
    [int]$TurnCount = 10,
    [string]$ApiBaseUrl = "http://127.0.0.1:8080",
    [string]$MobileUrl = "http://127.0.0.1:7357",
    [switch]$SkipStart,
    [switch]$IncludeAzure,
    [switch]$RequireAzure,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$artifactDir = Join-Path $repoRoot "runs\voice-simulator-tests"
$mobileDir = Join-Path $repoRoot "mobile_app"

function Test-UrlReady {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Get-DotEnvValue {
    param([string]$Name)

    $current = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        return $current
    }

    $envPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path $envPath)) {
        return $null
    }

    $line = Get-Content $envPath | Where-Object {
        $_.Trim() -match "^$([Regex]::Escape($Name))\s*="
    } | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

function Test-AzureSpeechConfigured {
    $key = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_KEY"
    $region = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_REGION"
    $ttsEndpoint = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_TTS_ENDPOINT"
    $sttEndpoint = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_STT_ENDPOINT"
    $hasTts = (-not [string]::IsNullOrWhiteSpace($key)) -and (
        -not [string]::IsNullOrWhiteSpace($region) -or
        -not [string]::IsNullOrWhiteSpace($ttsEndpoint)
    )
    $hasStt = (-not [string]::IsNullOrWhiteSpace($key)) -and (
        -not [string]::IsNullOrWhiteSpace($region) -or
        -not [string]::IsNullOrWhiteSpace($sttEndpoint)
    )
    return ($hasTts -and $hasStt)
}

function Write-AzureSkippedArtifact {
    param([string[]]$Missing)

    if (-not (Test-Path $artifactDir)) {
        New-Item -Path $artifactDir -ItemType Directory | Out-Null
    }
    $payload = [ordered]@{
        schema_version = 1
        runtime_mode = "azure"
        status = "skipped"
        reason = "Azure Speech settings are missing."
        missing_settings = $Missing
        raw_audio_persisted = $false
        created_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $payload |
        ConvertTo-Json -Depth 5 |
        Out-File -FilePath (Join-Path $artifactDir "voice-loopback-azure-skipped.json") -Encoding utf8
}

function Get-MissingAzureSpeechSettings {
    $missing = @()
    $key = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_KEY"
    $region = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_REGION"
    $ttsEndpoint = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_TTS_ENDPOINT"
    $sttEndpoint = Get-DotEnvValue -Name "AIJ_AZURE_SPEECH_STT_ENDPOINT"
    if ([string]::IsNullOrWhiteSpace($key)) {
        $missing += "AIJ_AZURE_SPEECH_KEY"
    }
    if ([string]::IsNullOrWhiteSpace($region) -and [string]::IsNullOrWhiteSpace($ttsEndpoint)) {
        $missing += "AIJ_AZURE_SPEECH_REGION or AIJ_AZURE_SPEECH_TTS_ENDPOINT"
    }
    if ([string]::IsNullOrWhiteSpace($region) -and [string]::IsNullOrWhiteSpace($sttEndpoint)) {
        $missing += "AIJ_AZURE_SPEECH_REGION or AIJ_AZURE_SPEECH_STT_ENDPOINT"
    }
    return $missing
}

function Resolve-Flutter {
    $preferred = Join-Path $env:USERPROFILE "develop\flutter\bin\flutter.bat"
    if (Test-Path $preferred) {
        return $preferred
    }
    $cmd = Get-Command flutter -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    throw "Flutter executable not found."
}

function Invoke-LoopbackTest {
    param(
        [string]$Runtime,
        [string]$FlutterPath
    )

    $env:AIJ_VOICE_LOOPBACK_ARTIFACT_DIR = $artifactDir
    Push-Location $mobileDir
    try {
        & $FlutterPath test test/voice_loopback_simulator_test.dart `
            --dart-define=AIJ_VOICE_LOOPBACK_RUNTIME=$Runtime `
            --dart-define=AIJ_VOICE_LOOPBACK_TURN_COUNT=$TurnCount
        if ($LASTEXITCODE -ne 0) {
            throw "Flutter voice loopback test failed for runtime '$Runtime'."
        }
    } finally {
        Pop-Location
        Remove-Item Env:\AIJ_VOICE_LOOPBACK_ARTIFACT_DIR -ErrorAction SilentlyContinue
    }
}

if ($TurnCount -ne 10) {
    throw "This recurring regression test is defined for exactly 10 question/answer pairs. Received: $TurnCount"
}

if (-not (Test-Path $artifactDir)) {
    New-Item -Path $artifactDir -ItemType Directory | Out-Null
}

if (-not $SkipStart) {
    if (-not (Test-UrlReady -Url "$ApiBaseUrl/health")) {
        & (Join-Path $repoRoot "skills\juris-api\scripts\start_juris_api.ps1") -Background -SkipLogTail
    }

    if (-not (Test-UrlReady -Url $MobileUrl)) {
        $mobileArgs = @(
            "-Background",
            "-ApiMode", "localApi",
            "-DatabaseOption", "postgres",
            "-StorageOption", "local",
            "-DbCloud", "postgresql://postgres:postgres@localhost:5432/aijurisdiction"
        )
        if ($NoOpen) {
            $mobileArgs += "-NoOpen"
        }
        & (Join-Path $repoRoot "skills\start-mobile-app\scripts\start_mobile_app.ps1") @mobileArgs
    }
}

$health = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -TimeoutSec 10
if ($health.status -ne "ok") {
    throw "API health is not ok."
}
if ($health.database.backend -ne "postgres") {
    throw "API is not using local PostgreSQL. Backend: $($health.database.backend)"
}
if ($health.llm.provider -ne "azurefoundry") {
    throw "API is not using azurefoundry. Provider: $($health.llm.provider)"
}
if (-not (Test-UrlReady -Url $MobileUrl)) {
    throw "Mobile app is not reachable at $MobileUrl."
}

$flutter = Resolve-Flutter
Invoke-LoopbackTest -Runtime "local-device" -FlutterPath $flutter

if ($IncludeAzure -or $RequireAzure) {
    if (Test-AzureSpeechConfigured) {
        Invoke-LoopbackTest -Runtime "azure" -FlutterPath $flutter
    } else {
        $missing = @(Get-MissingAzureSpeechSettings)
        Write-AzureSkippedArtifact -Missing $missing
        $message = "Azure Speech loopback test skipped. Missing settings: $($missing -join ', ')"
        if ($RequireAzure) {
            throw $message
        }
        Write-Warning $message
    }
}

Write-Output "Mobile voice loopback test completed."
Write-Output "API: $ApiBaseUrl"
Write-Output "Mobile: $MobileUrl"
Write-Output "Artifacts: $artifactDir"
