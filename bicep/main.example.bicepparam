using './main.bicep'

param location = 'eastus2'
param projectName = 'docpipeline'
param environment = 'dev'

// Optional. Leave empty for generated values.
param resourceGroupName = ''
param nameSuffix = ''

param vnetAddressSpace = [
  '10.0.0.0/16'
]
param containerAppSubnetCidr = '10.0.0.0/23'
param privateEndpointsSubnetCidr = '10.0.2.0/24'
param aiServicesSubnetCidr = '10.0.3.0/24'
param logicAppIntegrationSubnetCidr = '10.0.4.0/26'

param openaiModelName = 'gpt-5.1'
param openaiModelVersion = '2025-11-13'
param openaiModelSkuName = 'GlobalStandard'
param openaiModelCapacity = 30
param openaiApiVersion = '2025-04-01-preview'
param embeddingModelName = 'text-embedding-3-small'
param embeddingModelVersion = '1'
param embeddingModelSkuName = 'GlobalStandard'
param embeddingModelCapacity = 30
param openaiEmbeddingApiVersion = '2024-12-01-preview'

param containerImage = 'docpipeline:latest'
param containerCpu = '1.0'
param containerMemory = '2Gi'
param containerMinReplicas = 1
param containerMaxReplicas = 3
param searchDefaultTop = 30
param searchMaxTop = 1000
param backfillDefaultLimit = 25
param backfillMaxLimit = 200
param reprocessDefaultLimit = 100
param reprocessMaxLimit = 5000
param logicAppSkuName = 'WS1'
param logicAppSkuCapacity = 1
param cosmosThroughputMode = 'Serverless'

// Add public client/admin IPs that need portal or data-plane access to Storage here.
// These IPs are also allowed through the Network Security Perimeter.
param allowedIpAddresses = [
  '71.200.56.126'
]
// Add public client/admin IPs that only need Cosmos DB data-plane read/query access here.
param cosmosAllowedIpAddresses = [
  // '203.0.113.10'
]
param additionalNspSubscriptionIds = [
  '4345216c-3da4-4537-97ff-2a9f5053a420'
]

// Optional legacy single-principal Cosmos reader value. Prefer operatorPrincipalObjectIds.
param deployerPrincipalId = ''

// Optional operator/admin principals. Use Microsoft Entra object IDs for users,
// groups, service principals, or managed identities that should upload/read blobs,
// query Cosmos DB data, and call Azure Maps search/render APIs.
param operatorPrincipalObjectIds = [
  // '00000000-0000-0000-0000-000000000000'
]

// Bicep cannot emit a new Entra app client secret. Create/provide an app registration if Easy Auth is required.
param enableEasyAuth = false
param easyAuthClientId = ''
param easyAuthClientSecret = ''

// For first deploy or Event Grid changes, keep true. Bicep stages the Storage
// NSP association through Learning -> Event Grid -> Enforced using nested modules.
// Set false on later redeploys when no Event Grid update is needed.
param manageEventGridSubscription = true

param tags = {
  owner: 'your-team'
}
