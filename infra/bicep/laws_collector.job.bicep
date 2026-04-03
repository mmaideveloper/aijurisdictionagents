param location string = resourceGroup().location
param managedEnvironmentName string
param jobName string = 'laws-collector'
param acrName string
param managedIdentityName string
param image string
param postgresServerName string
param postgresDatabaseName string = 'laws_sk'
param postgresAdminUsername string
@secure()
param postgresAdminPassword string
@secure()
param postgresConnectionString string = ''
@secure()
param applicationInsightsConnectionString string = ''
param systemEmbeddingModelOption string = 'local'
param systemEmbeddingModel string = 'all-MiniLM-L6-v2'
param cronExpression string = '0 0 * * *'
param workerMaxProbes int = 1
param replicaTimeout int = 3600
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

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' existing = {
  name: postgresServerName
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, 'AcrPull')
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

resource lawsCollectorJob 'Microsoft.App/jobs@2024-03-01' = {
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
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: parallelism
        replicaCompletionCount: completions
      }
      replicaTimeout: replicaTimeout
      replicaRetryLimit: replicaRetryLimit
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: concat(
        [
          {
            name: 'laws-db-cloud'
            value: empty(postgresConnectionString)
              ? 'postgresql://${postgresAdminUsername}:${postgresAdminPassword}@${postgresServer.name}.postgres.database.azure.com:5432/${postgresDatabaseName}?sslmode=require'
              : postgresConnectionString
          }
        ],
        !empty(applicationInsightsConnectionString)
          ? [
              {
                name: 'applicationinsights-connection-string'
                value: applicationInsightsConnectionString
              }
            ]
          : []
      )
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
          env: concat(
            [
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
                name: 'LAWS_WORKER_FIXTURE'
                value: 'live'
              }
              {
                name: 'LAWS_WORKER_MAX_CYCLES'
                value: '1'
              }
              {
                name: 'LAWS_WORKER_MAX_PROBES'
                value: string(workerMaxProbes)
              }
              {
                name: 'SYSTEM_EMBEDDING_MODEL_OPTION'
                value: systemEmbeddingModelOption
              }
              {
                name: 'SYSTEM_EMBEDDING_MODEL'
                value: systemEmbeddingModel
              }
            ],
            !empty(applicationInsightsConnectionString)
              ? [
                  {
                    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
                    secretRef: 'applicationinsights-connection-string'
                  }
                ]
              : []
          )
        }
      ]
    }
  }
  dependsOn: [
    acrPullRoleAssignment
  ]
}

output jobName string = lawsCollectorJob.name
