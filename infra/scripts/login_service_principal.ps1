[CmdletBinding()]
param(
    [string]$ClientId,
    [string]$ClientSecret,
    [string]$TenantId,
    [string]$SubscriptionId,
    [string]$EnvFilePath = ".env",
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

Assert-ToolInstalled -ToolName "az"

$scriptRoot = Split-Path -Parent $PSCommandPath
$infraRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $infraRoot
$resolvedEnvFilePath = Join-Path $repoRoot $EnvFilePath

$clientIdFromEnvFile = ""
$clientSecretFromEnvFile = ""
$tenantIdFromEnvFile = ""
$subscriptionIdFromEnvFile = ""

if (-not $SkipEnvFile -and (Test-Path -Path $resolvedEnvFilePath)) {
    $clientIdFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CLIENT_ID"
    $clientSecretFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CLIENT_SECRET"
    $tenantIdFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_TENANT_ID"
    $subscriptionIdFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_SUBSCRIPTION_ID"
}

$ClientId = Resolve-InputValue -ExplicitValue $ClientId -EnvFileValue $clientIdFromEnvFile -EnvironmentValue $env:AZURE_CLIENT_ID
$ClientSecret = Resolve-InputValue -ExplicitValue $ClientSecret -EnvFileValue $clientSecretFromEnvFile -EnvironmentValue $env:AZURE_CLIENT_SECRET
$TenantId = Resolve-InputValue -ExplicitValue $TenantId -EnvFileValue $tenantIdFromEnvFile -EnvironmentValue $env:AZURE_TENANT_ID
$SubscriptionId = Resolve-InputValue -ExplicitValue $SubscriptionId -EnvFileValue $subscriptionIdFromEnvFile -EnvironmentValue $env:AZURE_SUBSCRIPTION_ID

Require-Value -Name "ClientId" -Value $ClientId
Require-Value -Name "ClientSecret" -Value $ClientSecret
Require-Value -Name "TenantId" -Value $TenantId
Require-Value -Name "SubscriptionId" -Value $SubscriptionId

$env:AZURE_CLIENT_ID = $ClientId
$env:AZURE_CLIENT_SECRET = $ClientSecret
$env:AZURE_TENANT_ID = $TenantId
$env:AZURE_SUBSCRIPTION_ID = $SubscriptionId

Write-Host "Logging into Azure with service principal..."
az login --service-principal `
    --username $env:AZURE_CLIENT_ID `
    --password $env:AZURE_CLIENT_SECRET `
    --tenant $env:AZURE_TENANT_ID `
    --only-show-errors `
    --output none

az account set --subscription $env:AZURE_SUBSCRIPTION_ID

$account = az account show --query "{subscription:id, tenant:tenantId, user:user.name}" --output json | ConvertFrom-Json

Write-Host "Azure login successful."
Write-Host "Subscription: $($account.subscription)"
Write-Host "Tenant:       $($account.tenant)"
Write-Host "Principal:    $($account.user)"
