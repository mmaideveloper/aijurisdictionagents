param location string = resourceGroup().location
param managedEnvironmentName string
param jobName string = 'document-processor'
param acrName string
param managedIdentityName string
param image string
param postgresServerName string
param postgresDatabaseName string = 'api'
param postgresAdminUsername string
@secure()
param postgresAdminPassword string
param storageAccountName string
param storageContainerName string = 'documents'
param triggerType string = 'Schedule'
param cronExpression string = '0 */15 * * * *'
param replicaTimeout int = 1800
param replicaRetryLimit int = 1
param parallelism int = 1
param completions int = 1
param tags object = {}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: managedEnvironmentName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: managedIdentityName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' existing = {
  name: postgresServerName
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, 'AcrPull', jobName)
  scope: acr
  properties: {
    principalId: managedIdentity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalType: 'ServicePrincipal'
  }
}

resource storageBlobDataRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, 'StorageBlobDataContributor', jobName)
  scope: storageAccount
  properties: {
    principalId: managedIdentity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalType: 'ServicePrincipal'
  }
}

resource documentProcessorJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    environmentId: managedEnvironment.id
    configuration: {
      triggerType: triggerType
      scheduleTriggerConfig: triggerType == 'Schedule' ? {
        cronExpression: cronExpression
        parallelism: parallelism
        replicaCompletionCount: completions
      } : null
      replicaTimeout: replicaTimeout
      replicaRetryLimit: replicaRetryLimit
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: [
        {
          name: 'processor-db-cloud'
          value: 'postgresql://${postgresAdminUsername}:${postgresAdminPassword}@${postgresServer.name}.postgres.database.azure.com:5432/${postgresDatabaseName}?sslmode=require'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'document-processor'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DB_OPTION'
              value: 'azure'
            }
            {
              name: 'DB_CLOUD'
              secretRef: 'processor-db-cloud'
            }
            {
              name: 'STORAGE_OPTION'
              value: 'azure'
            }
            {
              name: 'DOCUMENT_PROCESSOR'
              value: 'azure'
            }
            {
              name: 'STORE_CLOUD'
              value: 'https://${storageAccount.name}.blob.core.windows.net/${storageContainerName}'
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    acrPullRoleAssignment
    storageBlobDataRoleAssignment
  ]
}

output jobName string = documentProcessorJob.name
