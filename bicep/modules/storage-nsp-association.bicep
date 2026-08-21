targetScope = 'resourceGroup'

@description('Azure region for the Network Security Perimeter association.')
param location string

@description('Network Security Perimeter name.')
param networkSecurityPerimeterName string

@description('Storage NSP association name.')
param associationName string

@allowed([
  'Learning'
  'Enforced'
  'Audit'
])
@description('Access mode on the Storage NSP association.')
param accessMode string

@description('Storage account resource ID associated with the Network Security Perimeter.')
param storageAccountId string

@description('Network Security Perimeter profile resource ID.')
param profileId string

resource nsp 'Microsoft.Network/networkSecurityPerimeters@2023-08-01-preview' existing = {
  name: networkSecurityPerimeterName
}

resource storageAssociation 'Microsoft.Network/networkSecurityPerimeters/resourceAssociations@2023-08-01-preview' = {
  parent: nsp
  name: associationName
  location: location
  properties: {
    accessMode: accessMode
    privateLinkResource: {
      id: storageAccountId
    }
    profile: {
      id: profileId
    }
  }
}
