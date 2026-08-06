# ---------------------------------------------------------------
# Storage Account + Blob Containers
# ---------------------------------------------------------------

resource "azurerm_storage_account" "main" {
  name                          = "st${var.project_name}${local.name_suffix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  account_kind                  = "StorageV2"
  shared_access_key_enabled        = false
  allow_nested_items_to_be_public  = false
  default_to_oauth_authentication = true
  tags                            = local.common_tags

  network_rules {
    default_action             = "Deny"
    bypass                     = ["AzureServices"]
    ip_rules                   = var.allowed_ip_addresses
    virtual_network_subnet_ids = [azurerm_subnet.container_apps.id]
  }

  blob_properties {
    versioning_enabled = true

    cors_rule {
      allowed_headers    = ["*"]
      allowed_methods    = ["GET", "HEAD", "PUT", "DELETE", "OPTIONS"]
      allowed_origins    = ["https://portal.azure.com", "https://ms.portal.azure.com"]
      exposed_headers    = ["*"]
      max_age_in_seconds = 3600
    }
  }
}

resource "azurerm_storage_container" "ingest" {
  name                 = "ingest"
  storage_account_id   = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "processing" {
  name                 = "processing"
  storage_account_id   = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "completed" {
  name                 = "completed"
  storage_account_id   = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "originaldocument" {
  name                 = "originaldocument"
  storage_account_id   = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "failed" {
  name                 = "failed"
  storage_account_id   = azurerm_storage_account.main.id
  container_access_type = "private"
}
