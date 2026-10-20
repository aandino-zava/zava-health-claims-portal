targetScope = 'resourceGroup'

@description('Short unique prefix, lowercase letters and digits only.')
@minLength(3)
@maxLength(16)
param prefix string
param location string = 'centralus'
@description('App Service region; a different region creates a peered web VNet without moving the database.')
param appServiceLocation string = location
@allowed(['containerapps', 'appservice'])
param hosting string = 'appservice'
@secure()
param databasePassword string
param databaseUser string = 'claimsadmin'
param databaseSku string = 'Standard_D2ads_v5'
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param databaseTier string = 'GeneralPurpose'
@description('Stable PostgreSQL server name. Override only for a deliberately new database.')
param databaseServerName string = '${prefix}-${uniqueString(resourceGroup().id)}-pg'
@description('Optional explicit globally unique registry name. Keep stable after deployment.')
param registryName string = '${prefix}${uniqueString(resourceGroup().id)}'

var separateWebRegion = hosting == 'appservice' && appServiceLocation != location

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-runtime'
  location: location
}
resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, 'AcrPull')
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}
resource network 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: '${prefix}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.72.0.0/16'] }
    subnets: concat(hosting == 'containerapps' ? [
      {
        name: 'containers'
        properties: {
          addressPrefix: '10.72.0.0/23'
          delegations: [{ name: 'containerapps', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
    ] : [], [
      {
        name: 'database'
        properties: {
          addressPrefix: '10.72.2.0/24'
          delegations: [{ name: 'postgresql', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }]
        }
      }
    ], hosting == 'appservice' ? [
      {
        name: 'web'
        properties: {
          addressPrefix: '10.72.3.0/24'
          delegations: [{ name: 'appservice', properties: { serviceName: 'Microsoft.Web/serverFarms' } }]
        }
      }
    ] : [])
  }
}
resource dns 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: '${prefix}.private.postgres.database.azure.com'
  location: 'global'
}
resource webNetwork 'Microsoft.Network/virtualNetworks@2023-11-01' = if (separateWebRegion) {
  name: '${prefix}-web-vnet'
  location: appServiceLocation
  properties: {
    addressSpace: { addressPrefixes: ['10.73.0.0/16'] }
    subnets: [{
      name: 'web'
      properties: {
        addressPrefix: '10.73.3.0/24'
        delegations: [{ name: 'appservice', properties: { serviceName: 'Microsoft.Web/serverFarms' } }]
      }
    }]
  }
}
resource webToDatabase 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-11-01' = if (separateWebRegion) {
  parent: webNetwork
  name: 'to-database'
  properties: {
    remoteVirtualNetwork: { id: network.id }
    allowVirtualNetworkAccess: true
  }
}
resource databaseToWeb 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-11-01' = if (separateWebRegion) {
  parent: network
  name: 'to-web'
  properties: {
    remoteVirtualNetwork: { id: webNetwork!.id }
    allowVirtualNetworkAccess: true
  }
}
resource webDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (separateWebRegion) {
  parent: dns
  name: '${prefix}-web-link'
  location: 'global'
  properties: { registrationEnabled: false, virtualNetwork: { id: webNetwork!.id } }
}
resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: dns
  name: '${prefix}-link'
  location: 'global'
  properties: { registrationEnabled: false, virtualNetwork: { id: network.id } }
}
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: databaseServerName
  location: location
  sku: { name: databaseSku, tier: databaseTier }
  properties: {
    version: '16'
    administratorLogin: databaseUser
    administratorLoginPassword: databasePassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: {
      delegatedSubnetResourceId: '${network.id}/subnets/database'
      privateDnsZoneArmResourceId: dns.id
      publicNetworkAccess: 'Disabled'
    }
  }
  dependsOn: [dnsLink]
}
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'claims'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}
resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = if (hosting == 'containerapps') {
  name: '${prefix}-env'
  location: location
  properties: {
    vnetConfiguration: { infrastructureSubnetId: '${network.id}/subnets/containers' }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}
output registryName string = registry.name
output registryServer string = registry.properties.loginServer
output environmentId string = hosting == 'containerapps' ? environment!.id : ''
output webSubnetId string = separateWebRegion ? '${webNetwork!.id}/subnets/web' : '${network.id}/subnets/web'
output identityId string = identity.id
output databaseHost string = postgres.properties.fullyQualifiedDomainName
output logsWorkspaceId string = logs.id
