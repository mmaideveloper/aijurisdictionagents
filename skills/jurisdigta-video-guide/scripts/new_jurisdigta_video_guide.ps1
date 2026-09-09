[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    [string]$Slug,
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Title,
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$NarrationText,
    [datetime]$Date = (Get-Date),
    [switch]$Synthesize,
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$episodeName = "{0}-{1}" -f $Date.ToString("yyyy-MM-dd"), $Slug
$episodePath = Join-Path $repoRoot "marketing\youtube-shorts\$episodeName"
$presenterPath = Join-Path $repoRoot "marketing\youtube-shorts\assets\presenter-base-4s.mp4"
$logoPath = Join-Path $repoRoot "marketing\youtube-shorts\assets\logo-black-hires.png"

if (Test-Path -LiteralPath $episodePath) { throw "Episode already exists: $episodePath" }
if (-not (Test-Path -LiteralPath $presenterPath)) { throw "Reusable presenter source is missing: $presenterPath" }
if (-not (Test-Path -LiteralPath $logoPath)) { throw "Clean logo source is missing: $logoPath" }
if (-not $PSCmdlet.ShouldProcess($episodePath, "Create JurisDigta video-guide scaffold")) { return }

New-Item -ItemType Directory -Path $episodePath | Out-Null
$NarrationText.Trim() | Set-Content -LiteralPath (Join-Path $episodePath "narration.sk.txt") -Encoding utf8
$manifest = [ordered]@{
    schemaVersion = 1; slug = $Slug; title = $Title; date = $Date.ToString("yyyy-MM-dd")
    language = "sk-SK"; voice = "sk-SK-ViktoriaNeural"; voiceRate = "+8%"
    width = 1080; height = 1920; frameRate = 30; targetDurationSeconds = "10-15"
    presenterSource = "../assets/presenter-base-4s.mp4"; logoSource = "../assets/logo-black-hires.png"
    finalVideo = "$Slug-sk.mp4"; status = "scaffold"
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $episodePath "guide.json") -Encoding utf8

if ($Synthesize) {
    & $PythonPath -m edge_tts --voice sk-SK-ViktoriaNeural --rate=+8% --file (Join-Path $episodePath "narration.sk.txt") --write-media (Join-Path $episodePath "narration-viktoria.mp3") --write-subtitles (Join-Path $episodePath "speech.sk.srt")
    if ($LASTEXITCODE -ne 0) { throw "Viktoria narration synthesis failed. Install edge-tts in an isolated environment and retry." }
}

[pscustomobject]@{
    EpisodePath = $episodePath; Voice = "sk-SK-ViktoriaNeural"; VoiceRate = "+8%"
    PresenterSource = $presenterPath; LogoSource = $logoPath; NarrationGenerated = [bool]$Synthesize
}
