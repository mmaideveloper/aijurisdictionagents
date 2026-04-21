param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8080",
    [string]$ApiKey = "",
    [string]$Jurisdiction = "SK",
    [string]$OutputDir = "",
    [int]$TimeoutSec = 60,
    [switch]$SkipApiBootstrap,
    [switch]$ContinueOnError
)

$ErrorActionPreference = "Stop"

function Resolve-PowerShellPath {
    $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwshCmd) {
        return $pwshCmd.Source
    }

    $powershellCmd = Get-Command powershell -ErrorAction SilentlyContinue
    if ($powershellCmd) {
        return $powershellCmd.Source
    }

    throw "PowerShell executable not found."
}

function Import-DotEnv {
    param([string]$RepoRoot)

    $envPath = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envPath)) {
        return
    }

    foreach ($rawLine in Get-Content -Path $envPath) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or ($line -notmatch "=")) {
            continue
        }

        $name, $value = $line.Split("=", 2)
        $name = $name.Trim()
        if (-not $name) {
            continue
        }

        $value = $value.Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Test-UrlReady {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Ensure-LocalApi {
    param(
        [string]$RepoRoot,
        [string]$TargetBaseUrl
    )

    $healthUrl = "$TargetBaseUrl/health"
    if (Test-UrlReady -Url $healthUrl) {
        return
    }

    $apiUri = [System.Uri]$TargetBaseUrl
    $launcher = Join-Path $RepoRoot "skills\juris-api\scripts\start_juris_api.ps1"
    if (-not (Test-Path $launcher)) {
        throw "Juris API start skill script not found: $launcher"
    }

    Import-DotEnv -RepoRoot $RepoRoot
    $shellPath = Resolve-PowerShellPath
    $apiArgs = @(
        "-NoProfile",
        "-File", $launcher,
        "-Background",
        "-SkipLogTail",
        "-BindHost", $apiUri.Host,
        "-Port", "$($apiUri.Port)"
    )

    Start-Process -FilePath $shellPath -ArgumentList $apiArgs -WorkingDirectory $RepoRoot | Out-Null

    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if (Test-UrlReady -Url $healthUrl) {
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "Local API health check failed after startup: $healthUrl"
}

function Get-SafeFileName {
    param(
        [string]$ContentDisposition,
        [string]$FallbackStem
    )

    if ($ContentDisposition) {
        if ($ContentDisposition -match 'filename\*=UTF-8''''([^;]+)') {
            return [System.Uri]::UnescapeDataString($Matches[1]).Trim('"')
        }
        if ($ContentDisposition -match 'filename="?([^";]+)"?') {
            return $Matches[1].Trim()
        }
    }

    $safeStem = $FallbackStem -replace '[^A-Za-z0-9._-]+', '_'
    $safeStem = $safeStem.Trim("._-")
    if (-not $safeStem) {
        $safeStem = "document_template"
    }
    return "$safeStem-preview.pdf"
}

function New-TemplateManifestItem {
    param(
        [object]$Template,
        [string]$Status,
        [string]$FileName,
        [string]$ErrorMessage,
        [int64]$Bytes
    )

    [pscustomobject]@{
        template_key = $Template.template_key
        title = $Template.title
        category = $Template.category
        template_kind = $Template.template_kind
        jurisdiction = $Template.jurisdiction
        status = $Status
        file_name = $FileName
        bytes = $Bytes
        error = $ErrorMessage
    }
}

$skillScriptsDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $skillScriptsDir "..\..\..")

if (-not $ApiKey) {
    $ApiKey = $env:API_KEY
}
if (-not $ApiKey) {
    $ApiKey = "aijuris"
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "runs\testdocument\document-template-pdfs"
}

$ApiBaseUrl = $ApiBaseUrl.TrimEnd("/")
$Jurisdiction = $Jurisdiction.Trim().ToUpperInvariant()
$resolvedOutputDir = New-Item -Path $OutputDir -ItemType Directory -Force

if (-not $SkipApiBootstrap) {
    Ensure-LocalApi -RepoRoot $repoRoot -TargetBaseUrl $ApiBaseUrl
}

$headers = @{ "x-api-key" = $ApiKey }
$listUrl = "$ApiBaseUrl/v1/document-templates?include_deleted=false&jurisdiction=$([System.Uri]::EscapeDataString($Jurisdiction))"
$templateResponse = Invoke-RestMethod -Uri $listUrl -Headers $headers -TimeoutSec $TimeoutSec
$templates = @($templateResponse.items | Where-Object { $_.is_enabled -and -not $_.is_deleted })

if (-not $templates) {
    throw "No enabled document templates returned for jurisdiction '$Jurisdiction'."
}

$manifest = @()
foreach ($template in $templates) {
    $templateKey = [string]$template.template_key
    $encodedKey = [System.Uri]::EscapeDataString($templateKey)
    $encodedJurisdiction = [System.Uri]::EscapeDataString([string]$template.jurisdiction)
    $previewUrl = "$ApiBaseUrl/v1/document-templates/$encodedKey/preview/pdf?jurisdiction=$encodedJurisdiction"
    $fallbackName = Get-SafeFileName -ContentDisposition "" -FallbackStem $templateKey
    $targetPath = Join-Path $resolvedOutputDir.FullName $fallbackName

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $previewUrl -Headers $headers -OutFile $targetPath -TimeoutSec $TimeoutSec -PassThru
        $contentType = [string]$response.Headers["Content-Type"]
        if ($contentType -and ($contentType -notlike "application/pdf*")) {
            throw "Preview endpoint returned unexpected content type '$contentType'."
        }

        $fileName = Get-SafeFileName -ContentDisposition ([string]$response.Headers["Content-Disposition"]) -FallbackStem $templateKey
        if ($fileName -ne $fallbackName) {
            $renamedPath = Join-Path $resolvedOutputDir.FullName $fileName
            Move-Item -LiteralPath $targetPath -Destination $renamedPath -Force
            $targetPath = $renamedPath
        }

        $file = Get-Item -LiteralPath $targetPath
        if ($file.Length -lt 100) {
            throw "Generated PDF is unexpectedly small ($($file.Length) bytes)."
        }

        $manifest += New-TemplateManifestItem -Template $template -Status "ok" -FileName $file.Name -ErrorMessage "" -Bytes $file.Length
        Write-Output "OK  $templateKey -> $($file.Name)"
    } catch {
        $errorMessage = $_.Exception.Message
        $manifest += New-TemplateManifestItem -Template $template -Status "failed" -FileName $fallbackName -ErrorMessage $errorMessage -Bytes 0
        Write-Warning "FAIL $templateKey -> $errorMessage"
        if (-not $ContinueOnError) {
            break
        }
    }
}

$manifestPath = Join-Path $resolvedOutputDir.FullName "manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding UTF8

$failed = @($manifest | Where-Object { $_.status -ne "ok" })
$generated = @($manifest | Where-Object { $_.status -eq "ok" })

Write-Output ""
Write-Output "Generated PDFs: $($generated.Count) / $($templates.Count)"
Write-Output "Output folder: $($resolvedOutputDir.FullName)"
Write-Output "Manifest: $manifestPath"

if ($failed.Count -gt 0) {
    $details = ($failed | ForEach-Object { "$($_.template_key): $($_.error)" }) -join [Environment]::NewLine
    throw "Document template PDF generation failed for $($failed.Count) template(s).`n$details"
}
