targetScope = 'subscription'

@description('Azure region for all resources.')
param location string = 'eastus2'

@description('Short project name used as a prefix.')
@minLength(3)
param projectName string = 'docpipeline'

@description('Environment name, such as dev, test, staging, or prod.')
param environment string = 'dev'

@description('Optional resource group name. If empty, a name is generated from the project, environment, and suffix.')
param resourceGroupName string = ''

@description('Optional 6-character naming suffix. If empty, a deterministic suffix is generated.')
param nameSuffix string = ''

@description('Address space for the VNet.')
param vnetAddressSpace array = [
  '10.0.0.0/16'
]

@description('CIDR for the Container Apps subnet.')
param containerAppSubnetCidr string = '10.0.0.0/23'

@description('CIDR for the private endpoints subnet.')
param privateEndpointsSubnetCidr string = '10.0.2.0/24'

@description('CIDR for the AI services subnet.')
param aiServicesSubnetCidr string = '10.0.3.0/24'

@description('CIDR for the shared App Service regional VNet integration subnet used by the Function App and optional Logic App.')
param logicAppIntegrationSubnetCidr string = '10.0.4.0/26'

@description('Azure OpenAI chat model deployment name.')
param openaiModelName string = 'gpt-5.1'

@description('Azure OpenAI chat model version.')
param openaiModelVersion string = '2025-11-13'

@description('Azure OpenAI chat model deployment SKU name.')
param openaiModelSkuName string = 'GlobalStandard'

@description('Azure OpenAI chat model deployment capacity in thousands of TPM.')
param openaiModelCapacity int = 30

@description('Azure OpenAI chat/completions API version.')
param openaiApiVersion string = '2025-04-01-preview'

@description('Azure OpenAI embedding model deployment name.')
param embeddingModelName string = 'text-embedding-3-small'

@description('Azure OpenAI embedding model version.')
param embeddingModelVersion string = '1'

@description('Azure OpenAI embedding model deployment SKU name.')
param embeddingModelSkuName string = 'GlobalStandard'

@description('Azure OpenAI embedding model deployment capacity in thousands of TPM.')
param embeddingModelCapacity int = 30

@description('Azure OpenAI embeddings API version.')
param openaiEmbeddingApiVersion string = '2024-12-01-preview'

@description('Container image name. Use either docpipeline:latest or a fully qualified image reference.')
param containerImage string = 'docpipeline:latest'

@description('Container CPU cores.')
param containerCpu string = '1.0'

@description('Container memory in Gi.')
param containerMemory string = '2Gi'

@description('Minimum Container App replicas.')
param containerMinReplicas int = 1

@description('Maximum Container App replicas.')
param containerMaxReplicas int = 3

@description('Default number of results returned by search endpoints when top is omitted.')
param searchDefaultTop int = 30

@description('Maximum top value accepted by search endpoints.')
param searchMaxTop int = 1000

@description('Default number of result documents scanned by each search-index backfill batch.')
param backfillDefaultLimit int = 25

@description('Maximum number of result documents accepted by each search-index backfill batch.')
param backfillMaxLimit int = 200

@description('Default number of ingest blobs scanned by each requeue batch.')
param reprocessDefaultLimit int = 100

@description('Maximum number of ingest blobs accepted by each requeue batch.')
param reprocessMaxLimit int = 5000

@allowed([
  'WS1'
  'WS2'
  'WS3'
])
@description('Logic App Standard Workflow Service Plan SKU.')
param logicAppSkuName string = 'WS1'

@minValue(1)
@description('Logic App Standard plan instance count.')
param logicAppSkuCapacity int = 1

@allowed([
  'EP1'
  'EP2'
  'EP3'
])
@description('Azure Functions Elastic Premium SKU for the Power Platform search facade.')
param searchFunctionSkuName string = 'EP1'

@minValue(1)
@description('Azure Functions Elastic Premium plan instance count for the Power Platform search facade.')
param searchFunctionSkuCapacity int = 1

@allowed([
  'Serverless'
])
@description('Cosmos DB capacity mode. Terraform currently deploys serverless only.')
param cosmosThroughputMode string = 'Serverless'

@description('Public IP addresses allowed to reach shared limited public endpoints, such as Storage firewall and NSP access rules.')
param allowedIpAddresses array = [
  '71.200.56.126'
]

@description('Additional public IP addresses allowed to reach Cosmos DB data-plane APIs only.')
param cosmosAllowedIpAddresses array = []

@description('Additional subscription IDs allowed by the Network Security Perimeter inbound rule.')
param additionalNspSubscriptionIds array = [
  '4345216c-3da4-4537-97ff-2a9f5053a420'
]

@description('Optional deploying user/service principal object ID for backward-compatible Cosmos read permissions. Prefer operatorPrincipalObjectIds for new deployments.')
param deployerPrincipalId string = ''

@description('Microsoft Entra user, group, service principal, or managed identity object IDs that should receive operator data access to Storage blobs, Cosmos DB for NoSQL read/query access, and Azure Maps search/render access.')
param operatorPrincipalObjectIds array = []

@description('Enable Container Apps Easy Auth. Requires an existing Entra app client ID and secret.')
param enableEasyAuth bool = false

@description('Existing Entra app client ID used by Container Apps Easy Auth.')
param easyAuthClientId string = ''

@secure()
@description('Existing Entra app client secret used by Container Apps Easy Auth.')
param easyAuthClientSecret string = ''

@description('Tenant ID used for the Easy Auth OpenID issuer.')
param easyAuthIssuerTenantId string = tenant().tenantId

@description('Deploy or update the Storage BlobCreated Event Grid subscription. When true, nested modules stage the Storage NSP association through Learning mode, create/update Event Grid, then restore Enforced mode. Set false for later redeploys when no Event Grid update is needed.')
param manageEventGridSubscription bool = true

@description('Tags applied to all resources.')
param tags object = {}

var suffix = !empty(nameSuffix) ? toLower(nameSuffix) : take(toLower(uniqueString(subscription().id, projectName, environment, location)), 6)
var namePrefix = '${projectName}-${environment}'
var generatedResourceGroupName = 'rg-${namePrefix}-${suffix}'
var effectiveResourceGroupName = !empty(resourceGroupName) ? resourceGroupName : generatedResourceGroupName
var commonTags = union(tags, {
  project: projectName
  environment: environment
  managed_by: 'bicep'
})

resource resourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: effectiveResourceGroupName
  location: location
  tags: commonTags
}

module documentPipeline './modules/document-pipeline.bicep' = {
  scope: resourceGroup
  params: {
    location: location
    projectName: projectName
    environment: environment
    nameSuffix: suffix
    vnetAddressSpace: vnetAddressSpace
    containerAppSubnetCidr: containerAppSubnetCidr
    privateEndpointsSubnetCidr: privateEndpointsSubnetCidr
    aiServicesSubnetCidr: aiServicesSubnetCidr
    logicAppIntegrationSubnetCidr: logicAppIntegrationSubnetCidr
    openaiModelName: openaiModelName
    openaiModelVersion: openaiModelVersion
    openaiModelSkuName: openaiModelSkuName
    openaiModelCapacity: openaiModelCapacity
    openaiApiVersion: openaiApiVersion
    embeddingModelName: embeddingModelName
    embeddingModelVersion: embeddingModelVersion
    embeddingModelSkuName: embeddingModelSkuName
    embeddingModelCapacity: embeddingModelCapacity
    openaiEmbeddingApiVersion: openaiEmbeddingApiVersion
    containerImage: containerImage
    containerCpu: containerCpu
    containerMemory: containerMemory
    containerMinReplicas: containerMinReplicas
    containerMaxReplicas: containerMaxReplicas
    searchDefaultTop: searchDefaultTop
    searchMaxTop: searchMaxTop
    backfillDefaultLimit: backfillDefaultLimit
    backfillMaxLimit: backfillMaxLimit
    reprocessDefaultLimit: reprocessDefaultLimit
    reprocessMaxLimit: reprocessMaxLimit
    logicAppSkuName: logicAppSkuName
    logicAppSkuCapacity: logicAppSkuCapacity
    searchFunctionSkuName: searchFunctionSkuName
    searchFunctionSkuCapacity: searchFunctionSkuCapacity
    cosmosThroughputMode: cosmosThroughputMode
    allowedIpAddresses: allowedIpAddresses
    cosmosAllowedIpAddresses: cosmosAllowedIpAddresses
    additionalNspSubscriptionIds: additionalNspSubscriptionIds
    deployerPrincipalId: deployerPrincipalId
    operatorPrincipalObjectIds: operatorPrincipalObjectIds
    enableEasyAuth: enableEasyAuth
    easyAuthClientId: easyAuthClientId
    easyAuthClientSecret: easyAuthClientSecret
    easyAuthIssuerTenantId: easyAuthIssuerTenantId
    manageEventGridSubscription: manageEventGridSubscription
    tags: commonTags
  }
}

output resourceGroupName string = resourceGroup.name
output storageAccountName string = documentPipeline.outputs.storageAccountName
output storageBlobEndpoint string = documentPipeline.outputs.storageBlobEndpoint
output cosmosEndpoint string = documentPipeline.outputs.cosmosEndpoint
output openaiEndpoint string = documentPipeline.outputs.openaiEndpoint
output docintelEndpoint string = documentPipeline.outputs.docintelEndpoint
output azureMapsAccountName string = documentPipeline.outputs.azureMapsAccountName
output azureMapsClientId string = documentPipeline.outputs.azureMapsClientId
output acrLoginServer string = documentPipeline.outputs.acrLoginServer
output containerAppFqdn string = documentPipeline.outputs.containerAppFqdn
output containerAppUrl string = documentPipeline.outputs.containerAppUrl
output logicAppName string = documentPipeline.outputs.logicAppName
output logicAppUrl string = documentPipeline.outputs.logicAppUrl
output searchFunctionAppName string = documentPipeline.outputs.searchFunctionAppName
output searchFunctionAppUrl string = documentPipeline.outputs.searchFunctionAppUrl
output easyAuthRedirectUri string = documentPipeline.outputs.easyAuthRedirectUri
output logAnalyticsWorkspaceId string = documentPipeline.outputs.logAnalyticsWorkspaceId
output logAnalyticsWorkspaceName string = documentPipeline.outputs.logAnalyticsWorkspaceName
output networkSecurityPerimeterName string = documentPipeline.outputs.networkSecurityPerimeterName
