param location string = resourceGroup().location
param environmentName string
param containerAppName string
param acrName string
param logAnalyticsWorkspaceName string
param managedIdentityName string
param createLogAnalyticsWorkspace bool = true
param createManagedEnvironment bool = true
param createAcr bool = true
param createManagedIdentity bool = true
param createContainerApp bool = true
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

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = if (createManagedIdentity) {
  name: managedIdentityName
  location: location
  tags: tags
}

resource managedIdentityExisting 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = if (!createManagedIdentity) {
  name: managedIdentityName
}

var managedIdentityId = createManagedIdentity ? managedIdentity.id : managedIdentityExisting.id
var managedIdentityPrincipalId = createManagedIdentity
  ? managedIdentity.properties.principalId
  : managedIdentityExisting.properties.principalId
var createAcrPullRoleAssignment = createContainerApp || createAcr || createManagedIdentity

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
  ]
}

resource containerAppExisting 'Microsoft.App/containerApps@2024-03-01' existing = if (!createContainerApp) {
  name: containerAppName
}

output acrLoginServer string = acrLoginServer
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
