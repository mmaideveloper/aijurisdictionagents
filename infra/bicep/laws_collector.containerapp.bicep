param location string = resourceGroup().location
param managedEnvironmentName string
param containerAppName string = 'laws-collector'
param acrName string
param managedIdentityName string
param image string
param postgresServerName string
param postgresDatabaseName string = 'laws_sk'
param postgresAdminUsername string
@secure()
param postgresAdminPassword string
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

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' existing = {
  name: postgresServerName
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, 'AcrPull', containerAppName)
  scope: acr
  properties: {
    principalId: managedIdentity.properties.principalId
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalType: 'ServicePrincipal'
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8080
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: [
        {
          name: 'laws-db-cloud'
          value: 'postgresql://${postgresAdminUsername}:${postgresAdminPassword}@${postgresServer.name}.postgres.database.azure.com:5432/${postgresDatabaseName}?sslmode=require'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'laws-collector'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'LAWS_COUNTRY'
              value: 'SK'
            }
            {
              name: 'LAWS_DB_BACKEND'
              value: 'postgres'
            }
            {
              name: 'LAWS_DB_CLOUD'
              secretRef: 'laws-db-cloud'
            }
            {
              name: 'LAWS_WORKER_POLL_SECONDS'
              value: '3600'
            }
            {
              name: 'LAWS_WORKER_FIXTURE'
              value: 'baseline'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPullRoleAssignment
  ]
}

output containerAppName string = containerApp.name
