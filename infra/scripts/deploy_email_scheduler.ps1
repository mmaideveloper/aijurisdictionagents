[CmdletBinding()]
param(
    [string]$SubscriptionId,
    [string]$ResourceGroupName,
    [string]$Location,
    [string]$ContainerAppEnvironmentName,
    [string]$JobName = "email-scheduler",
    [string]$AcrName,
    [string]$ManagedIdentityName,
    [string]$PostgresServerName,
    [string]$PostgresDatabaseName = "aijurisdiction",
    [string]$PostgresAdminUsername,
    [string]$PostgresAdminPassword,
    [string]$ApplicationInsightsName,
    [string]$EmailTransport = "smtp",
    [string]$EmailSender = "no-reply@jurisdigta.eu",
    [string]$EmailSmtpHost = "mail.webhouse.sk",
    [string]$EmailSmtpPort = "587",
    [string]$EmailSmtpUseTls = "true",
    [string]$EmailSmtpUsername = "no-reply@jurisdigta.eu",
    [string]$EmailSmtpPassword = "",
    [string]$CronExpression = "*/5 * * * *",
    [string]$ImageTag = "latest",
    [string]$EnvFilePath = ".env",
    [switch]$SkipEnvFile,
    [switch]$BuildOnly
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

function Restore-EnvVar {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$PreviousValue
    )

    if ($null -eq $PreviousValue) {
        Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
        return
    }

    Set-Item -Path "Env:$Name" -Value $PreviousValue
}

function Convert-ToPostgresConnectionString {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [string]$DatabaseName,
        [Parameter(Mandatory = $true)]
        [string]$AdminUsername,
        [Parameter(Mandatory = $true)]
        [string]$AdminPassword
    )

    $normalizedHostName = $HostName.Trim().ToLowerInvariant()
    if (-not $normalizedHostName.EndsWith(".postgres.database.azure.com")) {
        $normalizedHostName = "${normalizedHostName}.postgres.database.azure.com"
    }

    $encodedUser = [System.Uri]::EscapeDataString($AdminUsername)
    $encodedPassword = [System.Uri]::EscapeDataString($AdminPassword)
    return "postgresql://${encodedUser}:${encodedPassword}@${normalizedHostName}:5432/${DatabaseName}?sslmode=require"
}

function Resolve-AcaCronExpression {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$DefaultValue
    )

    $resolved = if ([string]::IsNullOrWhiteSpace($Value)) { $DefaultValue } else { $Value.Trim() }
    $parts = @($resolved -split '\s+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    if ($parts.Count -eq 6) {
        if ($parts[0] -ne "0") {
            throw "$Name must use a 5-field ACA cron expression. If a 6-field value is provided, the first field must be 0 seconds."
        }

        $resolved = ($parts[1..5] -join ' ')
        Write-Host "Normalized $Name from 6 fields to ACA 5-field cron: $resolved"
        $parts = @($resolved -split '\s+')
    }

    if ($parts.Count -ne 5) {
        throw "$Name must be a 5-field ACA cron expression, for example '*/5 * * * *'."
    }

    return ($parts -join ' ')
}

function Resolve-AcaJobName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowEmptyString()]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$DefaultValue
    )

    $raw = if ([string]::IsNullOrWhiteSpace($Value)) { $DefaultValue } else { $Value.Trim() }
    $resolved = $raw.ToLowerInvariant()
    $resolved = [regex]::Replace($resolved, '[^a-z0-9-]+', '-')
    $resolved = [regex]::Replace($resolved, '-{2,}', '-')
    $resolved = $resolved.Trim('-')

    if ($raw -ne $resolved) {
        Write-Host "Normalized $Name from '$raw' to '$resolved'"
    }

    if (
        [string]::IsNullOrWhiteSpace($resolved) -or
        $resolved.Length -lt 2 -or
        $resolved.Length -gt 32 -or
        $resolved.Contains('--') -or
        $resolved[0] -notmatch '[a-z]' -or
        $resolved[$resolved.Length - 1] -notmatch '[a-z0-9]'
    ) {
        throw "$Name must be 2-32 characters, use lowercase alphanumeric or '-', start with a letter, end with alphanumeric, and not contain '--'. Resolved value: '$resolved'."
    }

    return $resolved
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

function Publish-EmailSchedulerImage {
    param(
        [Parameter(Mandatory = $true)][string]$RegistryName,
        [Parameter(Mandatory = $true)][string]$Tag
    )

    $repository = "aijuristiction-api"
    $imageReference = "$RegistryName.azurecr.io/$repository`:$Tag"
    Write-Host "Building email scheduler image in ACR: $imageReference"
    az acr build `
      --registry $RegistryName `
      --image "$repository`:$Tag" `
      --file "api/aijuristiction-api/Dockerfile" `
      . `
      --no-logs `
      --only-show-errors `
      --output none | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "ACR build failed for email scheduler image '$imageReference'."
    }

    return $imageReference
}

Assert-ToolInstalled -ToolName "az"
Assert-ToolInstalled -ToolName "python"

$envSubscriptionId = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_SUBSCRIPTION_ID" }
$envResourceGroup = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_RESOURCE_GROUP" }
$envLocation = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_LOCATION" }
$envContainerEnv = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_CONTAINERAPPS_ENVIRONMENT" }
$envAcr = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_CONTAINER_REGISTRY" }
$envIdentity = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_MANAGED_IDENTITY_NAME" }
$envPgServer = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_POSTGRES_SERVER_NAME" }
$envPgDb = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_POSTGRES_DATABASE_NAME" }
$envPgUser = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_POSTGRES_ADMIN_USERNAME" }
$envPgPass = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_POSTGRES_ADMIN_PASSWORD" }
$envApplicationInsightsName = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_APPLICATION_INSIGHTS_NAME" }
$envEmailTransport = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "EMAIL_TRANSPORT" }
$envEmailSender = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "EMAIL_SENDER" }
$envEmailSmtpHost = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "EMAIL_SMTP_HOST" }
$envEmailSmtpPort = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "EMAIL_SMTP_PORT" }
$envEmailSmtpUseTls = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "EMAIL_SMTP_USE_TLS" }
$envEmailSmtpUsername = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "EMAIL_SMTP_USERNAME" }
$envEmailSmtpPassword = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "EMAIL_SMTP_PASSWORD" }
$envJobName = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_EMAIL_SCHEDULER_JOB_NAME" }
$envCronExpression = if ($SkipEnvFile) { "" } else { Get-ValueFromEnvFile -Path $EnvFilePath -Key "AZURE_EMAIL_SCHEDULER_CRON_EXPRESSION" }

$SubscriptionId = Resolve-InputValue -ExplicitValue $SubscriptionId -EnvFileValue $envSubscriptionId -EnvironmentValue $env:AZURE_SUBSCRIPTION_ID
$ResourceGroupName = Resolve-InputValue -ExplicitValue $ResourceGroupName -EnvFileValue $envResourceGroup -EnvironmentValue $env:AZURE_RESOURCE_GROUP
$Location = Resolve-InputValue -ExplicitValue $Location -EnvFileValue $envLocation -EnvironmentValue $env:AZURE_LOCATION
$ContainerAppEnvironmentName = Resolve-InputValue -ExplicitValue $ContainerAppEnvironmentName -EnvFileValue $envContainerEnv -EnvironmentValue $env:AZURE_CONTAINERAPPS_ENVIRONMENT
$JobName = Resolve-InputValue -ExplicitValue $JobName -EnvFileValue $envJobName -EnvironmentValue $env:AZURE_EMAIL_SCHEDULER_JOB_NAME
$AcrName = Resolve-InputValue -ExplicitValue $AcrName -EnvFileValue $envAcr -EnvironmentValue $env:AZURE_CONTAINER_REGISTRY
$ManagedIdentityName = Resolve-InputValue -ExplicitValue $ManagedIdentityName -EnvFileValue $envIdentity -EnvironmentValue $env:AZURE_MANAGED_IDENTITY_NAME
$PostgresServerName = Resolve-InputValue -ExplicitValue $PostgresServerName -EnvFileValue $envPgServer -EnvironmentValue $env:AZURE_POSTGRES_SERVER_NAME
$PostgresDatabaseName = Resolve-InputValue -ExplicitValue $PostgresDatabaseName -EnvFileValue $envPgDb -EnvironmentValue $env:AZURE_POSTGRES_DATABASE_NAME
$PostgresAdminUsername = Resolve-InputValue -ExplicitValue $PostgresAdminUsername -EnvFileValue $envPgUser -EnvironmentValue $env:AZURE_POSTGRES_ADMIN_USERNAME
$PostgresAdminPassword = Resolve-InputValue -ExplicitValue $PostgresAdminPassword -EnvFileValue $envPgPass -EnvironmentValue $env:AZURE_POSTGRES_ADMIN_PASSWORD
$ApplicationInsightsName = Resolve-InputValue -ExplicitValue $ApplicationInsightsName -EnvFileValue $envApplicationInsightsName -EnvironmentValue $env:AZURE_APPLICATION_INSIGHTS_NAME
$EmailTransport = Resolve-InputValue -ExplicitValue $EmailTransport -EnvFileValue $envEmailTransport -EnvironmentValue $env:EMAIL_TRANSPORT
$EmailSender = Resolve-InputValue -ExplicitValue $EmailSender -EnvFileValue $envEmailSender -EnvironmentValue $env:EMAIL_SENDER
$EmailSmtpHost = Resolve-InputValue -ExplicitValue $EmailSmtpHost -EnvFileValue $envEmailSmtpHost -EnvironmentValue $env:EMAIL_SMTP_HOST
$EmailSmtpPort = Resolve-InputValue -ExplicitValue $EmailSmtpPort -EnvFileValue $envEmailSmtpPort -EnvironmentValue $env:EMAIL_SMTP_PORT
$EmailSmtpUseTls = Resolve-InputValue -ExplicitValue $EmailSmtpUseTls -EnvFileValue $envEmailSmtpUseTls -EnvironmentValue $env:EMAIL_SMTP_USE_TLS
$EmailSmtpUsername = Resolve-InputValue -ExplicitValue $EmailSmtpUsername -EnvFileValue $envEmailSmtpUsername -EnvironmentValue $env:EMAIL_SMTP_USERNAME
$EmailSmtpPassword = Resolve-InputValue -ExplicitValue $EmailSmtpPassword -EnvFileValue $envEmailSmtpPassword -EnvironmentValue $env:EMAIL_SMTP_PASSWORD
$CronExpression = Resolve-InputValue -ExplicitValue $CronExpression -EnvFileValue $envCronExpression -EnvironmentValue $env:AZURE_EMAIL_SCHEDULER_CRON_EXPRESSION

if ([string]::IsNullOrWhiteSpace($Location)) { $Location = "westeurope" }
if ([string]::IsNullOrWhiteSpace($JobName)) { $JobName = "email-scheduler" }
if ([string]::IsNullOrWhiteSpace($PostgresDatabaseName)) { $PostgresDatabaseName = "aijurisdiction" }
if ([string]::IsNullOrWhiteSpace($EmailTransport)) { $EmailTransport = "smtp" }
if ([string]::IsNullOrWhiteSpace($EmailSender)) { $EmailSender = "no-reply@jurisdigta.eu" }
if ([string]::IsNullOrWhiteSpace($EmailSmtpHost)) { $EmailSmtpHost = "mail.webhouse.sk" }
if ([string]::IsNullOrWhiteSpace($EmailSmtpPort)) { $EmailSmtpPort = "587" }
if ([string]::IsNullOrWhiteSpace($EmailSmtpUseTls)) { $EmailSmtpUseTls = "true" }
if ([string]::IsNullOrWhiteSpace($EmailSmtpUsername)) { $EmailSmtpUsername = "no-reply@jurisdigta.eu" }
if (-not $BuildOnly) {
    $JobName = Resolve-AcaJobName -Name "JobName" -Value $JobName -DefaultValue "email-scheduler"
    $CronExpression = Resolve-AcaCronExpression -Name "CronExpression" -Value $CronExpression -DefaultValue "*/5 * * * *"
}

Require-Value -Name "SubscriptionId" -Value $SubscriptionId
Require-Value -Name "AcrName" -Value $AcrName
if (-not $BuildOnly) {
    Require-Value -Name "ResourceGroupName" -Value $ResourceGroupName
    Require-Value -Name "Location" -Value $Location
    Require-Value -Name "ContainerAppEnvironmentName" -Value $ContainerAppEnvironmentName
    Require-Value -Name "ManagedIdentityName" -Value $ManagedIdentityName
    Require-Value -Name "PostgresServerName" -Value $PostgresServerName
    Require-Value -Name "PostgresDatabaseName" -Value $PostgresDatabaseName
    Require-Value -Name "PostgresAdminUsername" -Value $PostgresAdminUsername
    Require-Value -Name "PostgresAdminPassword" -Value $PostgresAdminPassword
    if ($EmailTransport.Trim().ToLowerInvariant() -eq "smtp") {
        Require-Value -Name "EmailSmtpPassword" -Value $EmailSmtpPassword
    }
}

az account set --subscription $SubscriptionId | Out-Null
$image = Publish-EmailSchedulerImage -RegistryName $AcrName -Tag $ImageTag

if ($BuildOnly) {
    Write-Host "Email scheduler image build complete. Deployment was not requested."
    Write-WorkflowSummary -Lines @(
        "## ACR image build summary",
        "| Image | Result | Deployment |",
        "| --- | --- | --- |",
        "| $image | uploaded | skipped |"
    )
    return
}

$resourceGroupExists = az group exists --name $ResourceGroupName --output tsv
if ($resourceGroupExists -eq "true") {
    Write-Host "Resource group '$ResourceGroupName' already exists. Skipping creation."
}
else {
    Write-Host "Creating resource group '$ResourceGroupName' in '$Location'..."
    az group create --name $ResourceGroupName --location $Location --only-show-errors --output none
}

$jobExistedBeforeDeployment = Test-ResourceExistsInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $JobName `
    -ResourceType "Microsoft.App/jobs"

$dbCloud = Convert-ToPostgresConnectionString `
    -HostName $PostgresServerName `
    -DatabaseName $PostgresDatabaseName `
    -AdminUsername $PostgresAdminUsername `
    -AdminPassword $PostgresAdminPassword

$applicationInsightsConnectionString = ""
if (-not [string]::IsNullOrWhiteSpace($ApplicationInsightsName)) {
    $applicationInsightsConnectionString = az monitor app-insights component show `
      --app $ApplicationInsightsName `
      --resource-group $ResourceGroupName `
      --query connectionString `
      --output tsv 2>$null
    if ($LASTEXITCODE -ne 0) {
        $applicationInsightsConnectionString = ""
    }
}

Write-Host "Applying email schema migrations to Azure PostgreSQL..."
$previousDbOption = $env:DB_OPTION
$previousDbCloud = $env:DB_CLOUD
try {
    $env:DB_OPTION = "azure"
    $env:DB_CLOUD = $dbCloud
    python "scripts/databases/apply_db_migrations.py" --project email
    if ($LASTEXITCODE -ne 0) {
        throw "Email schema migration failed for database '$PostgresDatabaseName'."
    }
}
finally {
    Restore-EnvVar -Name "DB_OPTION" -PreviousValue $previousDbOption
    Restore-EnvVar -Name "DB_CLOUD" -PreviousValue $previousDbCloud
}

Write-Host "Deploying email scheduler ACA job: $JobName"
az deployment group create `
  --resource-group $ResourceGroupName `
  --template-file "infra/bicep/email_scheduler.job.bicep" `
  --parameters `
      location=$Location `
      managedEnvironmentName=$ContainerAppEnvironmentName `
      jobName=$JobName `
      acrName=$AcrName `
      managedIdentityName=$ManagedIdentityName `
      image=$image `
      runScheduler=true `
      postgresServerName=$PostgresServerName `
      postgresDatabaseName=$PostgresDatabaseName `
      postgresAdminUsername=$PostgresAdminUsername `
      postgresAdminPassword=$PostgresAdminPassword `
      postgresConnectionString=$dbCloud `
      applicationInsightsConnectionString=$applicationInsightsConnectionString `
      emailTransport=$EmailTransport `
      emailSender=$EmailSender `
      emailSmtpHost=$EmailSmtpHost `
      emailSmtpPort=$EmailSmtpPort `
      emailSmtpUseTls=$EmailSmtpUseTls `
      emailSmtpUsername=$EmailSmtpUsername `
      emailSmtpPassword=$EmailSmtpPassword `
      cronExpression=$CronExpression | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Email scheduler ACA job deployment failed."
}

$jobDisposition = if ($jobExistedBeforeDeployment) { "updated" } else { "created" }

Write-Host "Email scheduler deployment complete."
Write-Host "ACA resources:"
Write-Host " - Managed environment (reused): $ContainerAppEnvironmentName"
Write-Host " - Email scheduler ACA job ($jobDisposition): $JobName"

Write-WorkflowSummary -Lines @(
    "## ACA deployment summary",
    "| Resource | Name | Result | Endpoint |",
    "| --- | --- | --- | --- |",
    "| Managed environment | $ContainerAppEnvironmentName | reused | n/a |",
    "| Email scheduler ACA job | $JobName | $jobDisposition | schedule: $CronExpression |"
)
