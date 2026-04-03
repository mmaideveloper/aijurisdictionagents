[CmdletBinding()]
param(
    [string]$SubscriptionId,
    [string]$ResourceGroupName,
    [string]$Location,
    [string]$ContainerAppEnvironmentName,
    [string]$ContainerAppName = "laws-collector",
    [string]$AcrName,
    [string]$ManagedIdentityName,
    [string]$PostgresServerName,
    [string]$PostgresDatabaseName = "laws_sk",
    [string]$PostgresAdminUsername,
    [string]$PostgresAdminPassword,
    [string]$SystemEmbeddingModelOption = "cloud",
    [string]$SystemEmbeddingModel = "all-MiniLM-L6-v2",
    [string]$CronExpression = "0 0 * * *",
    [string]$WorkerMaxProbes = "",
    [string]$ImageTag = "latest",
    [string]$EnvFilePath = ".env",
    [switch]$SkipEnvFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-ToolInstalled {
    param([Parameter(Mandatory = $true)][string]$ToolName)
    if (-not (Get-Command $ToolName -ErrorAction SilentlyContinue)) {
        throw "Missing required tool '$ToolName'."
    }
}

function Get-ValueFromEnvFile {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -Path $Path)) { return "" }
    $pattern = "^\s*$Key=(?<value>.*)$"
    $line = Get-Content -Path $Path | Where-Object { $_ -match $pattern } | Select-Object -First 1
    if (-not $line) { return "" }
    $value = [regex]::Match($line, $pattern).Groups["value"].Value.Trim()
    if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) {
        if ($value.Length -ge 2) { $value = $value.Substring(1, $value.Length - 2) }
    }
    return $value
}

function Resolve-InputValue {
    param([string]$ExplicitValue, [string]$EnvFileValue, [string]$EnvironmentValue)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitValue)) { return $ExplicitValue }
    if (-not [string]::IsNullOrWhiteSpace($EnvFileValue)) { return $EnvFileValue }
    return $EnvironmentValue
}

function Require-Value {
    param([string]$Name, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required. Pass parameter, set in .env, or export env var."
    }
}

function Resolve-PositiveInteger {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$Value,
        [int]$DefaultValue = 1
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $DefaultValue
    }

    $parsed = 0
    if (-not [int]::TryParse($Value, [ref]$parsed) -or $parsed -lt 1) {
        throw "$Name must be an integer >= 1."
    }

    return $parsed
}

function Test-ResourceExistsInGroup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResourceGroupName,
        [Parameter(Mandatory = $true)]
        [string]$ResourceName,
        [Parameter(Mandatory = $true)]
        [string]$ResourceType
    )

    az resource show `
        --resource-group $ResourceGroupName `
        --name $ResourceName `
        --resource-type $ResourceType `
        --query id `
        --output tsv 2>$null | Out-Null

    return ($LASTEXITCODE -eq 0)
}

function Write-WorkflowSummary {
    param([Parameter(Mandatory = $true)][string[]]$Lines)
    if ([string]::IsNullOrWhiteSpace($env:GITHUB_STEP_SUMMARY)) { return }
    $nonEmptyLines = @($Lines | Where-Object { $_ -ne $null })
    (($nonEmptyLines -join [Environment]::NewLine) + [Environment]::NewLine + [Environment]::NewLine) |
        Out-File -FilePath $env:GITHUB_STEP_SUMMARY -Append -Encoding utf8
}

Assert-ToolInstalled -ToolName "az"

$envSubscriptionId = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_SUBSCRIPTION_ID" }
$envResourceGroup = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_RESOURCE_GROUP" }
$envLocation = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_LOCATION" }
$envContainerEnv = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_CONTAINERAPPS_ENVIRONMENT" }
$envAcr = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_CONTAINER_REGISTRY" }
$envIdentity = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_MANAGED_IDENTITY_NAME" }
$envPgServer = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_POSTGRES_SERVER_NAME" }
$envPgDb = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_LAWS_POSTGRES_DATABASE_NAME_SK" }
$envPgUser = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_POSTGRES_ADMIN_USERNAME" }
$envPgPass = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_POSTGRES_ADMIN_PASSWORD" }
$envSystemEmbeddingModelOption = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "SYSTEM_EMBEDDING_MODEL_OPTION" }
$envSystemEmbeddingModel = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "SYSTEM_EMBEDDING_MODEL" }
$envWorkerMaxProbes = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_LAWS_COLLECTOR_MAX_PROBES" }

$SubscriptionId = Resolve-InputValue -ExplicitValue $SubscriptionId -EnvFileValue $envSubscriptionId -EnvironmentValue $env:AZURE_SUBSCRIPTION_ID
$ResourceGroupName = Resolve-InputValue -ExplicitValue $ResourceGroupName -EnvFileValue $envResourceGroup -EnvironmentValue $env:AZURE_RESOURCE_GROUP
$Location = Resolve-InputValue -ExplicitValue $Location -EnvFileValue $envLocation -EnvironmentValue $env:AZURE_LOCATION
$ContainerAppEnvironmentName = Resolve-InputValue -ExplicitValue $ContainerAppEnvironmentName -EnvFileValue $envContainerEnv -EnvironmentValue $env:AZURE_CONTAINERAPPS_ENVIRONMENT
$AcrName = Resolve-InputValue -ExplicitValue $AcrName -EnvFileValue $envAcr -EnvironmentValue $env:AZURE_CONTAINER_REGISTRY
$ManagedIdentityName = Resolve-InputValue -ExplicitValue $ManagedIdentityName -EnvFileValue $envIdentity -EnvironmentValue $env:AZURE_MANAGED_IDENTITY_NAME
$PostgresServerName = Resolve-InputValue -ExplicitValue $PostgresServerName -EnvFileValue $envPgServer -EnvironmentValue $env:AZURE_POSTGRES_SERVER_NAME
$PostgresDatabaseName = Resolve-InputValue -ExplicitValue $PostgresDatabaseName -EnvFileValue $envPgDb -EnvironmentValue $env:AZURE_LAWS_POSTGRES_DATABASE_NAME_SK
$PostgresAdminUsername = Resolve-InputValue -ExplicitValue $PostgresAdminUsername -EnvFileValue $envPgUser -EnvironmentValue $env:AZURE_POSTGRES_ADMIN_USERNAME
$PostgresAdminPassword = Resolve-InputValue -ExplicitValue $PostgresAdminPassword -EnvFileValue $envPgPass -EnvironmentValue $env:AZURE_POSTGRES_ADMIN_PASSWORD
$SystemEmbeddingModelOption = Resolve-InputValue -ExplicitValue $SystemEmbeddingModelOption -EnvFileValue $envSystemEmbeddingModelOption -EnvironmentValue $env:SYSTEM_EMBEDDING_MODEL_OPTION
$SystemEmbeddingModel = Resolve-InputValue -ExplicitValue $SystemEmbeddingModel -EnvFileValue $envSystemEmbeddingModel -EnvironmentValue $env:SYSTEM_EMBEDDING_MODEL
$WorkerMaxProbes = Resolve-InputValue -ExplicitValue $WorkerMaxProbes -EnvFileValue $envWorkerMaxProbes -EnvironmentValue $env:AZURE_LAWS_COLLECTOR_MAX_PROBES

Require-Value -Name "SubscriptionId" -Value $SubscriptionId
Require-Value -Name "ResourceGroupName" -Value $ResourceGroupName
Require-Value -Name "Location" -Value $Location
Require-Value -Name "ContainerAppEnvironmentName" -Value $ContainerAppEnvironmentName
Require-Value -Name "AcrName" -Value $AcrName
Require-Value -Name "ManagedIdentityName" -Value $ManagedIdentityName
Require-Value -Name "PostgresServerName" -Value $PostgresServerName
Require-Value -Name "PostgresDatabaseName" -Value $PostgresDatabaseName
Require-Value -Name "PostgresAdminUsername" -Value $PostgresAdminUsername
Require-Value -Name "PostgresAdminPassword" -Value $PostgresAdminPassword
if ([string]::IsNullOrWhiteSpace($SystemEmbeddingModelOption)) { $SystemEmbeddingModelOption = "cloud" }
if ([string]::IsNullOrWhiteSpace($SystemEmbeddingModel)) { $SystemEmbeddingModel = "all-MiniLM-L6-v2" }
$WorkerMaxProbes = Resolve-PositiveInteger -Name "WorkerMaxProbes" -Value $WorkerMaxProbes -DefaultValue 1

az account set --subscription $SubscriptionId | Out-Null
$resourceGroupExists = az group exists --name $ResourceGroupName --output tsv
if ($resourceGroupExists -eq "true") {
    Write-Host "Resource group '$ResourceGroupName' already exists. Skipping creation."
}
else {
    Write-Host "Creating resource group '$ResourceGroupName' in '$Location'..."
    az group create --name $ResourceGroupName --location $Location --only-show-errors --output none
}

$containerAppExistedBeforeDeployment = Test-ResourceExistsInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $ContainerAppName `
    -ResourceType "Microsoft.App/jobs"

$imageRepository = "laws-collector"
$image = "$AcrName.azurecr.io/$imageRepository`:$ImageTag"

Write-Host "Building laws collector image in ACR: $image"
az acr build `
  --registry $AcrName `
  --image "$imageRepository`:$ImageTag" `
  --file "src/services/laws_collector/Dockerfile" `
  . `
  --no-logs `
  --only-show-errors `
  --output none
if ($LASTEXITCODE -ne 0) {
    throw "ACR build failed for laws collector image '$image'."
}

Write-Host "Deploying laws collector ACA job: $ContainerAppName"
az deployment group create `
  --resource-group $ResourceGroupName `
  --template-file "infra/bicep/laws_collector.job.bicep" `
  --parameters `
      location=$Location `
      managedEnvironmentName=$ContainerAppEnvironmentName `
      jobName=$ContainerAppName `
      acrName=$AcrName `
      managedIdentityName=$ManagedIdentityName `
      image=$image `
      postgresServerName=$PostgresServerName `
      postgresDatabaseName=$PostgresDatabaseName `
      postgresAdminUsername=$PostgresAdminUsername `
      postgresAdminPassword=$PostgresAdminPassword `
      systemEmbeddingModelOption=$SystemEmbeddingModelOption `
      systemEmbeddingModel=$SystemEmbeddingModel `
      cronExpression=$CronExpression `
      workerMaxProbes=$WorkerMaxProbes | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Laws collector ACA job deployment failed."
}

$containerAppDisposition = if ($containerAppExistedBeforeDeployment) { "updated" } else { "created" }

Write-Host "Laws collector deployment complete."
Write-Host "ACA resources:"
Write-Host " - Managed environment (reused): $ContainerAppEnvironmentName"
Write-Host " - Laws collector ACA job ($containerAppDisposition): $ContainerAppName"

Write-WorkflowSummary -Lines @(
    "## ACA deployment summary",
    "| Resource | Name | Result | Endpoint |",
    "| --- | --- | --- | --- |",
    "| Managed environment | $ContainerAppEnvironmentName | reused | n/a |",
    "| Laws collector ACA job | $ContainerAppName | $containerAppDisposition | schedule-driven |"
)
