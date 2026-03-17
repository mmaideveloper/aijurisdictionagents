[CmdletBinding()]
param(
    [string]$ResourceGroupName,
    [string]$ContainerAppName,
    [int]$Tail = 100,
    [string]$Revision,
    [string]$CorrelationId,
    [string]$RequestId,
    [string]$EnvFilePath = ".env",
    [switch]$SystemLogs,
    [switch]$SkipEnvFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-ToolInstalled {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ToolName
    )

    if (-not (Get-Command $ToolName -ErrorAction SilentlyContinue)) {
        throw "Missing required tool '$ToolName'. Install it and retry."
    }
}

function Get-ValueFromEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    if (-not (Test-Path -Path $Path)) {
        return ""
    }

    $pattern = "^\s*$Key=(?<value>.*)$"
    $line = Get-Content -Path $Path | Where-Object { $_ -match $pattern } | Select-Object -First 1
    if (-not $line) {
        return ""
    }

    $value = [regex]::Match($line, $pattern).Groups["value"].Value.Trim()
    if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) {
        if ($value.Length -ge 2) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }

    return $value
}

function Resolve-InputValue {
    param(
        [string]$ExplicitValue,
        [string]$EnvFileValue,
        [string]$EnvironmentValue
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitValue)) {
        return $ExplicitValue
    }
    if (-not [string]::IsNullOrWhiteSpace($EnvFileValue)) {
        return $EnvFileValue
    }
    return $EnvironmentValue
}

function Require-Value {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required. Pass it as a parameter, define it in .env, or set env var."
    }
}

Assert-ToolInstalled -ToolName "az"

if ($Tail -lt 0 -or $Tail -gt 300) {
    throw "Tail must be between 0 and 300."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$resolvedEnvFilePath = if ($SkipEnvFile) {
    ""
}
else {
    $candidate = if ([System.IO.Path]::IsPathRooted($EnvFilePath)) {
        $EnvFilePath
    }
    else {
        Join-Path $repoRoot $EnvFilePath
    }

    if (Test-Path -Path $candidate) { $candidate } else { "" }
}

$resourceGroupFromEnvFile = if ($resolvedEnvFilePath) {
    Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_RESOURCE_GROUP"
}
else {
    ""
}
$containerAppFromEnvFile = if ($resolvedEnvFilePath) {
    Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CONTAINER_APP_NAME"
}
else {
    ""
}

$ResourceGroupName = Resolve-InputValue -ExplicitValue $ResourceGroupName -EnvFileValue $resourceGroupFromEnvFile -EnvironmentValue $env:AZURE_RESOURCE_GROUP
$ContainerAppName = Resolve-InputValue -ExplicitValue $ContainerAppName -EnvFileValue $containerAppFromEnvFile -EnvironmentValue $env:AZURE_CONTAINER_APP_NAME

Require-Value -Name "ResourceGroupName" -Value $ResourceGroupName
Require-Value -Name "ContainerAppName" -Value $ContainerAppName

$arguments = @(
    "containerapp", "logs", "show",
    "--name", $ContainerAppName,
    "--resource-group", $ResourceGroupName,
    "--tail", "$Tail"
)

if ($SystemLogs) {
    $arguments += @("--type", "system")
}
if (-not [string]::IsNullOrWhiteSpace($Revision)) {
    $arguments += @("--revision", $Revision)
}

$rawLogs = & az @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read Container App logs."
}

$filters = @()
if (-not [string]::IsNullOrWhiteSpace($CorrelationId)) {
    $filters += $CorrelationId
}
if (-not [string]::IsNullOrWhiteSpace($RequestId)) {
    $filters += $RequestId
}

$lines = @($rawLogs)
if ($filters.Count -gt 0) {
    $matched = @(
        foreach ($line in $lines) {
            $lineText = [string]$line
            foreach ($filter in $filters) {
                if ($lineText.Contains($filter)) {
                    $lineText
                    break
                }
            }
        }
    )
    if (-not $matched) {
        Write-Host "No log lines matched the requested filter(s)." -ForegroundColor Yellow
        exit 0
    }
    $matched
    exit 0
}

$lines
