# ---------------------------------------------------------------
# Event Grid: System Topic + Subscription
# Triggers on BlobCreated in the INGEST container.
# ---------------------------------------------------------------

resource "azurerm_eventgrid_system_topic" "storage" {
  name                   = "evgt-${local.name_prefix}-${local.name_suffix}"
  location               = azurerm_resource_group.main.location
  resource_group_name    = azurerm_resource_group.main.name
  source_resource_id    = azurerm_storage_account.main.id
  topic_type             = "Microsoft.Storage.StorageAccounts"
  tags                   = local.common_tags
}

resource "azurerm_eventgrid_system_topic_event_subscription" "blob_created" {
  name                = "sub-blob-created"
  system_topic        = azurerm_eventgrid_system_topic.storage.name
  resource_group_name = azurerm_resource_group.main.name

  webhook_endpoint {
    url                          = "https://${azurerm_container_app.main.ingress[0].fqdn}/api/events/blob"
    max_events_per_batch              = 1
    preferred_batch_size_in_kilobytes = 64
  }

  included_event_types = ["Microsoft.Storage.BlobCreated"]

  subject_filter {
    subject_begins_with = "/blobServices/default/containers/ingest/"
  }

  retry_policy {
    max_delivery_attempts = 10
    event_time_to_live    = 1440
  }
}
