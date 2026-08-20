targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string

@description('Short project name used as a prefix.')
@minLength(3)
param projectName string

@description('Environment name.')
param environment string

@description('Naming suffix.')
@minLength(6)
param nameSuffix string

@description('Address space for the VNet.')
param vnetAddressSpace array

@description('CIDR for the Container Apps subnet.')
param containerAppSubnetCidr string

@description('CIDR for the private endpoints subnet.')
param privateEndpointsSubnetCidr string

@description('CIDR for the AI services subnet.')
param aiServicesSubnetCidr string

@description('CIDR for the shared App Service regional VNet integration subnet used by the Function App and optional Logic App.')
param logicAppIntegrationSubnetCidr string

@description('Azure OpenAI chat model deployment name.')
param openaiModelName string

@description('Azure OpenAI chat model version.')
param openaiModelVersion string

@description('Azure OpenAI chat model deployment SKU name.')
param openaiModelSkuName string

@description('Azure OpenAI chat model deployment capacity in thousands of TPM.')
param openaiModelCapacity int

@description('Azure OpenAI chat/completions API version.')
param openaiApiVersion string

@description('Azure OpenAI embedding model deployment name.')
param embeddingModelName string

@description('Azure OpenAI embedding model version.')
param embeddingModelVersion string

@description('Azure OpenAI embedding model deployment SKU name.')
param embeddingModelSkuName string

@description('Azure OpenAI embedding model deployment capacity in thousands of TPM.')
param embeddingModelCapacity int

@description('Azure OpenAI embeddings API version.')
param openaiEmbeddingApiVersion string

@description('Container image name or fully qualified image reference.')
param containerImage string

@description('Container CPU cores.')
param containerCpu string

@description('Container memory in Gi.')
param containerMemory string

@description('Minimum Container App replicas.')
param containerMinReplicas int

@description('Maximum Container App replicas.')
param containerMaxReplicas int

@description('Default number of results returned by search endpoints when top is omitted.')
param searchDefaultTop int

@description('Maximum top value accepted by search endpoints.')
param searchMaxTop int

@description('Default number of result documents scanned by each search-index backfill batch.')
param backfillDefaultLimit int

@description('Maximum number of result documents accepted by each search-index backfill batch.')
param backfillMaxLimit int

@description('Default number of ingest blobs scanned by each requeue batch.')
param reprocessDefaultLimit int

@description('Maximum number of ingest blobs accepted by each requeue batch.')
param reprocessMaxLimit int

@allowed([
  'WS1'
  'WS2'
  'WS3'
])
@description('Logic App Standard Workflow Service Plan SKU.')
param logicAppSkuName string

@minValue(1)
@description('Logic App Standard plan instance count.')
param logicAppSkuCapacity int

@allowed([
  'EP1'
  'EP2'
  'EP3'
])
@description('Azure Functions Elastic Premium SKU for the Power Platform search facade.')
param searchFunctionSkuName string

@minValue(1)
@description('Azure Functions Elastic Premium plan instance count for the Power Platform search facade.')
param searchFunctionSkuCapacity int

@description('Cosmos DB capacity mode.')
param cosmosThroughputMode string

@description('Public IP addresses allowed to reach shared limited public endpoints, such as Storage firewall and NSP access rules.')
param allowedIpAddresses array

@description('Additional public IP addresses allowed to reach Cosmos DB data-plane APIs only.')
param cosmosAllowedIpAddresses array

@description('Additional subscription IDs allowed by the Network Security Perimeter inbound rule.')
param additionalNspSubscriptionIds array

@description('Optional deploying user/service principal object ID for backward-compatible Cosmos read permissions. Prefer operatorPrincipalObjectIds for new deployments.')
param deployerPrincipalId string

@description('Microsoft Entra user, group, service principal, or managed identity object IDs that should receive operator data access to Storage blobs, Cosmos DB for NoSQL read/query access, and Azure Maps search/render access.')
param operatorPrincipalObjectIds array

@description('Enable Container Apps Easy Auth.')
param enableEasyAuth bool

@description('Existing Entra app client ID used by Container Apps Easy Auth.')
param easyAuthClientId string

@secure()
@description('Existing Entra app client secret used by Container Apps Easy Auth.')
param easyAuthClientSecret string

@description('Tenant ID used for the Easy Auth OpenID issuer.')
param easyAuthIssuerTenantId string

@description('Deploy or update the Storage BlobCreated Event Grid subscription. When true, nested modules temporarily place the Storage NSP association in Learning mode, create/update Event Grid, then restore Enforced mode.')
param manageEventGridSubscription bool

@description('Tags applied to all resources.')
param tags object

var namePrefix = '${projectName}-${environment}'
var compactProjectName = toLower(replace(projectName, '-', ''))
var storageAccountName = take('st${compactProjectName}${nameSuffix}', 24)
var logicAppStorageAccountName = take('stlogic${compactProjectName}${nameSuffix}', 24)
var logicAppContentShareName = take('logicapp${nameSuffix}', 63)
var searchFunctionStorageAccountName = take('stfunc${compactProjectName}${nameSuffix}', 24)
var searchFunctionContentShareName = take('funcapp${nameSuffix}', 63)
var acrName = take('acr${compactProjectName}${nameSuffix}', 50)
var containerAppImage = contains(containerImage, '/') ? containerImage : '${acr.properties.loginServer}/${containerImage}'
var shouldEnableEasyAuth = enableEasyAuth && !empty(easyAuthClientId) && !empty(easyAuthClientSecret)
var effectiveOperatorPrincipalObjectIds = union(operatorPrincipalObjectIds, !empty(deployerPrincipalId) ? [
  deployerPrincipalId
] : [])
var allowedIpCidrs = [for ip in allowedIpAddresses: contains(ip, '/') ? ip : '${ip}/32']
var effectiveCosmosAllowedIpAddresses = union(allowedIpAddresses, cosmosAllowedIpAddresses)
var nspSubscriptionIds = concat([
  subscription().subscriptionId
], additionalNspSubscriptionIds)
var nspName = 'nsp-${namePrefix}-${nameSuffix}'
var storageNspAssociationName = 'assoc-storage'
var eventGridSystemTopicName = 'evgt-${namePrefix}-${nameSuffix}'
var blobCreatedEventSubscriptionName = 'sub-blob-created'
var nspDiagnosticLogCategories = [
  'NspPublicInboundPerimeterRulesAllowed'
  'NspPublicInboundPerimeterRulesDenied'
  'NspPublicOutboundPerimeterRulesAllowed'
  'NspPublicOutboundPerimeterRulesDenied'
  'NspIntraPerimeterInboundAllowed'
  'NspPublicInboundResourceRulesAllowed'
  'NspPublicInboundResourceRulesDenied'
  'NspPublicOutboundResourceRulesAllowed'
  'NspPublicOutboundResourceRulesDenied'
  'NspPrivateInboundAllowed'
  'NspCrossPerimeterOutboundAllowed'
  'NspCrossPerimeterInboundAllowed'
  'NspOutboundAttempt'
]
var cosmosCapabilities = cosmosThroughputMode == 'Serverless' ? [
  {
    name: 'EnableServerless'
  }
  {
    name: 'EnableNoSQLVectorSearch'
  }
] : [
  {
    name: 'EnableNoSQLVectorSearch'
  }
]
var storagePrivateDnsZoneName = 'privatelink.blob.${az.environment().suffixes.storage}'

var roleAcrPull = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var roleReader = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
var roleStorageBlobDataContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var roleStorageBlobDelegator = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a')
var roleCosmosAccountReader = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'fbdf93bf-df7d-467e-a4d2-9458aa1360c8')
var roleCognitiveServicesOpenAIUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
var roleCognitiveServicesUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
var roleAzureMapsSearchRenderDataReader = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '6be48352-4f82-47c9-ad5e-0acacefdb005')

resource containerAppsNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: 'nsg-container-apps-${nameSuffix}'
  location: location
  tags: tags
}

resource privateEndpointsNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: 'nsg-private-endpoints-${nameSuffix}'
  location: location
  tags: tags
}

resource aiServicesNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: 'nsg-ai-services-${nameSuffix}'
  location: location
  tags: tags
}

resource logicAppIntegrationNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: 'nsg-logic-app-integration-${nameSuffix}'
  location: location
  tags: tags
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-07-01' = {
  name: 'vnet-${namePrefix}-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: vnetAddressSpace
    }
    subnets: [
      {
        name: 'snet-container-apps'
        properties: {
          addressPrefix: containerAppSubnetCidr
          defaultOutboundAccess: false
          networkSecurityGroup: {
            id: containerAppsNsg.id
          }
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
          ]
          delegations: [
            {
              name: 'container-app-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: privateEndpointsSubnetCidr
          defaultOutboundAccess: false
          networkSecurityGroup: {
            id: privateEndpointsNsg.id
          }
        }
      }
      {
        name: 'snet-ai-services'
        properties: {
          addressPrefix: aiServicesSubnetCidr
          defaultOutboundAccess: false
          networkSecurityGroup: {
            id: aiServicesNsg.id
          }
        }
      }
      {
        name: 'snet-logic-app-integration'
        properties: {
          addressPrefix: logicAppIntegrationSubnetCidr
          defaultOutboundAccess: false
          networkSecurityGroup: {
            id: logicAppIntegrationNsg.id
          }
          delegations: [
            {
              name: 'logic-app-integration-delegation'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
    ]
  }
}

var containerAppsSubnetId = '${vnet.id}/subnets/snet-container-apps'
var privateEndpointsSubnetId = '${vnet.id}/subnets/snet-private-endpoints'
var logicAppIntegrationSubnetId = '${vnet.id}/subnets/snet-logic-app-integration'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: 'law-${namePrefix}-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'ai-${namePrefix}-${nameSuffix}'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
      ipRules: [for ip in allowedIpAddresses: {
        action: 'Allow'
        value: ip
      }]
      virtualNetworkRules: [
        {
          action: 'Allow'
          id: containerAppsSubnetId
        }
      ]
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = {
  parent: storage
  name: 'default'
  properties: {
    cors: {
      corsRules: [
        {
          allowedHeaders: [
            '*'
          ]
          allowedMethods: [
            'GET'
            'HEAD'
            'PUT'
            'DELETE'
            'OPTIONS'
          ]
          allowedOrigins: [
            'https://portal.azure.com'
            'https://ms.portal.azure.com'
          ]
          exposedHeaders: [
            '*'
          ]
          maxAgeInSeconds: 3600
        }
      ]
    }
    isVersioningEnabled: true
  }
}

resource ingestContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: 'ingest'
  properties: {
    publicAccess: 'None'
  }
}

resource processingContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: 'processing'
  properties: {
    publicAccess: 'None'
  }
}

resource completedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: 'completed'
  properties: {
    publicAccess: 'None'
  }
}

resource originalContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: 'originaldocument'
  properties: {
    publicAccess: 'None'
  }
}

resource failedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: 'failed'
  properties: {
    publicAccess: 'None'
  }
}

resource logicAppStorage 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: logicAppStorageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    defaultToOAuthAuthentication: false
    minimumTlsVersion: 'TLS1_2'
  }
}

var logicAppStorageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${logicAppStorage.name};EndpointSuffix=${az.environment().suffixes.storage};AccountKey=${logicAppStorage.listKeys().keys[0].value}'

resource logicAppPlan 'Microsoft.Web/serverfarms@2024-11-01' = {
  name: 'plan-logic-${namePrefix}-${nameSuffix}'
  location: location
  tags: tags
  kind: 'elastic'
  sku: {
    name: logicAppSkuName
    tier: 'WorkflowStandard'
    size: logicAppSkuName
    capacity: logicAppSkuCapacity
  }
}

resource searchFunctionStorage 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: searchFunctionStorageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    defaultToOAuthAuthentication: false
    minimumTlsVersion: 'TLS1_2'
  }
}

var searchFunctionStorageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${searchFunctionStorage.name};EndpointSuffix=${az.environment().suffixes.storage};AccountKey=${searchFunctionStorage.listKeys().keys[0].value}'

resource searchFunctionPlan 'Microsoft.Web/serverfarms@2024-11-01' = {
  name: 'plan-func-${namePrefix}-${nameSuffix}'
  location: location
  tags: tags
  kind: 'elastic'
  sku: {
    name: searchFunctionSkuName
    tier: 'ElasticPremium'
    size: searchFunctionSkuName
    capacity: searchFunctionSkuCapacity
  }
  properties: {
    reserved: true
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2025-05-01-preview' = {
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

resource acrPullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-acr-pull-${nameSuffix}'
  location: location
  tags: tags
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, acrPullIdentity.id, roleAcrPull)
  scope: acr
  properties: {
    principalId: acrPullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleAcrPull
  }
}

resource openai 'Microsoft.CognitiveServices/accounts@2025-09-01' = {
  name: 'oai-${namePrefix}-${nameSuffix}'
  location: location
  kind: 'OpenAI'
  tags: tags
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: 'oai-${namePrefix}-${nameSuffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
  }
}

resource gptDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-09-01' = {
  parent: openai
  name: openaiModelName
  sku: {
    name: openaiModelSkuName
    capacity: openaiModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: openaiModelName
      version: openaiModelVersion
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-09-01' = {
  parent: openai
  name: embeddingModelName
  sku: {
    name: embeddingModelSkuName
    capacity: embeddingModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
  }
  dependsOn: [
    gptDeployment
  ]
}

resource docintel 'Microsoft.CognitiveServices/accounts@2025-09-01' = {
  name: 'di-${namePrefix}-${nameSuffix}'
  location: location
  kind: 'FormRecognizer'
  tags: tags
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: 'di-${namePrefix}-${nameSuffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
  }
}

resource maps 'Microsoft.Maps/accounts@2023-06-01' = {
  name: 'maps-${namePrefix}-${nameSuffix}'
  location: 'global'
  kind: 'Gen2'
  tags: tags
  sku: {
    name: 'G2'
  }
  properties: {
    disableLocalAuth: true
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2025-10-15' = {
  name: 'cosmos-${namePrefix}-${nameSuffix}'
  location: location
  kind: 'GlobalDocumentDB'
  tags: tags
  properties: {
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    ipRules: [for ip in effectiveCosmosAllowedIpAddresses: {
      ipAddressOrRange: ip
    }]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        failoverPriority: 0
        locationName: location
      }
    ]
    capabilities: cosmosCapabilities
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2025-10-15' = {
  parent: cosmos
  name: 'docprocessing'
  properties: {
    resource: {
      id: 'docprocessing'
    }
  }
}

resource jobsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15' = {
  parent: cosmosDatabase
  name: 'jobs'
  properties: {
    resource: {
      id: 'jobs'
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/id'
        ]
      }
    }
  }
}

resource resultsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15' = {
  parent: cosmosDatabase
  name: 'results'
  properties: {
    resource: {
      id: 'results'
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/jobId'
        ]
      }
      vectorEmbeddingPolicy: {
        vectorEmbeddings: [
          {
            path: '/summary_vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 1536
          }
          {
            path: '/purpose_vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 1536
          }
          {
            path: '/chunks/vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 1536
          }
        ]
      }
      fullTextPolicy: {
        defaultLanguage: 'en-US'
        fullTextPaths: [
          {
            path: '/search_text'
            language: 'en-US'
          }
        ]
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/summary_vector/*'
          }
          {
            path: '/purpose_vector/*'
          }
          {
            path: '/chunks/vector/*'
          }
          {
            path: '/_etag/?'
          }
        ]
        vectorIndexes: [
          {
            path: '/summary_vector'
            type: 'quantizedFlat'
          }
          {
            path: '/purpose_vector'
            type: 'quantizedFlat'
          }
          {
            path: '/chunks/vector'
            type: 'quantizedFlat'
          }
        ]
        fullTextIndexes: [
          {
            path: '/search_text'
          }
        ]
      }
    }
  }
}

resource operationsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15' = {
  parent: cosmosDatabase
  name: 'operations'
  properties: {
    resource: {
      id: 'operations'
      partitionKey: {
        paths: [
          '/id'
        ]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/results/*'
          }
          {
            path: '/_etag/?'
          }
        ]
      }
    }
  }
}

resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: 'cae-${namePrefix}-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: containerAppsSubnetId
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2025-07-01' = {
  name: 'ca-${namePrefix}-${nameSuffix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned,UserAssigned'
    userAssignedIdentities: {
      '${acrPullIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: acr.properties.loginServer
          identity: acrPullIdentity.id
        }
      ]
      secrets: shouldEnableEasyAuth ? [
        {
          name: 'microsoft-provider-authentication-secret'
          value: easyAuthClientSecret
        }
      ] : []
      ingress: {
        external: true
        targetPort: 8000
        transport: 'Auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
    }
    template: {
      scale: {
        minReplicas: containerMinReplicas
        maxReplicas: containerMaxReplicas
      }
      containers: [
        {
          name: 'docpipeline'
          image: containerAppImage
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: storage.properties.primaryEndpoints.blob
            }
            {
              name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT'
              value: docintel.properties.endpoint
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openai.properties.endpoint
            }
            {
              name: 'AZURE_OPENAI_API_VERSION'
              value: openaiApiVersion
            }
            {
              name: 'AZURE_OPENAI_MODEL_NAME'
              value: openaiModelName
            }
            {
              name: 'AZURE_OPENAI_EMBEDDING_MODEL'
              value: embeddingModelName
            }
            {
              name: 'AZURE_OPENAI_EMBEDDING_API_VERSION'
              value: openaiEmbeddingApiVersion
            }
            {
              name: 'AZURE_MAPS_ENDPOINT'
              value: 'https://atlas.microsoft.com'
            }
            {
              name: 'AZURE_MAPS_CLIENT_ID'
              value: maps.properties.uniqueId
            }
            {
              name: 'AZURE_MAPS_COUNTRY_SET'
              value: 'US'
            }
            {
              name: 'AZURE_MAPS_LANGUAGE'
              value: 'en-US'
            }
            {
              name: 'AZURE_MAPS_FUZZY_SEARCH_LIMIT'
              value: '1'
            }
            {
              name: 'AZURE_MAPS_MAX_FUZZY_LEVEL'
              value: '1'
            }
            {
              name: 'AZURE_MAPS_TIMEOUT_SECONDS'
              value: '10'
            }
            {
              name: 'COSMOS_ENDPOINT'
              value: cosmos.properties.documentEndpoint
            }
            {
              name: 'COSMOS_DATABASE_NAME'
              value: cosmosDatabase.name
            }
            {
              name: 'COSMOS_CONTAINER_OPERATIONS'
              value: operationsContainer.name
            }
            {
              name: 'SEARCH_DEFAULT_TOP'
              value: string(searchDefaultTop)
            }
            {
              name: 'SEARCH_MAX_TOP'
              value: string(searchMaxTop)
            }
            {
              name: 'BACKFILL_DEFAULT_LIMIT'
              value: string(backfillDefaultLimit)
            }
            {
              name: 'BACKFILL_MAX_LIMIT'
              value: string(backfillMaxLimit)
            }
            {
              name: 'REPROCESS_DEFAULT_LIMIT'
              value: string(reprocessDefaultLimit)
            }
            {
              name: 'REPROCESS_MAX_LIMIT'
              value: string(reprocessMaxLimit)
            }
            {
              name: 'STORAGE_CONTAINER_INGEST'
              value: ingestContainer.name
            }
            {
              name: 'STORAGE_CONTAINER_PROCESSING'
              value: processingContainer.name
            }
            {
              name: 'STORAGE_CONTAINER_COMPLETED'
              value: completedContainer.name
            }
            {
              name: 'STORAGE_CONTAINER_ORIGINAL'
              value: originalContainer.name
            }
            {
              name: 'STORAGE_CONTAINER_FAILED'
              value: failedContainer.name
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    acrPullRoleAssignment
    gptDeployment
    embeddingDeployment
  ]
}

resource logicApp 'Microsoft.Web/sites@2024-11-01' = {
  name: 'logic-${namePrefix}-${nameSuffix}'
  location: location
  kind: 'functionapp,workflowapp'
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: logicAppPlan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    virtualNetworkSubnetId: logicAppIntegrationSubnetId
    siteConfig: {
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      vnetRouteAllEnabled: true
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: logicAppStorageConnectionString
        }
        {
          name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
          value: logicAppStorageConnectionString
        }
        {
          name: 'WEBSITE_CONTENTSHARE'
          value: logicAppContentShareName
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'dotnet'
        }
        {
          name: 'APP_KIND'
          value: 'workflowApp'
        }
        {
          name: 'WEBSITE_VNET_ROUTE_ALL'
          value: '1'
        }
        {
          name: 'AzureFunctionsJobHost__extensionBundle__id'
          value: 'Microsoft.Azure.Functions.ExtensionBundle.Workflows'
        }
        {
          name: 'AzureFunctionsJobHost__extensionBundle__version'
          value: '[1.*, 2.0.0)'
        }
        {
          name: 'CONTAINER_APP_BASE_URL'
          value: 'https://${containerApp.properties.configuration.ingress.fqdn}'
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openai.properties.endpoint
        }
        {
          name: 'AZURE_OPENAI_EMBEDDING_MODEL'
          value: embeddingModelName
        }
        {
          name: 'AZURE_OPENAI_EMBEDDING_API_VERSION'
          value: openaiEmbeddingApiVersion
        }
        {
          name: 'SEARCH_DEFAULT_TOP'
          value: string(searchDefaultTop)
        }
        {
          name: 'SEARCH_MAX_TOP'
          value: string(searchMaxTop)
        }
        {
          name: 'SEARCH_DEFAULT_VECTOR_FIELD'
          value: 'summary_vector'
        }
        {
          name: 'Workflows.SearchDocuments.OperationOptions'
          value: 'WithStatelessRunHistory'
        }
      ]
    }
  }
}

resource searchFunctionApp 'Microsoft.Web/sites@2024-11-01' = {
  name: 'func-${namePrefix}-${nameSuffix}'
  location: location
  kind: 'functionapp,linux'
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: searchFunctionPlan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    virtualNetworkSubnetId: logicAppIntegrationSubnetId
    siteConfig: {
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      linuxFxVersion: 'Python|3.11'
      alwaysOn: true
      vnetRouteAllEnabled: true
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: searchFunctionStorageConnectionString
        }
        {
          name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
          value: searchFunctionStorageConnectionString
        }
        {
          name: 'WEBSITE_CONTENTSHARE'
          value: searchFunctionContentShareName
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'AzureWebJobsFeatureFlags'
          value: 'EnableWorkerIndexing'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'ENABLE_ORYX_BUILD'
          value: 'true'
        }
        {
          name: 'WEBSITE_VNET_ROUTE_ALL'
          value: '1'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'CONTAINER_APP_BASE_URL'
          value: 'https://${containerApp.properties.configuration.ingress.fqdn}'
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openai.properties.endpoint
        }
        {
          name: 'AZURE_OPENAI_EMBEDDING_MODEL'
          value: embeddingModelName
        }
        {
          name: 'AZURE_OPENAI_EMBEDDING_API_VERSION'
          value: openaiEmbeddingApiVersion
        }
        {
          name: 'SEARCH_DEFAULT_TOP'
          value: string(searchDefaultTop)
        }
        {
          name: 'SEARCH_MAX_TOP'
          value: string(searchMaxTop)
        }
        {
          name: 'SEARCH_DEFAULT_VECTOR_FIELD'
          value: 'summary_vector'
        }
        {
          name: 'REQUEST_TIMEOUT_SECONDS'
          value: '30'
        }
      ]
    }
  }
}

resource containerAppAuth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (shouldEnableEasyAuth) {
  parent: containerApp
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      excludedPaths: [
        '/api/events/*'
        '/health'
      ]
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: easyAuthClientId
          clientSecretSettingName: 'microsoft-provider-authentication-secret'
          openIdIssuer: 'https://sts.windows.net/${easyAuthIssuerTenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            'api://${easyAuthClientId}'
          ]
        }
      }
    }
    login: {
      tokenStore: {
        enabled: false
      }
    }
  }
}

resource caStorageContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, containerApp.id, roleStorageBlobDataContributor)
  scope: storage
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleStorageBlobDataContributor
  }
}

resource caStorageDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, containerApp.id, roleStorageBlobDelegator)
  scope: storage
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleStorageBlobDelegator
  }
}

resource caCosmosContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-10-15' = {
  parent: cosmos
  name: guid(cosmos.id, containerApp.id, 'cosmos-data-contributor')
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: containerApp.identity.principalId
    scope: cosmos.id
  }
}

resource operatorStorageReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalObjectId in effectiveOperatorPrincipalObjectIds: {
  name: guid(storage.id, principalObjectId, roleReader)
  scope: storage
  properties: {
    principalId: principalObjectId
    roleDefinitionId: roleReader
  }
}]

resource operatorStorageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalObjectId in effectiveOperatorPrincipalObjectIds: {
  name: guid(storage.id, principalObjectId, roleStorageBlobDataContributor)
  scope: storage
  properties: {
    principalId: principalObjectId
    roleDefinitionId: roleStorageBlobDataContributor
  }
}]

resource operatorCosmosReader 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-10-15' = [for principalObjectId in effectiveOperatorPrincipalObjectIds: {
  parent: cosmos
  name: guid(cosmos.id, principalObjectId, 'cosmos-data-reader')
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000001'
    principalId: principalObjectId
    scope: cosmos.id
  }
}]

resource operatorCosmosAccountReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalObjectId in effectiveOperatorPrincipalObjectIds: {
  name: guid(cosmos.id, principalObjectId, roleCosmosAccountReader)
  scope: cosmos
  properties: {
    principalId: principalObjectId
    roleDefinitionId: roleCosmosAccountReader
  }
}]

resource operatorMapsSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalObjectId in effectiveOperatorPrincipalObjectIds: {
  name: guid(maps.id, principalObjectId, roleAzureMapsSearchRenderDataReader)
  scope: maps
  properties: {
    principalId: principalObjectId
    roleDefinitionId: roleAzureMapsSearchRenderDataReader
  }
}]

resource caOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, containerApp.id, roleCognitiveServicesOpenAIUser)
  scope: openai
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleCognitiveServicesOpenAIUser
  }
}

resource logicAppOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, logicApp.id, roleCognitiveServicesOpenAIUser)
  scope: openai
  properties: {
    principalId: logicApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleCognitiveServicesOpenAIUser
  }
}

resource searchFunctionOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, searchFunctionApp.id, roleCognitiveServicesOpenAIUser)
  scope: openai
  properties: {
    principalId: searchFunctionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleCognitiveServicesOpenAIUser
  }
}

resource caDocIntelUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(docintel.id, containerApp.id, roleCognitiveServicesUser)
  scope: docintel
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleCognitiveServicesUser
  }
}

resource caMapsSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(maps.id, containerApp.id, roleAzureMapsSearchRenderDataReader)
  scope: maps
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleAzureMapsSearchRenderDataReader
  }
}

resource blobPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: storagePrivateDnsZoneName
  location: 'global'
  tags: tags
}

resource cosmosPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.documents.azure.com'
  location: 'global'
  tags: tags
}

resource cognitivePrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: tags
}

resource openaiPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
  tags: tags
}

resource monitorPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.monitor.azure.com'
  location: 'global'
  tags: tags
}

resource blobPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: blobPrivateDnsZone
  name: 'link-blob'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource cosmosPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cosmosPrivateDnsZone
  name: 'link-cosmos'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource cognitivePrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cognitivePrivateDnsZone
  name: 'link-cognitive'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource openaiPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: openaiPrivateDnsZone
  name: 'link-openai'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource monitorPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: monitorPrivateDnsZone
  name: 'link-monitor'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = {
  name: 'pe-storage-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointsSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-storage'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

resource storagePrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = {
  parent: storagePrivateEndpoint
  name: 'dns-storage'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: storagePrivateDnsZoneName
        properties: {
          privateDnsZoneId: blobPrivateDnsZone.id
        }
      }
    ]
  }
}

resource cosmosPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = {
  name: 'pe-cosmos-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointsSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-cosmos'
        properties: {
          privateLinkServiceId: cosmos.id
          groupIds: [
            'Sql'
          ]
        }
      }
    ]
  }
}

resource cosmosPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = {
  parent: cosmosPrivateEndpoint
  name: 'dns-cosmos'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink.documents.azure.com'
        properties: {
          privateDnsZoneId: cosmosPrivateDnsZone.id
        }
      }
    ]
  }
}

resource openaiPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = {
  name: 'pe-openai-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointsSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-openai'
        properties: {
          privateLinkServiceId: openai.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
  dependsOn: [
    embeddingDeployment
  ]
}

resource openaiPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = {
  parent: openaiPrivateEndpoint
  name: 'dns-openai'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink.openai.azure.com'
        properties: {
          privateDnsZoneId: openaiPrivateDnsZone.id
        }
      }
    ]
  }
}

resource docintelPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = {
  name: 'pe-docintel-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointsSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-docintel'
        properties: {
          privateLinkServiceId: docintel.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource docintelPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = {
  parent: docintelPrivateEndpoint
  name: 'dns-docintel'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'privatelink.cognitiveservices.azure.com'
        properties: {
          privateDnsZoneId: cognitivePrivateDnsZone.id
        }
      }
    ]
  }
}

resource cosmosDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-cosmos'
  scope: cosmos
  properties: {
    workspaceId: logAnalytics.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        category: 'DataPlaneRequests'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'Requests'
        enabled: true
      }
    ]
  }
}

resource storageBlobDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-storage-blob'
  scope: blobService
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        category: 'StorageRead'
        enabled: true
      }
      {
        category: 'StorageWrite'
        enabled: true
      }
      {
        category: 'StorageDelete'
        enabled: true
      }
    ]
  }
}

resource nsp 'Microsoft.Network/networkSecurityPerimeters@2023-08-01-preview' = {
  name: nspName
  location: location
  tags: tags
  properties: {}
}

resource nspDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-nsp'
  scope: nsp
  properties: {
    workspaceId: logAnalytics.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [for category in nspDiagnosticLogCategories: {
      category: category
      enabled: true
    }]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

resource nspProfile 'Microsoft.Network/networkSecurityPerimeters/profiles@2023-08-01-preview' = {
  parent: nsp
  name: 'profile-acr'
  location: location
  properties: {}
}

resource nspRuleHome 'Microsoft.Network/networkSecurityPerimeters/profiles/accessRules@2023-08-01-preview' = {
  parent: nspProfile
  name: 'home'
  properties: {
    direction: 'Inbound'
    addressPrefixes: allowedIpCidrs
  }
}

resource nspRuleSubscriptions 'Microsoft.Network/networkSecurityPerimeters/profiles/accessRules@2023-08-01-preview' = {
  parent: nspProfile
  name: 'internal_subscriptions'
  properties: {
    direction: 'Inbound'
    subscriptions: [for subscriptionId in nspSubscriptionIds: {
      id: '/subscriptions/${subscriptionId}'
    }]
  }
}

// Event Grid source validation can fail when the Storage account is already NSP Enforced.
// The nested deployments let ARM update the same association in ordered stages.
module storageNspLearning './storage-nsp-association.bicep' = if (manageEventGridSubscription) {
  name: 'deploy-storage-nsp-learning'
  params: {
    location: location
    networkSecurityPerimeterName: nsp.name
    associationName: storageNspAssociationName
    accessMode: 'Learning'
    storageAccountId: storage.id
    profileId: nspProfile.id
  }
  dependsOn: [
    nspRuleHome
    nspRuleSubscriptions
  ]
}

module storageEventGrid './storage-event-grid.bicep' = if (manageEventGridSubscription) {
  name: 'deploy-storage-event-grid'
  params: {
    manageEventGridSubscription: manageEventGridSubscription
    location: location
    systemTopicName: eventGridSystemTopicName
    storageAccountId: storage.id
    eventSubscriptionName: blobCreatedEventSubscriptionName
    webhookEndpointUrl: 'https://${containerApp.properties.configuration.ingress.fqdn}/api/events/blob'
    tags: tags
  }
  dependsOn: [
    storageNspLearning
  ]
}

module storageNspEnforcedAfterEventGrid './storage-nsp-association.bicep' = if (manageEventGridSubscription) {
  name: 'deploy-storage-nsp-enforced-after-event-grid'
  params: {
    location: location
    networkSecurityPerimeterName: nsp.name
    associationName: storageNspAssociationName
    accessMode: 'Enforced'
    storageAccountId: storage.id
    profileId: nspProfile.id
  }
  dependsOn: [
    storageEventGrid
  ]
}

module storageNspEnforcedDirect './storage-nsp-association.bicep' = if (!manageEventGridSubscription) {
  name: 'deploy-storage-nsp-enforced'
  params: {
    location: location
    networkSecurityPerimeterName: nsp.name
    associationName: storageNspAssociationName
    accessMode: 'Enforced'
    storageAccountId: storage.id
    profileId: nspProfile.id
  }
  dependsOn: [
    nspRuleHome
    nspRuleSubscriptions
  ]
}

output storageAccountName string = storage.name
output storageBlobEndpoint string = storage.properties.primaryEndpoints.blob
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output openaiEndpoint string = openai.properties.endpoint
output docintelEndpoint string = docintel.properties.endpoint
output azureMapsAccountName string = maps.name
output azureMapsClientId string = maps.properties.uniqueId
output acrLoginServer string = acr.properties.loginServer
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output logicAppName string = logicApp.name
output logicAppUrl string = 'https://${logicApp.properties.defaultHostName}'
output searchFunctionAppName string = searchFunctionApp.name
output searchFunctionAppUrl string = 'https://${searchFunctionApp.properties.defaultHostName}'
output easyAuthRedirectUri string = 'https://${containerApp.properties.configuration.ingress.fqdn}/.auth/login/aad/callback'
output logAnalyticsWorkspaceId string = logAnalytics.id
output logAnalyticsWorkspaceName string = logAnalytics.name
output networkSecurityPerimeterName string = nsp.name
