targetScope = 'resourceGroup'
param prefix string
param location string = 'centralus'
param environmentId string
param identityId string
param registryServer string
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
@description('Comma-separated allowed client IDs, including the SPA and approved agent clients.')
param allowedClientIds string
param seedDemo bool = true

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-portal'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      registries: [{ server: registryServer, identity: identityId }]
      secrets: [{
        name: 'database-url'
        value: 'postgresql+psycopg://${appDatabaseUser}:${uriComponent(appDatabasePassword)}@${databaseHost}:5432/claims?sslmode=require'
      }, {
        name: 'migration-database-url'
        value: 'postgresql+psycopg://${databaseUser}:${uriComponent(databasePassword)}@${databaseHost}:5432/claims?sslmode=require'
      }]
    }
    template: {
      containers: [{
        name: 'portal'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'ENVIRONMENT', value: 'production' }
          { name: 'AUTH_MODE', value: 'entra' }
          { name: 'DATABASE_URL', secretRef: 'database-url' }
          { name: 'MIGRATION_DATABASE_URL', secretRef: 'migration-database-url' }
          { name: 'ENTRA_TENANT_ID', value: tenantId }
          { name: 'ENTRA_API_CLIENT_ID', value: apiClientId }
          { name: 'ENTRA_SPA_CLIENT_ID', value: spaClientId }
          { name: 'ENTRA_ALLOWED_CLIENT_IDS', value: allowedClientIds }
          { name: 'SEED_DEMO', value: string(seedDemo) }
        ]
        probes: [
          { type: 'Startup', httpGet: { path: '/health/ready', port: 8000 }, periodSeconds: 5, failureThreshold: 60 }
          { type: 'Readiness', httpGet: { path: '/health/ready', port: 8000 }, periodSeconds: 10, failureThreshold: 3 }
          { type: 'Liveness', httpGet: { path: '/health/live', port: 8000 }, periodSeconds: 20, failureThreshold: 3 }
        ]
      }]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}
output portalUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
