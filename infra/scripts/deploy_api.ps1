[CmdletBinding()]
param(
    [string]$SubscriptionId,
    [string]$Location,
    [string]$ResourceGroupName,
    [string]$EnvironmentName,
    [string]$ContainerAppName,
    [string]$AcrName,
    [string]$LogAnalyticsWorkspaceName,
    [string]$ManagedIdentityName,
    [string]$ImageTag,
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

function Get-DefaultAcrName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Seed
    )

    $sanitized = ($Seed.ToLower() -replace "[^a-z0-9]", "")
    if ([string]::IsNullOrWhiteSpace($sanitized)) {
        $sanitized = "aijur"
    }
    if ($sanitized.Length -gt 38) {
        $sanitized = $sanitized.Substring(0, 38)
    }

    $suffix = -join ((48..57) | Get-Random -Count 5 | ForEach-Object { [char]$_ })
    return "$sanitized$suffix"
}

function Normalize-AcrName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputName
    )

    $name = $InputName.Trim().ToLower()
    if ($name.EndsWith(".azurecr.io")) {
        $name = $name.Substring(0, $name.Length - ".azurecr.io".Length)
    }

    $sanitized = ($name -replace "[^a-z0-9]", "")
    if ([string]::IsNullOrWhiteSpace($sanitized)) {
        throw "ACR name '$InputName' is invalid after sanitization. Use 5-50 lowercase alphanumeric characters."
    }

    if ($sanitized.Length -lt 5) {
        throw "ACR name '$InputName' is too short after sanitization ('$sanitized'). Minimum is 5 characters."
    }

    if ($sanitized.Length -gt 50) {
        $sanitized = $sanitized.Substring(0, 50)
    }

    return $sanitized
}

function Resolve-ImageSpec {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DefaultRepository,
        [Parameter(Mandatory = $true)]
        [string]$ImageTagOrRepositoryTag
    )

    $inputValue = $ImageTagOrRepositoryTag.Trim()
    if ([string]::IsNullOrWhiteSpace($inputValue)) {
        throw "Image tag is empty. Provide a tag or repository:tag."
    }
    if ($inputValue.Contains("@")) {
        throw "Image value '$inputValue' is invalid. Use 'tag' or 'repository:tag' (digest syntax is not supported here)."
    }

    $repository = $DefaultRepository.Trim().ToLower()
    $tag = $inputValue

    $colonCount = ([regex]::Matches($inputValue, ":")).Count
    if ($colonCount -gt 1) {
        throw "Image value '$inputValue' is invalid. Use either 'tag' or 'repository:tag'."
    }
    if ($colonCount -eq 1) {
        $parts = $inputValue.Split(":", 2)
        $repository = $parts[0].Trim().ToLower()
        $tag = $parts[1].Trim()
    }

    if ([string]::IsNullOrWhiteSpace($repository) -or [string]::IsNullOrWhiteSpace($tag)) {
        throw "Image value '$inputValue' is invalid. Use either 'tag' or 'repository:tag'."
    }
    if ($repository -notmatch '^[a-z0-9]+([._/-][a-z0-9]+)*$') {
        throw "Invalid repository '$repository'. Use lowercase letters, digits, and separators . _ - /."
    }
    if ($tag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') {
        throw "Invalid tag '$tag'. Allowed: alphanumeric, underscore, dot, dash (max 128 chars)."
    }

    return @{
        Repository = $repository
        Tag = $tag
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

function Ensure-ServicePrincipalLogin {
    param(
        [string]$ExpectedClientId,
        [string]$LoginScriptPath,
        [string]$EnvFilePath,
        [switch]$SkipEnvFile
    )

    if ([string]::IsNullOrWhiteSpace($ExpectedClientId)) {
        Write-Host "AZURE_CLIENT_ID not provided via .env or env vars. Skipping service principal identity check."
        return
    }

    $currentUserName = ""
    $currentUserType = ""
    $accountRaw = az account show --query "{name:user.name,type:user.type}" --output json 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace([string]$accountRaw)) {
        try {
            $account = ($accountRaw | ConvertFrom-Json)
            $currentUserName = [string]$account.name
            $currentUserType = [string]$account.type
        }
        catch {
            $currentUserName = ""
            $currentUserType = ""
        }
    }

    $isMatchingPrincipal = (
        -not [string]::IsNullOrWhiteSpace($currentUserName) -and
        $currentUserName.Trim().ToLower() -eq $ExpectedClientId.Trim().ToLower()
    )

    if ($isMatchingPrincipal) {
        Write-Host "Azure principal already matches .env service principal '$ExpectedClientId' (type: $currentUserType)."
        return
    }

    if (-not (Test-Path -Path $LoginScriptPath)) {
        throw "Login helper script not found at '$LoginScriptPath'."
    }

    Write-Host "Azure principal does not match .env service principal '$ExpectedClientId'. Running login helper..."
    if ($SkipEnvFile) {
        & $LoginScriptPath -SkipEnvFile -EnvFilePath $EnvFilePath
    }
    else {
        & $LoginScriptPath -EnvFilePath $EnvFilePath
    }
}

function Convert-EnvFileToPairs {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -Path $Path)) {
        return @()
    }

    $allowedKeys = @(
        "LLM_PROVIDER",
        "OPENAI_KEY",
        "OPENAI_MODEL",
        "OPENAI_TEMPERATURE",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_AD_TOKEN",
        "AZURE_OPENAI_API_VERSION",
        "OPENAI_API_VERSION"
    )

    $pairs = New-Object System.Collections.Generic.List[string]
    $lines = Get-Content -Path $Path
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $match = [regex]::Match($trimmed, "^(?<key>[A-Za-z_][A-Za-z0-9_]*)=(?<value>.*)$")
        if (-not $match.Success) {
            continue
        }

        $key = $match.Groups["key"].Value
        if ($allowedKeys -notcontains $key) {
            continue
        }

        $value = $match.Groups["value"].Value.Trim()
        if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) {
            if ($value.Length -ge 2) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }

        $pairs.Add("$key=$value")
    }

    return $pairs.ToArray()
}

Assert-ToolInstalled -ToolName "az"

$scriptRoot = Split-Path -Parent $PSCommandPath
$infraRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $infraRoot
$resolvedEnvFilePath = Join-Path $repoRoot $EnvFilePath

$subscriptionIdFromEnvFile = ""
$locationFromEnvFile = ""
$resourceGroupFromEnvFile = ""
$environmentNameFromEnvFile = ""
$containerAppNameFromEnvFile = ""
$acrNameFromEnvFile = ""
$logAnalyticsWorkspaceFromEnvFile = ""
$managedIdentityNameFromEnvFile = ""
$imageTagFromEnvFile = ""
$clientIdFromEnvFile = ""

if (-not $SkipEnvFile -and (Test-Path -Path $resolvedEnvFilePath)) {
    $subscriptionIdFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_SUBSCRIPTION_ID"
    $locationFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_LOCATION"
    $resourceGroupFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_RESOURCE_GROUP"
    $environmentNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CONTAINERAPPS_ENVIRONMENT"
    $containerAppNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CONTAINER_APP_NAME"
    $acrNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CONTAINER_REGISTRY"
    $logAnalyticsWorkspaceFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_LOG_ANALYTICS_WORKSPACE_NAME"
    $managedIdentityNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_MANAGED_IDENTITY_NAME"
    $imageTagFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_API_IMAGE_TAG"
    $clientIdFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CLIENT_ID"
}

$SubscriptionId = Resolve-InputValue -ExplicitValue $SubscriptionId -EnvFileValue $subscriptionIdFromEnvFile -EnvironmentValue $env:AZURE_SUBSCRIPTION_ID
$Location = Resolve-InputValue -ExplicitValue $Location -EnvFileValue $locationFromEnvFile -EnvironmentValue $env:AZURE_LOCATION
$ResourceGroupName = Resolve-InputValue -ExplicitValue $ResourceGroupName -EnvFileValue $resourceGroupFromEnvFile -EnvironmentValue $env:AZURE_RESOURCE_GROUP
$EnvironmentName = Resolve-InputValue -ExplicitValue $EnvironmentName -EnvFileValue $environmentNameFromEnvFile -EnvironmentValue $env:AZURE_CONTAINERAPPS_ENVIRONMENT
$ContainerAppName = Resolve-InputValue -ExplicitValue $ContainerAppName -EnvFileValue $containerAppNameFromEnvFile -EnvironmentValue $env:AZURE_CONTAINER_APP_NAME
$AcrName = Resolve-InputValue -ExplicitValue $AcrName -EnvFileValue $acrNameFromEnvFile -EnvironmentValue $env:AZURE_CONTAINER_REGISTRY
$LogAnalyticsWorkspaceName = Resolve-InputValue -ExplicitValue $LogAnalyticsWorkspaceName -EnvFileValue $logAnalyticsWorkspaceFromEnvFile -EnvironmentValue $env:AZURE_LOG_ANALYTICS_WORKSPACE_NAME
$ManagedIdentityName = Resolve-InputValue -ExplicitValue $ManagedIdentityName -EnvFileValue $managedIdentityNameFromEnvFile -EnvironmentValue $env:AZURE_MANAGED_IDENTITY_NAME
$ImageTag = Resolve-InputValue -ExplicitValue $ImageTag -EnvFileValue $imageTagFromEnvFile -EnvironmentValue $env:AZURE_API_IMAGE_TAG
$ExpectedServicePrincipalClientId = Resolve-InputValue -ExplicitValue "" -EnvFileValue $clientIdFromEnvFile -EnvironmentValue $env:AZURE_CLIENT_ID

if ([string]::IsNullOrWhiteSpace($Location)) {
    $Location = "eastus"
}
if ([string]::IsNullOrWhiteSpace($ResourceGroupName)) {
    $ResourceGroupName = "rg-aijurisdiction-dev"
}
if ([string]::IsNullOrWhiteSpace($EnvironmentName)) {
    $EnvironmentName = "cae-aijurisdiction-dev"
}
if ([string]::IsNullOrWhiteSpace($ContainerAppName)) {
    $ContainerAppName = "ca-aijuristiction-api-dev"
}
if ([string]::IsNullOrWhiteSpace($LogAnalyticsWorkspaceName)) {
    $LogAnalyticsWorkspaceName = "log-aijurisdiction-dev"
}
if ([string]::IsNullOrWhiteSpace($ManagedIdentityName)) {
    $ManagedIdentityName = "id-aijurisdiction-api-dev"
}
if ([string]::IsNullOrWhiteSpace($ImageTag)) {
    $ImageTag = "local-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}
$imageSpec = Resolve-ImageSpec -DefaultRepository "aijuristiction-api" -ImageTagOrRepositoryTag $ImageTag
$ImageRepository = [string]$imageSpec.Repository
$ImageTag = [string]$imageSpec.Tag

Require-Value -Name "SubscriptionId" -Value $SubscriptionId

if ([string]::IsNullOrWhiteSpace($AcrName)) {
    $AcrName = Get-DefaultAcrName -Seed $ResourceGroupName
}
$originalAcrName = $AcrName
$AcrName = Normalize-AcrName -InputName $AcrName
if ($AcrName -ne $originalAcrName) {
    Write-Host "Normalized ACR name from '$originalAcrName' to '$AcrName' to satisfy Azure naming rules."
}

Write-Host "Using ACR name: $AcrName"
Write-Host "Using image: ${ImageRepository}:${ImageTag}"
Write-Host "Repository root: $repoRoot"

Ensure-ServicePrincipalLogin `
    -ExpectedClientId $ExpectedServicePrincipalClientId `
    -LoginScriptPath (Join-Path $scriptRoot "login_service_principal.ps1") `
    -EnvFilePath $EnvFilePath `
    -SkipEnvFile:$SkipEnvFile

az account set --subscription $SubscriptionId | Out-Null
az extension add --name containerapp --upgrade --only-show-errors | Out-Null

$resourceGroupExists = az group exists --name $ResourceGroupName --output tsv
if ($resourceGroupExists -eq "true") {
    Write-Host "Resource group '$ResourceGroupName' already exists. Skipping creation."
}
else {
    Write-Host "Creating resource group '$ResourceGroupName' in '$Location'..."
    az group create `
        --name $ResourceGroupName `
        --location $Location `
        --only-show-errors `
        --output none
}

Write-Host "Deploying Azure infrastructure with Bicep..."
$outputsRaw = az deployment group create `
    --resource-group $ResourceGroupName `
    --name "api-infra-$([DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))" `
    --template-file (Join-Path $infraRoot "bicep/main.bicep") `
    --parameters `
      location=$Location `
      environmentName=$EnvironmentName `
      containerAppName=$ContainerAppName `
      acrName=$AcrName `
      logAnalyticsWorkspaceName=$LogAnalyticsWorkspaceName `
      managedIdentityName=$ManagedIdentityName `
    --query properties.outputs `
    --output json 2>&1

if ($LASTEXITCODE -ne 0) {
    $deploymentErrorText = if ($outputsRaw -is [System.Array]) { $outputsRaw -join "`n" } else { [string]$outputsRaw }
    if ($deploymentErrorText -match "Microsoft\.Authorization/roleAssignments/write") {
        throw @"
Azure deployment failed: missing permission to create role assignments.

Your deployment principal needs:
- Role: User Access Administrator (or Owner)
- Scope: resource group '$ResourceGroupName' (or wider scope)

Grant example:
az role assignment create --assignee <AZURE_CLIENT_ID> --role "User Access Administrator" --scope /subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName

Raw Azure error:
$deploymentErrorText
"@
    }

    throw "Azure deployment failed before outputs were returned.`n$deploymentErrorText"
}

$outputsText = if ($outputsRaw -is [System.Array]) { $outputsRaw -join "`n" } else { [string]$outputsRaw }
try {
    $outputs = $outputsText | ConvertFrom-Json
}
catch {
    throw "Failed to parse deployment outputs as JSON.`nRaw output:`n$outputsText"
}

if (-not $outputs -or -not ($outputs.PSObject.Properties.Name -contains "acrLoginServer")) {
    throw "Deployment outputs do not include 'acrLoginServer'. Raw outputs:`n$outputsText"
}

$acrLoginServer = [string]$outputs.acrLoginServer.value

if ([string]::IsNullOrWhiteSpace($acrLoginServer)) {
    throw "Deployment output 'acrLoginServer' is empty. Raw outputs:`n$outputsText"
}

Write-Host "Building image in ACR: ${acrLoginServer}/${ImageRepository}:${ImageTag}"
Push-Location $repoRoot
try {
    az acr build `
        --registry $AcrName `
        --image "${ImageRepository}:${ImageTag}" `
        --file "api/aijuristiction-api/Dockerfile" `
        . `
        --only-show-errors `
        --output none
}
finally {
    Pop-Location
}

$imageRef = "${acrLoginServer}/${ImageRepository}:${ImageTag}"
Write-Host "Updating Container App image: $imageRef"

$envPairs = Convert-EnvFileToPairs -Path $resolvedEnvFilePath

if ($envPairs.Count -gt 0) {
    az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroupName `
        --image $imageRef `
        --set-env-vars $envPairs `
        --only-show-errors `
        --output none
}
else {
    az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroupName `
        --image $imageRef `
        --only-show-errors `
        --output none
}

$fqdn = az containerapp show `
    --name $ContainerAppName `
    --resource-group $ResourceGroupName `
    --query "properties.configuration.ingress.fqdn" `
    --output tsv

Write-Host ""
Write-Host "Deployment complete."
Write-Host "Container App URL: https://$fqdn"
Write-Host "Health check:       https://$fqdn/health"
