param(
    [int]$TurnCount = 10,
    [string]$ApiBaseUrl = "http://127.0.0.1:8080",
    [string]$MobileUrl = "http://127.0.0.1:7357",
    [switch]$SkipStart,
    [switch]$IncludeAzure,
    [switch]$RequireAzure,
    [switch]$LiveDiscussion,
    [switch]$SpeakLiveDiscussion,
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

function ConvertFrom-SseContent {
    param([string]$Content)

    $events = @()
    $blocks = $Content -split "(`r?`n){2,}"
    foreach ($block in $blocks) {
        $eventName = $null
        $dataLines = @()
        foreach ($line in ($block -split "`r?`n")) {
            $trimmed = $line.Trim()
            if ($trimmed.StartsWith("event:")) {
                $eventName = $trimmed.Substring("event:".Length).Trim()
            } elseif ($trimmed.StartsWith("data:")) {
                $dataLines += $trimmed.Substring("data:".Length).Trim()
            }
        }
        if (-not $eventName -or $dataLines.Count -eq 0) {
            continue
        }
        $dataRaw = $dataLines -join "`n"
        try {
            $data = $dataRaw | ConvertFrom-Json
        } catch {
            $data = [ordered]@{ raw = $dataRaw }
        }
        $events += [ordered]@{
            event = $eventName
            data = $data
        }
    }
    return $events
}

function Invoke-BlockingSpeech {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,
        [string]$Role = "unknown"
    )

    if (-not $script:SpeechSynthesizer) {
        Add-Type -AssemblyName System.Speech
        $script:SpeechSynthesizer = [System.Speech.Synthesis.SpeechSynthesizer]::new()
        $script:SpeechSynthesizer.Rate = -1
        $script:SpeechSynthesizer.Volume = 100
    }

    Write-Output "Speaking [$Role]: $Text"
    $script:SpeechSynthesizer.Speak($Text)
}

function Invoke-LiveDiscussion {
    param(
        [string]$ApiBaseUrl,
        [int]$ExpectedPairs,
        [switch]$Speak
    )

    $caseTitle = "simulacia $(Get-Random -Minimum 100000 -Maximum 999999)"
    $headers = @{
        "x-api-key" = "aijuris"
        "Content-Type" = "application/json"
    }

    $sessionPayload = @{
        country = "SK"
        language = "sk"
        discussion_type = "advice"
    } | ConvertTo-Json -Depth 5
    $session = Invoke-RestMethod `
        -Uri "$ApiBaseUrl/v1/chat/sessions" `
        -Method Post `
        -Headers $headers `
        -Body $sessionPayload `
        -TimeoutSec 30

    $instruction = "Vytvor novy pripad s nazvom $caseTitle. Spusti hlasovu simulaciu. Pytaj sa kratke otazky a odpovedaj ako AI Simulator Agent, kym vznikne 10 otazok a 10 odpovedi."
    $streamPayload = @{
        instruction = $instruction
        question_timeout_seconds = 1
        max_discussion_minutes = 6
        communication_minutes = 6
        user_simulation_mode = "AIUserSimulatorAgent"
        documents = @()
    } | ConvertTo-Json -Depth 8

    $streamResponse = Invoke-WebRequest `
        -Uri "$ApiBaseUrl/v1/chat/sessions/$($session.id)/stream" `
        -Method Post `
        -Headers $headers `
        -Body $streamPayload `
        -TimeoutSec 420 `
        -UseBasicParsing

    $events = @(ConvertFrom-SseContent -Content $streamResponse.Content)
    $messages = @(
        $events |
            Where-Object { $_.event -eq "message" -and $_.data.content } |
            ForEach-Object {
                [ordered]@{
                    role = [string]$_.data.role
                    content = [string]$_.data.content
                    received_at_utc = [DateTime]::UtcNow.ToString("o")
                }
            }
    )

    $systemTurns = @($messages | Where-Object { $_.role -ne "user" })
    $simulatorTurns = @($messages | Where-Object { $_.role -eq "user" })
    $pairCount = [Math]::Min($systemTurns.Count, $simulatorTurns.Count)
    $spoken = @()

    foreach ($message in $messages) {
        if ($spoken.Count -ge ($ExpectedPairs * 2)) {
            break
        }
        $text = $message.content.Trim()
        if ([string]::IsNullOrWhiteSpace($text)) {
            continue
        }

        $speechStarted = [DateTime]::UtcNow
        if ($Speak) {
            Invoke-BlockingSpeech -Text $text -Role $message.role
        }
        $speechCompleted = [DateTime]::UtcNow
        $spoken += [ordered]@{
            role = $message.role
            text = $text
            text_length = $text.Length
            speech_started_at_utc = $speechStarted.ToString("o")
            speech_completed_at_utc = $speechCompleted.ToString("o")
            interrupted = $false
            speak_mode = if ($Speak) { "windows-sapi-blocking" } else { "artifact-only" }
        }
    }

    $passed = ($pairCount -ge $ExpectedPairs) -and ($spoken.Count -ge ($ExpectedPairs * 2))
    $artifact = [ordered]@{
        schema_version = 1
        mode = "live-ai-simulator-discussion"
        case_title = $caseTitle
        session_id = $session.id
        api_base_url = $ApiBaseUrl
        expected_question_answer_pairs = $ExpectedPairs
        observed_question_answer_pairs = $pairCount
        stream_message_count = $messages.Count
        spoken_turn_count = $spoken.Count
        passed = $passed
        raw_audio_persisted = $false
        speech_output = if ($Speak) { "spoken" } else { "not-spoken" }
        interruption_policy = "blocking sequential speech; next turn is not spoken until current Speak() returns"
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        messages = $messages
        spoken_turns = $spoken
    }
    $artifactPath = Join-Path $artifactDir "voice-live-discussion.json"
    $artifact | ConvertTo-Json -Depth 10 | Out-File -FilePath $artifactPath -Encoding utf8

    if (-not $passed) {
        throw "Live AI Simulator discussion did not reach $ExpectedPairs question/answer pairs. Observed pairs: $pairCount. Artifact: $artifactPath"
    }

    Write-Output "Live AI Simulator discussion completed."
    Write-Output "Case title: $caseTitle"
    Write-Output "Observed pairs: $pairCount"
    Write-Output "Artifact: $artifactPath"
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

if ($LiveDiscussion) {
    Invoke-LiveDiscussion -ApiBaseUrl $ApiBaseUrl -ExpectedPairs $TurnCount -Speak:$SpeakLiveDiscussion
}

Write-Output "Mobile voice loopback test completed."
Write-Output "API: $ApiBaseUrl"
Write-Output "Mobile: $MobileUrl"
Write-Output "Artifacts: $artifactDir"
