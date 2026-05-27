# ---------------------------------------------------------------
# Azure Container Registry (Basic SKU, admin disabled)
# ---------------------------------------------------------------

resource "azurerm_container_registry" "main" {
  name                = "acr${var.project_name}${local.name_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.common_tags
}
