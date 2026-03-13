param location string = resourceGroup().location
param environmentName string
param containerAppName string
param acrName string
param storageAccountName string = toLower('staijur${uniqueString(subscription().subscriptionId, resourceGroup().name)}')
param storageContainerName string = 'case-documents'
param logAnalyticsWorkspaceName string
param managedIdentityName string
param postgresServerName string
param postgresDatabaseName string = 'aijurisdiction'
param postgresAdminUsername string
@secure()
param postgresAdminPassword string = ''
param postgresSkuName string = 'Standard_B1ms'
param postgresSkuTier string = 'Burstable'
param postgresVersion string = '16'
param postgresStorageSizeGb int = 32
param postgresClientIp string = ''
param createLogAnalyticsWorkspace bool = true
param createManagedEnvironment bool = true
param createAcr bool = true
param createStorageAccount bool = true
param createManagedIdentity bool = true
param createContainerApp bool = true
param createPostgresServer bool = true
param tags object = {}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (createLogAnalyticsWorkspace) {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource logAnalyticsWorkspaceExisting 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = if (!createLogAnalyticsWorkspace) {
  name: logAnalyticsWorkspaceName
}

var logAnalyticsCustomerId = createLogAnalyticsWorkspace
  ? logAnalyticsWorkspace.properties.customerId
  : logAnalyticsWorkspaceExisting.properties.customerId
var logAnalyticsSharedKey = createLogAnalyticsWorkspace
  ? logAnalyticsWorkspace.listKeys().primarySharedKey
  : logAnalyticsWorkspaceExisting.listKeys().primarySharedKey

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = if (createManagedEnvironment) {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

resource managedEnvironmentExisting 'Microsoft.App/managedEnvironments@2024-03-01' existing = if (!createManagedEnvironment) {
  name: environmentName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = if (createAcr) {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource acrExisting 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = if (!createAcr) {
  name: acrName
}

var acrId = createAcr ? acr.id : acrExisting.id
var acrLoginServer = createAcr ? acr.properties.loginServer : acrExisting.properties.loginServer

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = if (createStorageAccount) {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource storageAccountExisting 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (!createStorageAccount) {
  name: storageAccountName
}

var storageAccountId = createStorageAccount ? storageAccount.id : storageAccountExisting.id
var storageBlobEndpoint = createStorageAccount
  ? storageAccount.properties.primaryEndpoints.blob
  : storageAccountExisting.properties.primaryEndpoints.blob

resource storageBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = if (createStorageAccount) {
  name: '${storageAccount.name}/default'
}

resource storageBlobServiceExisting 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = if (!createStorageAccount) {
  name: '${storageAccountName}/default'
}

resource storageContainerOnNewStorage 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (createStorageAccount) {
  name: storageContainerName
  parent: storageBlobService
  properties: {
    publicAccess: 'None'
  }
}

resource storageContainerOnExistingStorage 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (!createStorageAccount) {
  name: storageContainerName
  parent: storageBlobServiceExisting
  properties: {
    publicAccess: 'None'
  }
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = if (createManagedIdentity) {
  name: managedIdentityName
  location: location
  tags: tags
}

resource managedIdentityExisting 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = if (!createManagedIdentity) {
  name: managedIdentityName
}

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = if (createPostgresServer) {
  name: postgresServerName
  location: location
  tags: tags
  sku: {
    name: postgresSkuName
    tier: postgresSkuTier
  }
  properties: {
    administratorLogin: postgresAdminUsername
    administratorLoginPassword: postgresAdminPassword
    version: postgresVersion
    storage: {
      storageSizeGB: postgresStorageSizeGb
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource postgresServerExisting 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' existing = if (!createPostgresServer) {
  name: postgresServerName
}

resource postgresExtensionsConfigOnNewServer 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2022-12-01' = if (createPostgresServer) {
  name: 'azure.extensions'
  parent: postgresServer
  properties: {
    value: 'vector'
    source: 'user-override'
  }
}

resource postgresExtensionsConfigOnExistingServer 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2022-12-01' = if (!createPostgresServer) {
  name: 'azure.extensions'
  parent: postgresServerExisting
  properties: {
    value: 'vector'
    source: 'user-override'
  }
}

resource postgresAllowAzureOnNewServer 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = if (createPostgresServer) {
  name: 'AllowAzureServices'
  parent: postgresServer
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource postgresAllowAzureOnExistingServer 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = if (!createPostgresServer) {
  name: 'AllowAzureServices'
  parent: postgresServerExisting
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource postgresClientIpRuleOnNewServer 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = if (createPostgresServer && !empty(postgresClientIp)) {
  name: 'AllowCurrentClientIp'
  parent: postgresServer
  properties: {
    startIpAddress: postgresClientIp
    endIpAddress: postgresClientIp
  }
}

resource postgresClientIpRuleOnExistingServer 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = if (!createPostgresServer && !empty(postgresClientIp)) {
  name: 'AllowCurrentClientIp'
  parent: postgresServerExisting
  properties: {
    startIpAddress: postgresClientIp
    endIpAddress: postgresClientIp
  }
}

resource postgresDatabaseOnNewServer 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = if (createPostgresServer) {
  name: postgresDatabaseName
  parent: postgresServer
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource postgresDatabaseOnExistingServer 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = if (!createPostgresServer) {
  name: postgresDatabaseName
  parent: postgresServerExisting
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

var managedIdentityId = createManagedIdentity ? managedIdentity.id : managedIdentityExisting.id
var managedIdentityPrincipalId = createManagedIdentity
  ? managedIdentity.properties.principalId
  : managedIdentityExisting.properties.principalId
var createAcrPullRoleAssignment = createContainerApp || createAcr || createManagedIdentity
var createStorageBlobDataRoleAssignment = createContainerApp || createStorageAccount || createManagedIdentity

resource acrPullRoleAssignmentOnNewAcr 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createAcrPullRoleAssignment && createAcr) {
  name: guid(acrId, managedIdentityId, 'AcrPull')
  scope: acr
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalType: 'ServicePrincipal'
  }
}

resource acrPullRoleAssignmentOnExistingAcr 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createAcrPullRoleAssignment && !createAcr) {
  name: guid(acrId, managedIdentityId, 'AcrPull')
  scope: acrExisting
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalType: 'ServicePrincipal'
  }
}

resource storageBlobDataRoleAssignmentOnNewStorage 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createStorageBlobDataRoleAssignment && createStorageAccount) {
  name: guid(storageAccountId, managedIdentityId, 'StorageBlobDataContributor')
  scope: storageAccount
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalType: 'ServicePrincipal'
  }
}

resource storageBlobDataRoleAssignmentOnExistingStorage 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createStorageBlobDataRoleAssignment && !createStorageAccount) {
  name: guid(storageAccountId, managedIdentityId, 'StorageBlobDataContributor')
  scope: storageAccountExisting
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalType: 'ServicePrincipal'
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = if (createContainerApp) {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: createManagedEnvironment ? managedEnvironment.id : managedEnvironmentExisting.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
  dependsOn: [
    acrPullRoleAssignmentOnNewAcr
    acrPullRoleAssignmentOnExistingAcr
    storageBlobDataRoleAssignmentOnNewStorage
    storageBlobDataRoleAssignmentOnExistingStorage
  ]
}

resource containerAppExisting 'Microsoft.App/containerApps@2024-03-01' existing = if (!createContainerApp) {
  name: containerAppName
}

output acrLoginServer string = acrLoginServer
output storageAccountName string = createStorageAccount ? storageAccount.name : storageAccountExisting.name
output storageContainerName string = storageContainerName
output storageBlobEndpoint string = storageBlobEndpoint
output containerAppName string = createContainerApp ? containerApp.name : containerAppExisting.name
output containerAppFqdn string = createContainerApp
  ? containerApp.properties.configuration.ingress.fqdn
  : containerAppExisting.properties.configuration.ingress.fqdn
output containerAppUrl string = createContainerApp
  ? 'https://${containerApp.properties.configuration.ingress.fqdn}'
  : 'https://${containerAppExisting.properties.configuration.ingress.fqdn}'
output containerAppsEnvironmentName string = createManagedEnvironment
  ? managedEnvironment.name
  : managedEnvironmentExisting.name
output postgresServerName string = createPostgresServer ? postgresServer.name : postgresServerExisting.name
output postgresDatabaseName string = postgresDatabaseName
output postgresHost string = createPostgresServer
  ? postgresServer.properties.fullyQualifiedDomainName
  : postgresServerExisting.properties.fullyQualifiedDomainName
