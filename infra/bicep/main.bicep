param location string = resourceGroup().location
param environmentName string
param containerAppName string
param frontendContainerAppName string
param documentProcessorJobName string = 'document-processor'
param documentProcessorCronExpression string = '*/15 * * * *'
param documentProcessorMaxRunningTime int = 15
param emailSchedulerJobName string = 'email-scheduler'
param emailSchedulerCronExpression string = '*/5 * * * *'
param lawsCollectorJobName string = 'laws-collector'
param lawsCollectorCronExpression string = '0 0 * * *'
param lawsCollectorMaxProbes int = 1
param lawsCollectorMaxRunningTime int = 60
param lawsCollectorImport string = 'zip'
param acrName string
param storageAccountName string = toLower('staijur${uniqueString(subscription().subscriptionId, resourceGroup().name)}')
param storageContainerName string = 'case-documents'
param lawsStorageContainerName string = 'laws-collection-sk'
param logAnalyticsWorkspaceName string
param applicationInsightsName string
param managedIdentityName string
param postgresServerName string
param postgresDatabaseName string = 'aijurisdiction'
param lawsPostgresDatabaseName string = 'laws_sk'
param postgresAdminUsername string
@secure()
param postgresAdminPassword string = ''
@secure()
param postgresConnectionString string = ''
@secure()
param lawsPostgresConnectionString string = ''
param postgresSkuName string = 'Standard_B1ms'
param postgresSkuTier string = 'Burstable'
param postgresVersion string = '17'
param postgresStorageSizeGb int = 32
param postgresClientIp string = ''
param llmProvider string = 'azurefoundry'
param systemEmbeddingModelOption string = 'local'
param systemEmbeddingModel string = 'all-MiniLM-L6-v2'
param azureOpenAIEndpoint string
param azureOpenAIEmbeddingsModel string = 'text-embedding-3-large'
param azureOpenAIApiVersion string = '2024-12-01-preview'
@secure()
param azureOpenAIApiKey string
param createLogAnalyticsWorkspace bool = true
param createManagedEnvironment bool = true
param createAcr bool = true
param createStorageAccount bool = true
param createManagedIdentity bool = true
param createApplicationInsights bool = true
param createContainerApp bool = true
param createFrontendContainerApp bool = true
param createDocumentProcessorJob bool = true
param createEmailSchedulerJob bool = true
param createLawsCollectorJob bool = true
param createPostgresServer bool = true
param createAcrPullRoleAssignment bool = true
param createStorageBlobDataRoleAssignment bool = true
param createLogAnalyticsDataReaderRoleAssignment bool = true
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

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = if (createApplicationInsights) {
  name: applicationInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    Request_Source: 'CustomDeployment'
    WorkspaceResourceId: createLogAnalyticsWorkspace ? logAnalyticsWorkspace.id : logAnalyticsWorkspaceExisting.id
  }
}

resource applicationInsightsExisting 'Microsoft.Insights/components@2020-02-02' existing = if (!createApplicationInsights) {
  name: applicationInsightsName
}

// Application Insights tables otherwise default to substantially longer retention.
// Session troubleshooting is deliberately capped at seven days in every table queried
// by Admin > Debug. Keep total retention equal to interactive retention so no archive remains.
var sessionDebugLogTables = [
  'AppDependencies'
  'AppExceptions'
  'AppRequests'
  'AppTraces'
]

resource createdWorkspaceDebugTables 'Microsoft.OperationalInsights/workspaces/tables@2025-07-01' = [for tableName in sessionDebugLogTables: if (createLogAnalyticsWorkspace) {
  parent: logAnalyticsWorkspace
  name: tableName
  properties: {
    retentionInDays: 7
    totalRetentionInDays: 7
  }
}]

resource existingWorkspaceDebugTables 'Microsoft.OperationalInsights/workspaces/tables@2025-07-01' = [for tableName in sessionDebugLogTables: if (!createLogAnalyticsWorkspace) {
  parent: logAnalyticsWorkspaceExisting
  name: tableName
  properties: {
    retentionInDays: 7
    totalRetentionInDays: 7
  }
}]

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

resource lawsPostgresDatabaseOnNewServer 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = if (createPostgresServer) {
  name: lawsPostgresDatabaseName
  parent: postgresServer
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource lawsPostgresDatabaseOnExistingServer 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = if (!createPostgresServer) {
  name: lawsPostgresDatabaseName
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

resource logAnalyticsDataReaderRoleAssignmentOnNewWorkspace 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createLogAnalyticsDataReaderRoleAssignment && createLogAnalyticsWorkspace) {
  name: guid(logAnalyticsWorkspace.id, managedIdentityId, 'LogAnalyticsDataReader')
  scope: logAnalyticsWorkspace
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '3b03c2da-16b3-4a49-8834-0f8130efdd3b'
    )
    principalType: 'ServicePrincipal'
  }
}

resource logAnalyticsDataReaderRoleAssignmentOnExistingWorkspace 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createLogAnalyticsDataReaderRoleAssignment && !createLogAnalyticsWorkspace) {
  name: guid(logAnalyticsWorkspaceExisting.id, managedIdentityId, 'LogAnalyticsDataReader')
  scope: logAnalyticsWorkspaceExisting
  properties: {
    principalId: managedIdentityPrincipalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '3b03c2da-16b3-4a49-8834-0f8130efdd3b'
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
    logAnalyticsDataReaderRoleAssignmentOnNewWorkspace
    logAnalyticsDataReaderRoleAssignmentOnExistingWorkspace
    storageBlobDataRoleAssignmentOnNewStorage
    storageBlobDataRoleAssignmentOnExistingStorage
  ]
}

resource containerAppExisting 'Microsoft.App/containerApps@2024-03-01' existing = if (!createContainerApp) {
  name: containerAppName
}

module frontendContainerApp 'frontend.containerapp.bicep' = if (createFrontendContainerApp) {
  name: 'frontendContainerApp'
  params: {
    location: location
    managedEnvironmentName: environmentName
    containerAppName: frontendContainerAppName
    acrName: acrName
    managedIdentityName: managedIdentityName
    image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    tags: tags
  }
  dependsOn: [
    managedEnvironment
    acr
    managedIdentity
  ]
}

resource frontendContainerAppExisting 'Microsoft.App/containerApps@2024-03-01' existing = if (!createFrontendContainerApp) {
  name: frontendContainerAppName
}

module documentProcessorJob 'document_processor.job.bicep' = if (createDocumentProcessorJob) {
  name: 'documentProcessorJob'
  params: {
    location: location
    managedEnvironmentName: environmentName
    jobName: documentProcessorJobName
    cronExpression: documentProcessorCronExpression
    documentProcessorMaxRunningTime: documentProcessorMaxRunningTime
    acrName: acrName
    managedIdentityName: managedIdentityName
    image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    storageAccountName: storageAccountName
    storageContainerName: storageContainerName
    postgresServerName: postgresServerName
    postgresDatabaseName: postgresDatabaseName
    postgresAdminUsername: postgresAdminUsername
    postgresAdminPassword: postgresAdminPassword
    postgresConnectionString: postgresConnectionString
    applicationInsightsConnectionString: createApplicationInsights
      ? applicationInsights.properties.ConnectionString
      : applicationInsightsExisting.properties.ConnectionString
    llmProvider: llmProvider
    systemEmbeddingModelOption: systemEmbeddingModelOption
    systemEmbeddingModel: systemEmbeddingModel
    azureOpenAIEndpoint: azureOpenAIEndpoint
    azureOpenAIEmbeddingsModel: azureOpenAIEmbeddingsModel
    azureOpenAIApiVersion: azureOpenAIApiVersion
    azureOpenAIApiKey: azureOpenAIApiKey
    tags: tags
  }
  dependsOn: [
    managedEnvironment
    acr
    managedIdentity
    postgresServer
    postgresDatabaseOnNewServer
    postgresDatabaseOnExistingServer
    storageContainerOnNewStorage
    storageContainerOnExistingStorage
  ]
}

resource documentProcessorJobExisting 'Microsoft.App/jobs@2024-03-01' existing = if (!createDocumentProcessorJob) {
  name: documentProcessorJobName
}

module emailSchedulerJob 'email_scheduler.job.bicep' = if (createEmailSchedulerJob) {
  name: 'emailSchedulerJob'
  params: {
    location: location
    managedEnvironmentName: environmentName
    jobName: emailSchedulerJobName
    cronExpression: emailSchedulerCronExpression
    acrName: acrName
    managedIdentityName: managedIdentityName
    image: 'mcr.microsoft.com/azurelinux/base/core:3.0'
    runScheduler: false
    postgresServerName: postgresServerName
    postgresDatabaseName: postgresDatabaseName
    postgresAdminUsername: postgresAdminUsername
    postgresAdminPassword: postgresAdminPassword
    postgresConnectionString: postgresConnectionString
    applicationInsightsConnectionString: createApplicationInsights
      ? applicationInsights.properties.ConnectionString
      : applicationInsightsExisting.properties.ConnectionString
    tags: tags
  }
  dependsOn: [
    managedEnvironment
    acr
    managedIdentity
    postgresServer
    postgresDatabaseOnNewServer
    postgresDatabaseOnExistingServer
  ]
}

resource emailSchedulerJobExisting 'Microsoft.App/jobs@2024-03-01' existing = if (!createEmailSchedulerJob) {
  name: emailSchedulerJobName
}

module lawsCollectorJob 'laws_collector.job.bicep' = if (createLawsCollectorJob) {
  name: 'lawsCollectorJob'
  params: {
    location: location
    managedEnvironmentName: environmentName
    jobName: lawsCollectorJobName
    acrName: acrName
    managedIdentityName: managedIdentityName
    image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    storageAccountName: storageAccountName
    storageContainerName: lawsStorageContainerName
    postgresServerName: postgresServerName
    postgresDatabaseName: lawsPostgresDatabaseName
    postgresAdminUsername: postgresAdminUsername
    postgresAdminPassword: postgresAdminPassword
    postgresConnectionString: lawsPostgresConnectionString
    applicationInsightsConnectionString: createApplicationInsights
      ? applicationInsights.properties.ConnectionString
      : applicationInsightsExisting.properties.ConnectionString
    lawsCollectorImport: lawsCollectorImport
    systemEmbeddingModelOption: systemEmbeddingModelOption
    systemEmbeddingModel: systemEmbeddingModel
    cronExpression: lawsCollectorCronExpression
    workerMaxProbes: lawsCollectorMaxProbes
    lawsCollectorMaxRunningTime: lawsCollectorMaxRunningTime
    tags: tags
  }
  dependsOn: [
    managedEnvironment
    acr
    managedIdentity
    postgresServer
    lawsPostgresDatabaseOnNewServer
    lawsPostgresDatabaseOnExistingServer
    storageContainerOnNewStorage
    storageContainerOnExistingStorage
  ]
}

resource lawsCollectorJobExisting 'Microsoft.App/jobs@2024-03-01' existing = if (!createLawsCollectorJob) {
  name: lawsCollectorJobName
}

output acrLoginServer string = acrLoginServer
output storageAccountName string = createStorageAccount ? storageAccount.name : storageAccountExisting.name
output storageContainerName string = storageContainerName
output storageBlobEndpoint string = storageBlobEndpoint
output logAnalyticsWorkspaceCustomerId string = logAnalyticsCustomerId
output applicationInsightsName string = createApplicationInsights ? applicationInsights.name : applicationInsightsExisting.name
output applicationInsightsConnectionString string = createApplicationInsights
  ? applicationInsights.properties.ConnectionString
  : applicationInsightsExisting.properties.ConnectionString
output containerAppName string = createContainerApp ? containerApp.name : containerAppExisting.name
output containerAppFqdn string = createContainerApp
  ? containerApp.properties.configuration.ingress.fqdn
  : containerAppExisting.properties.configuration.ingress.fqdn
output containerAppUrl string = createContainerApp
  ? 'https://${containerApp.properties.configuration.ingress.fqdn}'
  : 'https://${containerAppExisting.properties.configuration.ingress.fqdn}'
output frontendContainerAppName string = createFrontendContainerApp
  ? frontendContainerApp.outputs.containerAppName
  : frontendContainerAppExisting.name
output frontendContainerAppFqdn string = createFrontendContainerApp
  ? frontendContainerApp.outputs.containerAppFqdn
  : frontendContainerAppExisting.properties.configuration.ingress.fqdn
output frontendContainerAppUrl string = createFrontendContainerApp
  ? frontendContainerApp.outputs.containerAppUrl
  : 'https://${frontendContainerAppExisting.properties.configuration.ingress.fqdn}'
output documentProcessorJobName string = createDocumentProcessorJob
  ? documentProcessorJob.outputs.jobName
  : documentProcessorJobExisting.name
output containerAppsEnvironmentName string = createManagedEnvironment
  ? managedEnvironment.name
  : managedEnvironmentExisting.name
output postgresServerName string = createPostgresServer ? postgresServer.name : postgresServerExisting.name
output postgresDatabaseName string = postgresDatabaseName
output lawsPostgresDatabaseName string = lawsPostgresDatabaseName
output lawsCollectorJobName string = createLawsCollectorJob
  ? lawsCollectorJob.outputs.jobName
  : lawsCollectorJobExisting.name
output postgresHost string = createPostgresServer
  ? postgresServer.properties.fullyQualifiedDomainName
  : postgresServerExisting.properties.fullyQualifiedDomainName
