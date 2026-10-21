targetScope = 'resourceGroup'
param prefix string
@description('Optional explicit globally unique web app name. Keep stable after deployment.')
param webAppName string = '${prefix}-${uniqueString(resourceGroup().id)}-portal'
param location string = 'centralus'
param identityId string
param image string
param databaseHost string
param databaseUser string = 'claimsadmin'
@secure()
param databasePassword string
@secure()
param appDatabasePassword string
param appDatabaseUser string = 'claims_app'
param tenantId string
param apiClientId string
param spaClientId string
param allowedClientIds string
param webSubnetId string
param logsWorkspaceId string
param seedDemo bool = true
@description('Optional fictional-claims concierge connection. Supply destination identifiers, never credentials.')
param conciergeConfig object = {}
@allowed(['B1', 'B2', 'B3', 'S1', 'S2', 'S3', 'P0v3', 'P1v3', 'P2v3', 'P3v3'])
param appServiceSku string = 'B1'

var appServiceTier = startsWith(appServiceSku, 'B') ? 'Basic' : (startsWith(appServiceSku, 'S') ? 'Standard' : 'PremiumV3')

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: last(split(identityId, '/'))
}
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${prefix}-plan'
  location: location
  kind: 'linux'
  sku: { name: appServiceSku, tier: appServiceTier, capacity: 1 }
  properties: { reserved: true }
}
resource app 'Microsoft.Web/sites@2023-12-01' = {
  name: webAppName
  location: location
  kind: 'app,linux,container'
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: webSubnetId
    siteConfig: {
      linuxFxVersion: 'DOCKER|${image}'
      acrUseManagedIdentityCreds: true
      acrUserManagedIdentityID: identity.properties.clientId
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      healthCheckPath: '/health/ready'
      appSettings: [
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'WEBSITE_WARMUP_PATH', value: '/health/ready' }
        { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: '1800' }
        { name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE', value: 'false' }
        { name: 'ENVIRONMENT', value: 'production' }
        { name: 'AUTH_MODE', value: 'entra' }
        { name: 'DATABASE_URL', value: 'postgresql+psycopg://${appDatabaseUser}:${uriComponent(appDatabasePassword)}@${databaseHost}:5432/claims?sslmode=require' }
        { name: 'MIGRATION_DATABASE_URL', value: 'postgresql+psycopg://${databaseUser}:${uriComponent(databasePassword)}@${databaseHost}:5432/claims?sslmode=require' }
        { name: 'ENTRA_TENANT_ID', value: tenantId }
        { name: 'ENTRA_API_CLIENT_ID', value: apiClientId }
        { name: 'ENTRA_SPA_CLIENT_ID', value: spaClientId }
        { name: 'ENTRA_ALLOWED_CLIENT_IDS', value: allowedClientIds }
        { name: 'SEED_DEMO', value: string(seedDemo) }
        { name: 'CONCIERGE_ENABLED', value: string(conciergeConfig.?enabled ?? false) }
        { name: 'CONCIERGE_DATAVERSE_URL', value: conciergeConfig.?dataverseUrl ?? '' }
        { name: 'CONCIERGE_IDENTITY_CLIENT_ID', value: conciergeConfig.?identityClientId ?? '' }
        { name: 'CONCIERGE_REVIEWER_OBJECT_ID', value: conciergeConfig.?reviewerObjectId ?? '' }
        { name: 'CONCIERGE_REVIEWER_USER_ID', value: conciergeConfig.?reviewerUserId ?? '' }
        { name: 'CONCIERGE_ALLOWED_CLAIM_IDS', value: conciergeConfig.?allowedClaimIds ?? '' }
      ]
    }
  }
}
resource ftpPolicy 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: app
  name: 'ftp'
  properties: { allow: false }
}
resource scmPolicy 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: app
  name: 'scm'
  properties: { allow: false }
}
resource consoleLogging 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: app
  name: 'logs'
  properties: {
    httpLogs: { fileSystem: { enabled: true, retentionInDays: 3, retentionInMb: 100 } }
    detailedErrorMessages: { enabled: false }
    failedRequestsTracing: { enabled: false }
  }
}
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'console-to-workspace'
  scope: app
  properties: {
    workspaceId: logsWorkspaceId
    logs: [{ category: 'AppServiceConsoleLogs', enabled: true }]
  }
}
output portalUrl string = 'https://${app.properties.defaultHostName}'
