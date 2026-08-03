# ---------------------------------------------------------------
# Managed Identity Role Assignments
#
# User-assigned identity for ACR pull (must exist before Container App).
# Container App system-assigned identity → all downstream services.
# No API keys, no connection strings, no SAS (except user delegation).
# ---------------------------------------------------------------

# --- User-assigned identity for ACR pull ---
resource "azurerm_user_assigned_identity" "acr_pull" {
  name                = "id-acr-pull-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

# --- ACR: AcrPull via user-assigned identity (created before CA) ---
resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.acr_pull.principal_id
}

# --- Storage: Blob Data Contributor (read/write/delete blobs) ---
resource "azurerm_role_assignment" "ca_storage_contributor" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_container_app.main.identity[0].principal_id
}

# --- Storage: Blob Delegator (generate user delegation SAS) ---
resource "azurerm_role_assignment" "ca_storage_delegator" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Delegator"
  principal_id         = azurerm_container_app.main.identity[0].principal_id
}

# --- Cosmos DB: Built-in Data Contributor (read/write data) ---
resource "azurerm_cosmosdb_sql_role_assignment" "ca_cosmos_contributor" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  # Built-in "Cosmos DB Built-in Data Contributor" role definition ID
  role_definition_id = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id       = azurerm_container_app.main.identity[0].principal_id
  scope              = azurerm_cosmosdb_account.main.id
}

# --- Cosmos DB: Built-in Data Reader for deploying user ---
data "azurerm_client_config" "current" {}

resource "azurerm_cosmosdb_sql_role_assignment" "deployer_cosmos_reader" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  # Built-in "Cosmos DB Built-in Data Reader" role definition ID
  role_definition_id = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000001"
  principal_id       = data.azurerm_client_config.current.object_id
  scope              = azurerm_cosmosdb_account.main.id
}

# --- Cosmos DB: Account Reader (control-plane metadata) for deploying user ---
resource "azurerm_role_assignment" "deployer_cosmos_account_reader" {
  scope                = azurerm_cosmosdb_account.main.id
  role_definition_name = "Cosmos DB Account Reader Role"
  principal_id         = data.azurerm_client_config.current.object_id
}

# --- Azure OpenAI: Cognitive Services OpenAI User ---
resource "azurerm_role_assignment" "ca_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_container_app.main.identity[0].principal_id
}

# --- Azure OpenAI: Logic App query vectorization ---
resource "azurerm_role_assignment" "logic_app_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_logic_app_standard.search.identity[0].principal_id
}

# --- Document Intelligence: Cognitive Services User ---
resource "azurerm_role_assignment" "ca_docintel_user" {
  scope                = azurerm_cognitive_account.docintel.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_container_app.main.identity[0].principal_id
}
