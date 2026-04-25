param location string = resourceGroup().location
param managedEnvironmentName string
param jobName string = 'email-scheduler'
param acrName string
param managedIdentityName string
param image string
param runScheduler bool = true
param postgresServerName string
param postgresDatabaseName string = 'aijurisdiction'
param postgresAdminUsername string
@secure()
param postgresAdminPassword string
@secure()
param postgresConnectionString string = ''
@secure()
param applicationInsightsConnectionString string = ''
param emailTransport string = 'smtp'
param emailSender string = 'no-reply@jurisdigta.eu'
param emailSmtpHost string = 'mail.webhouse.sk'
param emailSmtpPort string = '587'
param emailSmtpUseTls string = 'true'
param emailSmtpUsername string = 'no-reply@jurisdigta.eu'
@secure()
param emailSmtpPassword string = ''
param cronExpression string = '*/5 * * * *'
param replicaTimeout int = 600
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

var emailSchedulerSecrets = concat(
  [
    {
      name: 'scheduler-db-cloud'
      value: empty(postgresConnectionString)
        ? 'postgresql://${postgresAdminUsername}:${postgresAdminPassword}@${postgresServer.name}.postgres.database.azure.com:5432/${postgresDatabaseName}?sslmode=require'
        : postgresConnectionString
    }
  ],
  !empty(emailSmtpPassword)
    ? [
        {
          name: 'email-smtp-password'
          value: emailSmtpPassword
        }
      ]
    : [],
  !empty(applicationInsightsConnectionString)
    ? [
        {
          name: 'applicationinsights-connection-string'
          value: applicationInsightsConnectionString
        }
      ]
    : []
)

var emailSchedulerEnv = concat(
  [
    {
      name: 'EMAIL_DB_OPTION'
      value: 'azure'
    }
    {
      name: 'EMAIL_DB_CLOUD'
      secretRef: 'scheduler-db-cloud'
    }
    {
      name: 'EMAIL_DB_LOCAL'
      value: '/tmp/email.sqlite3'
    }
    {
      name: 'EMAIL_TRANSPORT'
      value: emailTransport
    }
    {
      name: 'EMAIL_SENDER'
      value: emailSender
    }
    {
      name: 'EMAIL_SMTP_HOST'
      value: emailSmtpHost
    }
    {
      name: 'EMAIL_SMTP_PORT'
      value: emailSmtpPort
    }
    {
      name: 'EMAIL_SMTP_USE_TLS'
      value: emailSmtpUseTls
    }
    {
      name: 'EMAIL_SMTP_USERNAME'
      value: emailSmtpUsername
    }
    {
      name: 'EMAIL_SCHEDULER_ENABLED'
      value: 'true'
    }
    {
      name: 'OTEL_SERVICE_NAME'
      value: 'email-scheduler'
    }
  ],
  !empty(emailSmtpPassword)
    ? [
        {
          name: 'EMAIL_SMTP_PASSWORD'
          secretRef: 'email-smtp-password'
        }
      ]
    : [],
  !empty(applicationInsightsConnectionString)
    ? [
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          secretRef: 'applicationinsights-connection-string'
        }
      ]
    : []
)

var emailSchedulerCommand = runScheduler ? [
  'python'
] : [
  '/bin/sh'
]

var emailSchedulerArgs = runScheduler ? [
  '-m'
  'app.email_scheduler_job_main'
] : [
  '-c'
  'echo email scheduler shell provisioned; exit 0'
]

resource emailSchedulerJob 'Microsoft.App/jobs@2024-03-01' = {
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
      secrets: emailSchedulerSecrets
    }
    template: {
      containers: [
        {
          name: 'email-scheduler'
          image: image
          command: emailSchedulerCommand
          args: emailSchedulerArgs
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: emailSchedulerEnv
        }
      ]
    }
  }
  dependsOn: [
    acrPullRoleAssignment
  ]
}

output jobName string = emailSchedulerJob.name
