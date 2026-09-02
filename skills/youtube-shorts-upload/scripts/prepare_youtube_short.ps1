[CmdletBinding(DefaultParameterSetName = "Url")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Url")]
    [ValidatePattern("^https://")]
    [string]$VideoUrl,

    [Parameter(Mandatory = $true, ParameterSetName = "Path")]
    [string]$VideoPath,

    [ValidateRange(1, 2147483648)]
    [long]$MaxBytes = 536870912
)

$ErrorActionPreference = "Stop"
$allowedExtensions = @(".mp4", ".mov", ".webm")
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$resolvedOutputDirectory = Join-Path $repoRoot "runs\youtube-shorts-upload"

New-Item -ItemType Directory -Force -Path $resolvedOutputDirectory | Out-Null

$temporaryPath = ""
$sourceKind = $PSCmdlet.ParameterSetName
$sourceHost = ""

try {
    if ($PSCmdlet.ParameterSetName -eq "Url") {
        $uri = [Uri]$VideoUrl
        $sourceHost = $uri.Host
        $sourceName = [System.IO.Path]::GetFileName($uri.AbsolutePath)
        if (-not $sourceName) {
            throw "The HTTPS URL must end with a video filename."
        }

        $extension = [System.IO.Path]::GetExtension($sourceName).ToLowerInvariant()
        if ($extension -notin $allowedExtensions) {
            throw "Unsupported video extension '$extension'. Allowed: $($allowedExtensions -join ', ')."
        }

        $temporaryPath = Join-Path $resolvedOutputDirectory (".download-{0}{1}" -f ([Guid]::NewGuid().ToString("N")), $extension)
        $httpClient = [System.Net.Http.HttpClient]::new()
        $response = $null
        $inputStream = $null
        $outputStream = $null
        try {
            $response = $httpClient.GetAsync(
                $uri,
                [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
            ).GetAwaiter().GetResult()
            $null = $response.EnsureSuccessStatusCode()

            if ($response.RequestMessage.RequestUri.Scheme -ne "https") {
                throw "The video download redirected to a non-HTTPS URL."
            }

            $contentLength = $response.Content.Headers.ContentLength
            if ($contentLength -and $contentLength -gt $MaxBytes) {
                throw "The remote video is $contentLength bytes, exceeding the configured limit of $MaxBytes bytes."
            }

            $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $outputStream = [System.IO.File]::Open(
                $temporaryPath,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            $buffer = [byte[]]::new(81920)
            $downloadedBytes = 0L
            while (($bytesRead = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $downloadedBytes += $bytesRead
                if ($downloadedBytes -gt $MaxBytes) {
                    throw "The remote video exceeded the configured limit of $MaxBytes bytes during download."
                }
                $outputStream.Write($buffer, 0, $bytesRead)
            }
        }
        finally {
            if ($outputStream) { $outputStream.Dispose() }
            if ($inputStream) { $inputStream.Dispose() }
            if ($response) { $response.Dispose() }
            $httpClient.Dispose()
        }
        $sourceFile = Get-Item -LiteralPath $temporaryPath
    }
    else {
        $sourceFile = Get-Item -LiteralPath $VideoPath
        if ($sourceFile.PSIsContainer) {
            throw "VideoPath must point to a file, not a directory."
        }
        $sourceName = $sourceFile.Name
        $extension = $sourceFile.Extension.ToLowerInvariant()
        if ($extension -notin $allowedExtensions) {
            throw "Unsupported video extension '$extension'. Allowed: $($allowedExtensions -join ', ')."
        }
    }

    if ($sourceFile.Length -le 0) {
        throw "The video file is empty."
    }
    if ($sourceFile.Length -gt $MaxBytes) {
        throw "The video is $($sourceFile.Length) bytes, exceeding the configured limit of $MaxBytes bytes."
    }

    $probeStatus = "ffprobe unavailable; verify Short eligibility in YouTube Studio"
    $width = $null
    $height = $null
    $durationSeconds = $null
    $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
    if ($ffprobe) {
        $probeJson = & $ffprobe.Source -v error -select_streams v:0 -show_entries stream=width,height,duration -of json $sourceFile.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "ffprobe could not read the source video."
        }
        $probe = $probeJson | ConvertFrom-Json
        $stream = @($probe.streams)[0]
        if (-not $stream) {
            throw "No video stream was found."
        }
        $width = [int]$stream.width
        $height = [int]$stream.height
        $durationSeconds = [double]$stream.duration
        if ($width -gt $height) {
            throw "The video is horizontal ($width x $height); YouTube Shorts require square or vertical media."
        }
        if ($durationSeconds -gt 180) {
            throw "The video is $durationSeconds seconds long; YouTube Shorts must be 180 seconds or shorter."
        }
        $probeStatus = "eligible"
    }

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFile.FullName).Hash.ToLowerInvariant()
    $safeStem = [System.IO.Path]::GetFileNameWithoutExtension($sourceName) -replace "[^A-Za-z0-9._-]", "-"
    $safeStem = $safeStem.Trim("-", ".")
    if (-not $safeStem) {
        $safeStem = "youtube-short"
    }

    $destinationPath = Join-Path $resolvedOutputDirectory "$safeStem$extension"
    if (Test-Path -LiteralPath $destinationPath) {
        $existingHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destinationPath).Hash.ToLowerInvariant()
        if ($existingHash -ne $hash) {
            $destinationPath = Join-Path $resolvedOutputDirectory "$safeStem-$($hash.Substring(0, 8))$extension"
        }
    }

    if (-not (Test-Path -LiteralPath $destinationPath)) {
        Copy-Item -LiteralPath $sourceFile.FullName -Destination $destinationPath
    }

    [pscustomobject]@{
        StagedPath = (Resolve-Path -LiteralPath $destinationPath).Path
        SizeBytes = (Get-Item -LiteralPath $destinationPath).Length
        Sha256 = $hash
        SourceKind = $sourceKind
        SourceHost = $sourceHost
        ProbeStatus = $probeStatus
        Width = $width
        Height = $height
        DurationSeconds = $durationSeconds
    }
}
finally {
    if ($temporaryPath -and (Test-Path -LiteralPath $temporaryPath)) {
        Remove-Item -LiteralPath $temporaryPath -Force
    }
}
