# ---------------------------------------------------------------
# Azure Functions search facade for Power Platform
# ---------------------------------------------------------------

resource "azurerm_storage_account" "search_function" {
  name                            = substr("stfunc${replace(var.project_name, "-", "")}${local.name_suffix}", 0, 24)
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

resource "azurerm_service_plan" "search_function" {
  name                = "plan-func-${local.name_prefix}-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = var.search_function_sku_name
  tags                = local.common_tags
}

resource "azurerm_linux_function_app" "search" {
  name                       = "func-${local.name_prefix}-${local.name_suffix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.search_function.id
  storage_account_name       = azurerm_storage_account.search_function.name
  storage_account_access_key = azurerm_storage_account.search_function.primary_access_key
  https_only                 = true
  virtual_network_subnet_id  = azurerm_subnet.logic_app_integration.id
  tags                       = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on              = true
    ftps_state             = "Disabled"
    minimum_tls_version    = "1.2"
    vnet_route_all_enabled = true

    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    FUNCTIONS_EXTENSION_VERSION           = "~4"
    FUNCTIONS_WORKER_RUNTIME              = "python"
    AzureWebJobsFeatureFlags              = "EnableWorkerIndexing"
    SCM_DO_BUILD_DURING_DEPLOYMENT        = "true"
    ENABLE_ORYX_BUILD                     = "true"
    WEBSITE_VNET_ROUTE_ALL                = "1"
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
    CONTAINER_APP_BASE_URL                = "https://${azurerm_container_app.main.ingress[0].fqdn}"
    AZURE_OPENAI_ENDPOINT                 = azurerm_cognitive_account.openai.endpoint
    AZURE_OPENAI_EMBEDDING_MODEL          = var.embedding_model_name
    AZURE_OPENAI_EMBEDDING_API_VERSION    = var.openai_embedding_api_version
    SEARCH_DEFAULT_TOP                    = tostring(var.search_default_top)
    SEARCH_MAX_TOP                        = tostring(var.search_max_top)
    SEARCH_DEFAULT_VECTOR_FIELD           = "summary_vector"
    REQUEST_TIMEOUT_SECONDS               = "30"
  }
}
