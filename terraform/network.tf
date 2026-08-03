# ---------------------------------------------------------------
# VNet, Subnets, NSGs
# ---------------------------------------------------------------

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.name_prefix}-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = var.vnet_address_space
  tags                = local.common_tags
}

# --- Container Apps subnet ---
resource "azurerm_subnet" "container_apps" {
  name                            = "snet-container-apps"
  resource_group_name             = azurerm_resource_group.main.name
  virtual_network_name            = azurerm_virtual_network.main.name
  address_prefixes                = [var.container_app_subnet_cidr]
  default_outbound_access_enabled = false

  service_endpoints = ["Microsoft.Storage"]

  delegation {
    name = "container-app-delegation"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# --- Private endpoints subnet ---
resource "azurerm_subnet" "private_endpoints" {
  name                            = "snet-private-endpoints"
  resource_group_name             = azurerm_resource_group.main.name
  virtual_network_name            = azurerm_virtual_network.main.name
  address_prefixes                = [var.private_endpoints_subnet_cidr]
  default_outbound_access_enabled = false
}

# --- AI Services subnet ---
resource "azurerm_subnet" "ai_services" {
  name                            = "snet-ai-services"
  resource_group_name             = azurerm_resource_group.main.name
  virtual_network_name            = azurerm_virtual_network.main.name
  address_prefixes                = [var.ai_services_subnet_cidr]
  default_outbound_access_enabled = false
}

# --- Logic App Standard regional VNet integration subnet ---
resource "azurerm_subnet" "logic_app_integration" {
  name                            = "snet-logic-app-integration"
  resource_group_name             = azurerm_resource_group.main.name
  virtual_network_name            = azurerm_virtual_network.main.name
  address_prefixes                = [var.logic_app_integration_subnet_cidr]
  default_outbound_access_enabled = false

  delegation {
    name = "logic-app-integration-delegation"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

# --- NSGs ---
resource "azurerm_network_security_group" "container_apps" {
  name                = "nsg-container-apps-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_subnet_network_security_group_association" "container_apps" {
  subnet_id                 = azurerm_subnet.container_apps.id
  network_security_group_id = azurerm_network_security_group.container_apps.id
}

resource "azurerm_network_security_group" "private_endpoints" {
  name                = "nsg-private-endpoints-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_subnet_network_security_group_association" "private_endpoints" {
  subnet_id                 = azurerm_subnet.private_endpoints.id
  network_security_group_id = azurerm_network_security_group.private_endpoints.id
}

resource "azurerm_network_security_group" "ai_services" {
  name                = "nsg-ai-services-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_subnet_network_security_group_association" "ai_services" {
  subnet_id                 = azurerm_subnet.ai_services.id
  network_security_group_id = azurerm_network_security_group.ai_services.id
}

resource "azurerm_network_security_group" "logic_app_integration" {
  name                = "nsg-logic-app-integration-${local.name_suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_subnet_network_security_group_association" "logic_app_integration" {
  subnet_id                 = azurerm_subnet.logic_app_integration.id
  network_security_group_id = azurerm_network_security_group.logic_app_integration.id
}
