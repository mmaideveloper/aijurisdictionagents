[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workflowFiles = @(
    ".github/workflows/api_build_deploy.yml",
    ".github/workflows/web_build_deploy.yml",
    ".github/workflows/laws_collector_build_deploy.yml",
    ".github/workflows/email_build_deploy.yml",
    ".github/workflows/document_processor_build_deploy.yml"
)

$createImageInputPattern = '(?ms)^      create_image:\s+description:.*?required: false\s+type: boolean\s+default: false'
$deployInputPattern = '(?ms)^      deploy:\s+description:.*?required: false\s+type: boolean\s+default: false'
$effectiveGate = "if: github.event_name == 'workflow_dispatch' && (inputs.create_image || inputs.deploy)"

foreach ($relativePath in $workflowFiles) {
    $path = Join-Path $repoRoot $relativePath
    $content = Get-Content -Raw -Path $path
    if ($content -notmatch $createImageInputPattern) {
        throw "$relativePath must define create_image as a boolean with default false."
    }
    if ($content -notmatch $deployInputPattern) {
        throw "$relativePath must define deploy as a boolean with default false."
    }
    if (-not $content.Contains($effectiveGate)) {
        throw "$relativePath must gate Azure publication with create_image || deploy."
    }
    Write-Host "$relativePath`: workflow controls OK"
}

$buildOnlyCases = @(
    @{
        Script = "infra/scripts/deploy_laws_collector.ps1"
        Extra = @{ SystemEmbeddingModelOption = "cloud"; SystemEmbeddingModel = "unused" }
    },
    @{
        Script = "infra/scripts/deploy_email_scheduler.ps1"
        Extra = @{}
    },
    @{
        Script = "infra/scripts/deploy_document_processor.ps1"
        Extra = @{ SystemEmbeddingModelOption = "cloud"; SystemEmbeddingModel = "unused" }
    }
)

foreach ($case in $buildOnlyCases) {
    $global:AcrWorkflowValidationAzCalls = [System.Collections.Generic.List[string]]::new()
    function global:az {
        $global:AcrWorkflowValidationAzCalls.Add(($args -join " "))
        $global:LASTEXITCODE = 0
    }
    function global:python {
        $global:LASTEXITCODE = 0
    }

    try {
        $arguments = @{
            SkipEnvFile = $true
            BuildOnly = $true
            SubscriptionId = "00000000-0000-0000-0000-000000000000"
            AcrName = "validationacr"
            ImageTag = "offline-validation"
        }
        foreach ($entry in $case.Extra.GetEnumerator()) {
            $arguments[$entry.Key] = $entry.Value
        }

        & (Join-Path $repoRoot $case.Script) @arguments

        $calls = $global:AcrWorkflowValidationAzCalls
        if ($calls.Count -ne 2 -or $calls[0] -notmatch '^account set ' -or $calls[1] -notmatch '^acr build ') {
            throw "$($case.Script) build-only mode invoked unexpected Azure operations: $($calls -join '; ')"
        }
        if (($calls -join " ") -match 'group|postgres|containerapp|deployment') {
            throw "$($case.Script) build-only mode attempted a deployment mutation: $($calls -join '; ')"
        }
        Write-Host "$($case.Script): build-only isolation OK"
    }
    finally {
        Remove-Item Function:\az -ErrorAction SilentlyContinue
        Remove-Item Function:\python -ErrorAction SilentlyContinue
        Remove-Variable AcrWorkflowValidationAzCalls -Scope Global -ErrorAction SilentlyContinue
    }
}

Write-Host "ACR workflow control validation passed."
