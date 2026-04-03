[CmdletBinding()]
param(
    [string]$SubscriptionId,
    [string]$Location,
    [string]$ResourceGroupName,
    [string]$EnvironmentName,
    [string]$ContainerAppName,
    [string]$PostgresServerName,
    [string]$PostgresDatabaseName,
    [string]$PostgresAdminUsername,
    [string]$PostgresAdminPassword,
    [string]$PostgresSkuName,
    [string]$PostgresSkuTier,
    [string]$PostgresVersion,
    [string]$PostgresStorageSizeGb,
    [string]$AcrName,
    [string]$StorageAccountName,
    [string]$StorageContainerName,
    [string]$LogAnalyticsWorkspaceName,
    [string]$ApplicationInsightsName,
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

function Get-DefaultStorageAccountName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Seed
    )

    $normalizedSeed = $Seed.Trim().ToLower()
    $prefix = ($normalizedSeed -replace "[^a-z0-9]", "")
    if ([string]::IsNullOrWhiteSpace($prefix)) {
        $prefix = "aijur"
    }
    if ($prefix.Length -gt 10) {
        $prefix = $prefix.Substring(0, 10)
    }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalizedSeed)
        $hash = [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").ToLower()
    }
    finally {
        $sha.Dispose()
    }

    $suffix = $hash.Substring(0, 10)
    return "st${prefix}${suffix}"
}

function Normalize-StorageAccountName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputName
    )

    $sanitized = ($InputName.Trim().ToLower() -replace "[^a-z0-9]", "")
    if ([string]::IsNullOrWhiteSpace($sanitized)) {
        throw "Storage account name '$InputName' is invalid after sanitization. Use 3-24 lowercase alphanumeric characters."
    }

    if ($sanitized.Length -lt 3) {
        $sanitized = ($sanitized + "stg").Substring(0, 3)
    }

    if ($sanitized.Length -gt 24) {
        $sanitized = $sanitized.Substring(0, 24)
    }

    return $sanitized
}

function Normalize-StorageContainerName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputName
    )

    $sanitized = $InputName.Trim().ToLower()
    if ($sanitized -notmatch '^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$') {
        throw "Storage container name '$InputName' is invalid. Use 3-63 chars: lowercase letters, digits, and hyphens."
    }

    if ($sanitized.Contains("--")) {
        throw "Storage container name '$InputName' is invalid. Consecutive hyphens are not allowed."
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

function Restore-EnvVar {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$PreviousValue
    )

    if ($null -eq $PreviousValue) {
        Remove-Item -Path "Env:$Name" -ErrorAction SilentlyContinue
        return
    }

    Set-Item -Path "Env:$Name" -Value $PreviousValue
}

function Write-WorkflowSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Lines
    )

    if ([string]::IsNullOrWhiteSpace($env:GITHUB_STEP_SUMMARY)) {
        return
    }

    (($Lines -join [Environment]::NewLine) + [Environment]::NewLine + [Environment]::NewLine) |
        Out-File -FilePath $env:GITHUB_STEP_SUMMARY -Append -Encoding utf8
}

function Get-JsonPayloadFromCliOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RawText
    )

    $trimmed = $RawText.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        throw "CLI output was empty."
    }

    $firstObjectStart = $trimmed.IndexOf("{")
    $firstArrayStart = $trimmed.IndexOf("[")

    $startIndex = -1
    if ($firstObjectStart -ge 0 -and $firstArrayStart -ge 0) {
        $startIndex = [Math]::Min($firstObjectStart, $firstArrayStart)
    }
    elseif ($firstObjectStart -ge 0) {
        $startIndex = $firstObjectStart
    }
    else {
        $startIndex = $firstArrayStart
    }

    if ($startIndex -lt 0) {
        throw "CLI output did not contain JSON."
    }

    $jsonCandidate = $trimmed.Substring($startIndex).Trim()
    $lastObjectEnd = $jsonCandidate.LastIndexOf("}")
    $lastArrayEnd = $jsonCandidate.LastIndexOf("]")
    $endIndex = [Math]::Max($lastObjectEnd, $lastArrayEnd)
    if ($endIndex -lt 0) {
        throw "CLI output contained an incomplete JSON payload."
    }

    return $jsonCandidate.Substring(0, $endIndex + 1)
}

function Get-PublicIpAddress {
    try {
        return [string](Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 10)
    }
    catch {
        return ""
    }
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

    $normalizedHostName = $HostName.Trim().ToLower()
    if (-not $normalizedHostName.EndsWith(".postgres.database.azure.com")) {
        $normalizedHostName = "${normalizedHostName}.postgres.database.azure.com"
    }

    $normalizedAdminUsername = $AdminUsername.Trim()

    $encodedUser = [System.Uri]::EscapeDataString($normalizedAdminUsername)
    $encodedPassword = [System.Uri]::EscapeDataString($AdminPassword)
    return "postgresql://${encodedUser}:${encodedPassword}@${normalizedHostName}:5432/${DatabaseName}?sslmode=require"
}

function Get-ResourceLocationInGroup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResourceGroupName,
        [Parameter(Mandatory = $true)]
        [string]$ResourceName,
        [Parameter(Mandatory = $true)]
        [string]$ResourceType
    )

    $location = az resource show `
        --resource-group $ResourceGroupName `
        --name $ResourceName `
        --resource-type $ResourceType `
        --query location `
        --output tsv 2>$null

    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$location)) {
        return ""
    }

    return [string]$location
}

function Normalize-LocationName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Location
    )

    return (($Location -replace "\s+", "").Trim().ToLowerInvariant())
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
        "OPENAI_EMBEDDINGS_MODEL",
        "OPENAI_TEMPERATURE",
        "SYSTEM_EMBEDDING_MODEL_OPTION",
        "SYSTEM_EMBEDDING_MODEL",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_EMBEDDINGS_MODEL",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_AD_TOKEN",
        "AZURE_OPENAI_API_VERSION",
        "OPENAI_API_VERSION",
        "DB_OPTION",
        "DB_CLOUD",
        "STORAGE_OPTION",
        "STORE_CLOUD"
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

function Wait-ForAcrImage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RegistryName,
        [Parameter(Mandatory = $true)]
        [string]$Repository,
        [Parameter(Mandatory = $true)]
        [string]$Tag,
        [int]$MaxAttempts = 12,
        [int]$DelaySeconds = 5
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $checkRaw = az acr repository show `
            --name $RegistryName `
            --image "${Repository}:${Tag}" `
            --output json 2>$null

        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace([string]$checkRaw)) {
            return $true
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    return $false
}

function Build-AndPushImage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RegistryName,
        [Parameter(Mandatory = $true)]
        [string]$AcrLoginServer,
        [Parameter(Mandatory = $true)]
        [string]$Repository,
        [Parameter(Mandatory = $true)]
        [string]$Tag,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$BuildContextPath,
        [Parameter(Mandatory = $true)]
        [string]$DockerfilePath
    )

    $fullImageRef = "${AcrLoginServer}/${Repository}:${Tag}"

    Push-Location $RepoRoot
    try {
        $acrBuildRaw = az acr build `
            --registry $RegistryName `
            --image "${Repository}:${Tag}" `
            --file $DockerfilePath `
            $BuildContextPath `
            --no-logs `
            --only-show-errors `
            --output json 2>&1

        if ($LASTEXITCODE -eq 0) {
            return
        }

        $acrBuildErrorText = if ($acrBuildRaw -is [System.Array]) { $acrBuildRaw -join "`n" } else { [string]$acrBuildRaw }
        $isSasAuthError = ($acrBuildErrorText -match "AuthenticationFailed") -and ($acrBuildErrorText -match "Signed expiry time")

        if (-not $isSasAuthError) {
            throw "ACR build failed for image '${Repository}:${Tag}'.`n$acrBuildErrorText"
        }

        Write-Host "Detected ACR task SAS authentication issue. Falling back to local Docker build/push..."
        Assert-ToolInstalled -ToolName "docker"

        az acr login --name $RegistryName --only-show-errors --output none
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to login to ACR '$RegistryName' before Docker fallback."
        }

        docker build -t $fullImageRef -f $DockerfilePath $BuildContextPath
        if ($LASTEXITCODE -ne 0) {
            throw "Docker build failed for image '$fullImageRef'."
        }

        docker push $fullImageRef
        if ($LASTEXITCODE -ne 0) {
            throw "Docker push failed for image '$fullImageRef'."
        }
    }
    finally {
        Pop-Location
    }
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
$postgresServerNameFromEnvFile = ""
$postgresDatabaseNameFromEnvFile = ""
$postgresAdminUsernameFromEnvFile = ""
$postgresAdminPasswordFromEnvFile = ""
$postgresSkuNameFromEnvFile = ""
$postgresSkuTierFromEnvFile = ""
$postgresVersionFromEnvFile = ""
$postgresStorageSizeGbFromEnvFile = ""
$acrNameFromEnvFile = ""
$storageAccountNameFromEnvFile = ""
$storageContainerNameFromEnvFile = ""
$logAnalyticsWorkspaceFromEnvFile = ""
$applicationInsightsNameFromEnvFile = ""
$managedIdentityNameFromEnvFile = ""
$imageTagFromEnvFile = ""
$clientIdFromEnvFile = ""

if (-not $SkipEnvFile -and (Test-Path -Path $resolvedEnvFilePath)) {
    $subscriptionIdFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_SUBSCRIPTION_ID"
    $locationFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_LOCATION"
    $resourceGroupFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_RESOURCE_GROUP"
    $environmentNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CONTAINERAPPS_ENVIRONMENT"
    $containerAppNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CONTAINER_APP_NAME"
    $postgresServerNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_SERVER_NAME"
    $postgresDatabaseNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_DATABASE_NAME"
    $postgresAdminUsernameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_ADMIN_USERNAME"
    $postgresAdminPasswordFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_ADMIN_PASSWORD"
    $postgresSkuNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_SKU_NAME"
    $postgresSkuTierFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_SKU_TIER"
    $postgresVersionFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_VERSION"
    $postgresStorageSizeGbFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_POSTGRES_STORAGE_SIZE_GB"
    $acrNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CONTAINER_REGISTRY"
    $storageAccountNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_STORAGE_ACCOUNT_NAME"
    $storageContainerNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_STORAGE_CONTAINER_NAME"
    $logAnalyticsWorkspaceFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_LOG_ANALYTICS_WORKSPACE_NAME"
    $applicationInsightsNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_APPLICATION_INSIGHTS_NAME"
    $managedIdentityNameFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_MANAGED_IDENTITY_NAME"
    $imageTagFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_API_IMAGE_TAG"
    $clientIdFromEnvFile = Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "AZURE_CLIENT_ID"
}

$SubscriptionId = Resolve-InputValue -ExplicitValue $SubscriptionId -EnvFileValue $subscriptionIdFromEnvFile -EnvironmentValue $env:AZURE_SUBSCRIPTION_ID
$Location = Resolve-InputValue -ExplicitValue $Location -EnvFileValue $locationFromEnvFile -EnvironmentValue $env:AZURE_LOCATION
$ResourceGroupName = Resolve-InputValue -ExplicitValue $ResourceGroupName -EnvFileValue $resourceGroupFromEnvFile -EnvironmentValue $env:AZURE_RESOURCE_GROUP
$EnvironmentName = Resolve-InputValue -ExplicitValue $EnvironmentName -EnvFileValue $environmentNameFromEnvFile -EnvironmentValue $env:AZURE_CONTAINERAPPS_ENVIRONMENT
$ContainerAppName = Resolve-InputValue -ExplicitValue $ContainerAppName -EnvFileValue $containerAppNameFromEnvFile -EnvironmentValue $env:AZURE_CONTAINER_APP_NAME
$PostgresServerName = Resolve-InputValue -ExplicitValue $PostgresServerName -EnvFileValue $postgresServerNameFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_SERVER_NAME
$PostgresDatabaseName = Resolve-InputValue -ExplicitValue $PostgresDatabaseName -EnvFileValue $postgresDatabaseNameFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_DATABASE_NAME
$PostgresAdminUsername = Resolve-InputValue -ExplicitValue $PostgresAdminUsername -EnvFileValue $postgresAdminUsernameFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_ADMIN_USERNAME
$PostgresAdminPassword = Resolve-InputValue -ExplicitValue $PostgresAdminPassword -EnvFileValue $postgresAdminPasswordFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_ADMIN_PASSWORD
$PostgresSkuName = Resolve-InputValue -ExplicitValue $PostgresSkuName -EnvFileValue $postgresSkuNameFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_SKU_NAME
$PostgresSkuTier = Resolve-InputValue -ExplicitValue $PostgresSkuTier -EnvFileValue $postgresSkuTierFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_SKU_TIER
$PostgresVersion = Resolve-InputValue -ExplicitValue $PostgresVersion -EnvFileValue $postgresVersionFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_VERSION
$PostgresStorageSizeGb = Resolve-InputValue -ExplicitValue $PostgresStorageSizeGb -EnvFileValue $postgresStorageSizeGbFromEnvFile -EnvironmentValue $env:AZURE_POSTGRES_STORAGE_SIZE_GB
$AcrName = Resolve-InputValue -ExplicitValue $AcrName -EnvFileValue $acrNameFromEnvFile -EnvironmentValue $env:AZURE_CONTAINER_REGISTRY
$StorageAccountName = Resolve-InputValue -ExplicitValue $StorageAccountName -EnvFileValue $storageAccountNameFromEnvFile -EnvironmentValue $env:AZURE_STORAGE_ACCOUNT_NAME
$StorageContainerName = Resolve-InputValue -ExplicitValue $StorageContainerName -EnvFileValue $storageContainerNameFromEnvFile -EnvironmentValue $env:AZURE_STORAGE_CONTAINER_NAME
$LogAnalyticsWorkspaceName = Resolve-InputValue -ExplicitValue $LogAnalyticsWorkspaceName -EnvFileValue $logAnalyticsWorkspaceFromEnvFile -EnvironmentValue $env:AZURE_LOG_ANALYTICS_WORKSPACE_NAME
$ApplicationInsightsName = Resolve-InputValue -ExplicitValue $ApplicationInsightsName -EnvFileValue $applicationInsightsNameFromEnvFile -EnvironmentValue $env:AZURE_APPLICATION_INSIGHTS_NAME
$ManagedIdentityName = Resolve-InputValue -ExplicitValue $ManagedIdentityName -EnvFileValue $managedIdentityNameFromEnvFile -EnvironmentValue $env:AZURE_MANAGED_IDENTITY_NAME
$ImageTag = Resolve-InputValue -ExplicitValue $ImageTag -EnvFileValue $imageTagFromEnvFile -EnvironmentValue $env:AZURE_API_IMAGE_TAG
$ExpectedServicePrincipalClientId = Resolve-InputValue -ExplicitValue "" -EnvFileValue $clientIdFromEnvFile -EnvironmentValue $env:AZURE_CLIENT_ID

if ([string]::IsNullOrWhiteSpace($Location)) {
    $Location = "westeurope"
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
if ([string]::IsNullOrWhiteSpace($PostgresServerName)) {
    $PostgresServerName = "db-juris-dev"
}
if ([string]::IsNullOrWhiteSpace($PostgresDatabaseName)) {
    $PostgresDatabaseName = "aijurisdiction"
}
if ([string]::IsNullOrWhiteSpace($PostgresAdminUsername)) {
    $PostgresAdminUsername = "jurisadmin"
}
if ([string]::IsNullOrWhiteSpace($PostgresSkuName)) {
    $PostgresSkuName = "Standard_B1ms"
}
if ([string]::IsNullOrWhiteSpace($PostgresSkuTier)) {
    $PostgresSkuTier = "Burstable"
}
if ([string]::IsNullOrWhiteSpace($PostgresVersion)) {
    $PostgresVersion = "16"
}
if ([string]::IsNullOrWhiteSpace($PostgresStorageSizeGb)) {
    $PostgresStorageSizeGb = "32"
}
if ([string]::IsNullOrWhiteSpace($LogAnalyticsWorkspaceName)) {
    $LogAnalyticsWorkspaceName = "log-aijurisdiction-dev"
}
if ([string]::IsNullOrWhiteSpace($ApplicationInsightsName)) {
    $ApplicationInsightsName = "ai-juris-dev"
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
Require-Value -Name "PostgresAdminPassword" -Value $PostgresAdminPassword

if ([string]::IsNullOrWhiteSpace($AcrName)) {
    $AcrName = Get-DefaultAcrName -Seed $ResourceGroupName
}
if ([string]::IsNullOrWhiteSpace($StorageAccountName)) {
    $StorageAccountName = Get-DefaultStorageAccountName -Seed $ResourceGroupName
}
if ([string]::IsNullOrWhiteSpace($StorageContainerName)) {
    $StorageContainerName = "case-documents"
}
$originalAcrName = $AcrName
$AcrName = Normalize-AcrName -InputName $AcrName
if ($AcrName -ne $originalAcrName) {
    Write-Host "Normalized ACR name from '$originalAcrName' to '$AcrName' to satisfy Azure naming rules."
}

$originalStorageAccountName = $StorageAccountName
$StorageAccountName = Normalize-StorageAccountName -InputName $StorageAccountName
if ($StorageAccountName -ne $originalStorageAccountName) {
    Write-Host "Normalized storage account name from '$originalStorageAccountName' to '$StorageAccountName' to satisfy Azure naming rules."
}

$StorageContainerName = Normalize-StorageContainerName -InputName $StorageContainerName

Write-Host "Using ACR name: $AcrName"
Write-Host "Using PostgreSQL server: $PostgresServerName"
Write-Host "Using PostgreSQL database: $PostgresDatabaseName"
Write-Host "Using Application Insights: $ApplicationInsightsName"
Write-Host "Using storage account: $StorageAccountName"
Write-Host "Using storage container: $StorageContainerName"
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

Write-Host "Inspecting existing resources to avoid re-creation..."
$logAnalyticsWorkspaceLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $LogAnalyticsWorkspaceName `
    -ResourceType "Microsoft.OperationalInsights/workspaces"
$managedEnvironmentLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $EnvironmentName `
    -ResourceType "Microsoft.App/managedEnvironments"
$acrLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $AcrName `
    -ResourceType "Microsoft.ContainerRegistry/registries"
$storageAccountLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $StorageAccountName `
    -ResourceType "Microsoft.Storage/storageAccounts"
$applicationInsightsLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $ApplicationInsightsName `
    -ResourceType "Microsoft.Insights/components"
$managedIdentityLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $ManagedIdentityName `
    -ResourceType "Microsoft.ManagedIdentity/userAssignedIdentities"
$postgresServerLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $PostgresServerName `
    -ResourceType "Microsoft.DBforPostgreSQL/flexibleServers"
$containerAppLocation = Get-ResourceLocationInGroup `
    -ResourceGroupName $ResourceGroupName `
    -ResourceName $ContainerAppName `
    -ResourceType "Microsoft.App/containerApps"

$createLogAnalyticsWorkspace = [string]::IsNullOrWhiteSpace($logAnalyticsWorkspaceLocation)
$createManagedEnvironment = [string]::IsNullOrWhiteSpace($managedEnvironmentLocation)
$createAcr = [string]::IsNullOrWhiteSpace($acrLocation)
$createStorageAccount = [string]::IsNullOrWhiteSpace($storageAccountLocation)
$createApplicationInsights = [string]::IsNullOrWhiteSpace($applicationInsightsLocation)
$createManagedIdentity = [string]::IsNullOrWhiteSpace($managedIdentityLocation)
$createPostgresServer = [string]::IsNullOrWhiteSpace($postgresServerLocation)
$createContainerApp = [string]::IsNullOrWhiteSpace($containerAppLocation)

$normalizedLocation = Normalize-LocationName -Location $Location
$locationChecks = @(
    @{ Label = "Log Analytics Workspace"; Location = $logAnalyticsWorkspaceLocation },
    @{ Label = "Container Apps Environment"; Location = $managedEnvironmentLocation },
    @{ Label = "Container Registry"; Location = $acrLocation },
    @{ Label = "Storage Account"; Location = $storageAccountLocation },
    @{ Label = "Application Insights"; Location = $applicationInsightsLocation },
    @{ Label = "Managed Identity"; Location = $managedIdentityLocation },
    @{ Label = "PostgreSQL Flexible Server"; Location = $postgresServerLocation },
    @{ Label = "Container App"; Location = $containerAppLocation }
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_.Location) }

$mismatchedLocations = @(
    $locationChecks | Where-Object {
        (Normalize-LocationName -Location $_.Location) -ne $normalizedLocation
    } | ForEach-Object {
        "$($_.Label)='$($_.Location)'"
    }
)

if ($mismatchedLocations.Count -gt 0) {
    throw "Existing Azure resources do not match requested location '$Location': $($mismatchedLocations -join ', '). Update the target names or recreate those resources in the desired region."
}

Write-Host "Create plan:"
Write-Host " - Log Analytics Workspace: $createLogAnalyticsWorkspace"
Write-Host " - Container Apps Environment: $createManagedEnvironment"
Write-Host " - Container Registry: $createAcr"
Write-Host " - Storage Account: $createStorageAccount"
Write-Host " - Application Insights: $createApplicationInsights"
Write-Host " - Managed Identity: $createManagedIdentity"
Write-Host " - PostgreSQL Flexible Server: $createPostgresServer"
Write-Host " - Container App: $createContainerApp"

$currentClientIp = Get-PublicIpAddress
if (-not [string]::IsNullOrWhiteSpace($currentClientIp)) {
    Write-Host "Detected current public IP for PostgreSQL firewall rule: $currentClientIp"
}

Write-Host "Deploying Azure infrastructure with Bicep..."
$outputsRaw = az deployment group create `
    --resource-group $ResourceGroupName `
    --name "api-infra-$([DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))" `
    --template-file (Join-Path $infraRoot "bicep/main.bicep") `
    --only-show-errors `
    --parameters `
      location=$Location `
      environmentName=$EnvironmentName `
      containerAppName=$ContainerAppName `
      postgresServerName=$PostgresServerName `
      postgresDatabaseName=$PostgresDatabaseName `
      postgresAdminUsername=$PostgresAdminUsername `
      postgresAdminPassword=$PostgresAdminPassword `
      postgresSkuName=$PostgresSkuName `
      postgresSkuTier=$PostgresSkuTier `
      postgresVersion=$PostgresVersion `
      postgresStorageSizeGb=$PostgresStorageSizeGb `
      postgresClientIp=$currentClientIp `
      acrName=$AcrName `
      storageAccountName=$StorageAccountName `
      storageContainerName=$StorageContainerName `
      logAnalyticsWorkspaceName=$LogAnalyticsWorkspaceName `
      applicationInsightsName=$ApplicationInsightsName `
      managedIdentityName=$ManagedIdentityName `
      createLogAnalyticsWorkspace=$($createLogAnalyticsWorkspace.ToString().ToLower()) `
      createManagedEnvironment=$($createManagedEnvironment.ToString().ToLower()) `
      createAcr=$($createAcr.ToString().ToLower()) `
      createStorageAccount=$($createStorageAccount.ToString().ToLower()) `
      createApplicationInsights=$($createApplicationInsights.ToString().ToLower()) `
      createManagedIdentity=$($createManagedIdentity.ToString().ToLower()) `
      createPostgresServer=$($createPostgresServer.ToString().ToLower()) `
      createContainerApp=$($createContainerApp.ToString().ToLower()) `
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
    $outputsJson = Get-JsonPayloadFromCliOutput -RawText $outputsText
    $outputs = $outputsJson | ConvertFrom-Json
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

$storageAccountNameOutput = if ($outputs.PSObject.Properties.Name -contains "storageAccountName") {
    [string]$outputs.storageAccountName.value
}
else {
    $StorageAccountName
}
$storageContainerNameOutput = if ($outputs.PSObject.Properties.Name -contains "storageContainerName") {
    [string]$outputs.storageContainerName.value
}
else {
    $StorageContainerName
}
$storageBlobEndpointOutput = if ($outputs.PSObject.Properties.Name -contains "storageBlobEndpoint") {
    [string]$outputs.storageBlobEndpoint.value
}
else {
    ""
}
$applicationInsightsConnectionStringOutput = if ($outputs.PSObject.Properties.Name -contains "applicationInsightsConnectionString") {
    [string]$outputs.applicationInsightsConnectionString.value
}
else {
    ""
}
$applicationInsightsNameOutput = if ($outputs.PSObject.Properties.Name -contains "applicationInsightsName") {
    [string]$outputs.applicationInsightsName.value
}
else {
    $ApplicationInsightsName
}
$postgresHostOutput = if ($outputs.PSObject.Properties.Name -contains "postgresHost") {
    [string]$outputs.postgresHost.value
}
else {
    "${PostgresServerName}.postgres.database.azure.com"
}
$postgresDatabaseNameOutput = if ($outputs.PSObject.Properties.Name -contains "postgresDatabaseName") {
    [string]$outputs.postgresDatabaseName.value
}
else {
    $PostgresDatabaseName
}
$dbCloud = Convert-ToPostgresConnectionString `
    -HostName $postgresHostOutput `
    -DatabaseName $postgresDatabaseNameOutput `
    -AdminUsername $PostgresAdminUsername `
    -AdminPassword $PostgresAdminPassword
$storeCloud = if (-not [string]::IsNullOrWhiteSpace($storageBlobEndpointOutput)) {
    $storageBlobEndpointOutput.TrimEnd("/") + "/$storageContainerNameOutput"
}
else {
    ""
}

Write-Host "Building image in ACR: ${acrLoginServer}/${ImageRepository}:${ImageTag}"
$apiBuildContextPath = "."
$apiDockerfilePath = "api/aijuristiction-api/Dockerfile"
Build-AndPushImage `
    -RegistryName $AcrName `
    -AcrLoginServer $acrLoginServer `
    -Repository $ImageRepository `
    -Tag $ImageTag `
    -RepoRoot $repoRoot `
    -BuildContextPath $apiBuildContextPath `
    -DockerfilePath $apiDockerfilePath

$imageRef = "${acrLoginServer}/${ImageRepository}:${ImageTag}"
Write-Host "Waiting for image manifest in ACR: $imageRef"
$imageReady = Wait-ForAcrImage -RegistryName $AcrName -Repository $ImageRepository -Tag $ImageTag
if (-not $imageReady) {
    throw "Image manifest not found in ACR after build: $imageRef"
}

Write-Host "Ensuring Container App secrets exist before image update..."
$applicationInsightsConnectionStringFromEnvFile = if ($resolvedEnvFilePath) {
    Get-ValueFromEnvFile -Path $resolvedEnvFilePath -Key "APPLICATIONINSIGHTS_CONNECTION_STRING"
}
else {
    ""
}
$applicationInsightsConnectionString = Resolve-InputValue `
    -ExplicitValue "" `
    -EnvFileValue $applicationInsightsConnectionStringFromEnvFile `
    -EnvironmentValue $env:APPLICATIONINSIGHTS_CONNECTION_STRING
if ([string]::IsNullOrWhiteSpace($applicationInsightsConnectionString)) {
    $applicationInsightsConnectionString = $applicationInsightsConnectionStringOutput
}
$secretPairs = New-Object System.Collections.Generic.List[string]
$secretPairs.Add("db-cloud=$dbCloud")
if (-not [string]::IsNullOrWhiteSpace($applicationInsightsConnectionString)) {
    $secretPairs.Add("applicationinsights-connection-string=$applicationInsightsConnectionString")
}
az containerapp secret set `
    --name $ContainerAppName `
    --resource-group $ResourceGroupName `
    --secrets $secretPairs.ToArray() `
    --only-show-errors `
    --output none

Write-Host "Updating Container App image: $imageRef"

$envPairs = Convert-EnvFileToPairs -Path $resolvedEnvFilePath
$envPairsList = New-Object System.Collections.Generic.List[string]
foreach ($item in $envPairs) {
    $key = $item.Split("=", 2)[0]
    if ($key -in @("DB_OPTION", "DB_CLOUD", "DB_LOCAL", "STORAGE_OPTION", "STORE_CLOUD", "STORE_LOCAL", "APPLICATIONINSIGHTS_CONNECTION_STRING")) {
        continue
    }
    $envPairsList.Add($item)
}
$envPairsList.Add("DB_OPTION=azure")
$envPairsList.Add("DB_CLOUD=secretref:db-cloud")
$envPairsList.Add("DB_LOCAL=/tmp/api.sqlite3")
$envPairsList.Add("STORAGE_OPTION=azure")
$envPairsList.Add("STORE_LOCAL=/tmp/storage")
if (-not [string]::IsNullOrWhiteSpace($storeCloud)) {
    $envPairsList.Add("STORE_CLOUD=$storeCloud")
}
if (-not [string]::IsNullOrWhiteSpace($applicationInsightsConnectionString)) {
    $envPairsList.Add("APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:applicationinsights-connection-string")
}
$envPairs = $envPairsList.ToArray()

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

Write-Host "Applying API schema migrations to Azure PostgreSQL..."
$previousDbOption = $env:DB_OPTION
$previousDbCloud = $env:DB_CLOUD
try {
    $env:DB_OPTION = "azure"
    $env:DB_CLOUD = $dbCloud
    python (Join-Path $repoRoot "scripts/databases/apply_api_db_schema.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Schema migration command failed."
    }
}
finally {
    Restore-EnvVar -Name "DB_OPTION" -PreviousValue $previousDbOption
    Restore-EnvVar -Name "DB_CLOUD" -PreviousValue $previousDbCloud
}

Write-Host ""
Write-Host "Deployment complete."
Write-Host "Container App URL: https://$fqdn"
Write-Host "Health check:       https://$fqdn/health"
Write-Host "PostgreSQL host:    $postgresHostOutput"
Write-Host "PostgreSQL database:$postgresDatabaseNameOutput"
Write-Host "Application Insights: $applicationInsightsNameOutput"
Write-Host "Storage account:    $storageAccountNameOutput"
Write-Host "Storage container:  $storageContainerNameOutput"
if (-not [string]::IsNullOrWhiteSpace($storageBlobEndpointOutput)) {
    Write-Host "Storage blob endpoint: $storageBlobEndpointOutput"
}

$managedEnvironmentDisposition = if ($createManagedEnvironment) { "created" } else { "reused" }
$containerAppDisposition = if ($createContainerApp) { "created" } else { "updated" }

Write-Host "ACA resources:"
Write-Host " - Managed environment ($managedEnvironmentDisposition): $EnvironmentName"
Write-Host " - API container app ($containerAppDisposition): $ContainerAppName"

Write-WorkflowSummary -Lines @(
    "## ACA deployment summary",
    "",
    "| Resource | Name | Result | Endpoint |",
    "| --- | --- | --- | --- |",
    "| Managed environment | $EnvironmentName | $managedEnvironmentDisposition | n/a |",
    "| API container app | $ContainerAppName | $containerAppDisposition | https://$fqdn |"
)
