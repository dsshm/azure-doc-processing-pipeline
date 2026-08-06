targetScope = 'resourceGroup'

@description('Deploy or update the Storage BlobCreated Event Grid subscription.')
param manageEventGridSubscription bool

@description('Azure region for Event Grid resources.')
param location string

@description('Event Grid system topic name.')
param systemTopicName string

@description('Storage account resource ID used as the Event Grid source.')
param storageAccountId string

@description('Event subscription name.')
param eventSubscriptionName string

@description('HTTPS webhook endpoint that receives BlobCreated events.')
param webhookEndpointUrl string

@description('Tags applied to Event Grid resources.')
param tags object

resource eventGridSystemTopic 'Microsoft.EventGrid/systemTopics@2025-04-01-preview' = if (manageEventGridSubscription) {
  name: systemTopicName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    source: storageAccountId
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

resource blobCreatedSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2025-04-01-preview' = if (manageEventGridSubscription) {
  parent: eventGridSystemTopic
  name: eventSubscriptionName
  properties: {
    destination: {
      endpointType: 'WebHook'
      properties: {
        endpointUrl: webhookEndpointUrl
        maxEventsPerBatch: 1
        preferredBatchSizeInKilobytes: 64
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
      ]
      subjectBeginsWith: '/blobServices/default/containers/ingest/'
    }
    retryPolicy: {
      eventTimeToLiveInMinutes: 1440
      maxDeliveryAttempts: 10
    }
  }
}
