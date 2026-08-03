param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $PSScriptRoot "..\fixtures\sk-SK\payment-confirmation-request.wav"
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $resolvedOutput
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

Add-Type -AssemblyName System.Speech
$synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $preferredVoice = $synthesizer.GetInstalledVoices() |
        Where-Object { $_.VoiceInfo.Culture.Name -eq "sk-SK" } |
        Select-Object -First 1
    if ($null -eq $preferredVoice) {
        $preferredVoice = $synthesizer.GetInstalledVoices() |
            Where-Object { $_.VoiceInfo.Culture.Name -like "en-*" } |
            Select-Object -First 1
    }
    if ($null -eq $preferredVoice) {
        throw "No Windows synthetic speech voice is installed."
    }

    $synthesizer.SelectVoice($preferredVoice.VoiceInfo.Name)
    $synthesizer.Rate = -1
    $synthesizer.SetOutputToWaveFile($resolvedOutput)
    $synthesizer.Speak(
        "Priprav mi potvrdenie o zaplatení 5000 eur Jankovi Hraškovi, " +
        "adresa Testovo 10, splatné do konca roka."
    )
}
finally {
    $synthesizer.Dispose()
}

$bytes = [System.IO.File]::ReadAllBytes($resolvedOutput)
if ($bytes.Length -lt 45 -or
    [System.Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne "RIFF" -or
    [System.Text.Encoding]::ASCII.GetString($bytes, 8, 4) -ne "WAVE") {
    throw "Synthetic fixture is not a valid RIFF/WAVE file."
}

Write-Host "Generated synthetic WAV fixture ($($bytes.Length) bytes)."
