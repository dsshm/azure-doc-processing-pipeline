# ---------------------------------------------------------------
# Logic App Standard search facade
# ---------------------------------------------------------------

resource "azurerm_storage_account" "logic_app" {
  name                            = substr("stlogic${replace(var.project_name, "-", "")}${local.name_suffix}", 0, 24)
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  shared_access_key_enabled       = true
  allow_nested_items_to_be_public = false
  default_to_oauth_authentication = false
  min_tls_version                 = "TLS1_2"
  tags                            = local.common_tags
}

resource "azurerm_service_plan" "logic_app" {
  name                = "plan-logic-${local.name_prefix}-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Windows"
  sku_name            = var.logic_app_sku_name
  tags                = local.common_tags
}

resource "azurerm_logic_app_standard" "search" {
  name                       = "logic-${local.name_prefix}-${local.name_suffix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  app_service_plan_id        = azurerm_service_plan.logic_app.id
  storage_account_name       = azurerm_storage_account.logic_app.name
  storage_account_access_key = azurerm_storage_account.logic_app.primary_access_key
  version                    = "~4"
  https_only                 = true
  virtual_network_subnet_id  = azurerm_subnet.logic_app_integration.id
  tags                       = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME                         = "dotnet"
    APP_KIND                                         = "workflowApp"
    WEBSITE_VNET_ROUTE_ALL                           = "1"
    AzureFunctionsJobHost__extensionBundle__id      = "Microsoft.Azure.Functions.ExtensionBundle.Workflows"
    AzureFunctionsJobHost__extensionBundle__version = "[1.*, 2.0.0)"
    CONTAINER_APP_BASE_URL                           = "https://${azurerm_container_app.main.ingress[0].fqdn}"
    AZURE_OPENAI_ENDPOINT                            = azurerm_cognitive_account.openai.endpoint
    AZURE_OPENAI_EMBEDDING_MODEL                     = var.embedding_model_name
    AZURE_OPENAI_EMBEDDING_API_VERSION               = var.openai_embedding_api_version
    SEARCH_DEFAULT_TOP                               = tostring(var.search_default_top)
    SEARCH_MAX_TOP                                   = tostring(var.search_max_top)
    SEARCH_DEFAULT_VECTOR_FIELD                      = "summary_vector"
    "Workflows.SearchDocuments.OperationOptions"     = "WithStatelessRunHistory"
  }
}
