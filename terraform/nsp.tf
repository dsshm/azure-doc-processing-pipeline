# ---------------------------------------------------------------
# Network Security Perimeter — Storage Account
# ---------------------------------------------------------------

resource "azapi_resource" "nsp" {
  type      = "Microsoft.Network/networkSecurityPerimeters@2023-08-01-preview"
  name      = "nsp-${local.name_prefix}-${local.name_suffix}"
  parent_id = azurerm_resource_group.main.id
  location  = azurerm_resource_group.main.location
  tags      = local.common_tags

  body = {}
}

resource "azapi_resource" "nsp_profile" {
  type      = "Microsoft.Network/networkSecurityPerimeters/profiles@2023-08-01-preview"
  name      = "profile-acr"
  parent_id = azapi_resource.nsp.id
  location  = azurerm_resource_group.main.location

  body = {}
}

# Allow inbound from home IP
resource "azapi_resource" "nsp_rule_home" {
  type      = "Microsoft.Network/networkSecurityPerimeters/profiles/accessRules@2023-08-01-preview"
  name      = "home"
  parent_id = azapi_resource.nsp_profile.id

  body = {
    properties = {
      direction       = "Inbound"
      addressPrefixes = ["71.200.56.126/32"]
    }
  }
}

# Allow inbound from resources in the same subscription
resource "azapi_resource" "nsp_rule_subscriptions" {
  type      = "Microsoft.Network/networkSecurityPerimeters/profiles/accessRules@2023-08-01-preview"
  name      = "internal_subscriptions"
  parent_id = azapi_resource.nsp_profile.id

  body = {
    properties = {
      direction = "Inbound"
      subscriptions = [
        { id = "/subscriptions/${data.azurerm_subscription.current.subscription_id}" },
        { id = "/subscriptions/4345216c-3da4-4537-97ff-2a9f5053a420" }
      ]
    }
  }
}

# Associate storage account with NSP in Enforced mode
resource "azapi_resource" "nsp_association_storage" {
  type      = "Microsoft.Network/networkSecurityPerimeters/resourceAssociations@2023-08-01-preview"
  name      = "assoc-storage"
  parent_id = azapi_resource.nsp.id
  location  = azurerm_resource_group.main.location

  body = {
    properties = {
      accessMode = "Enforced"
      privateLinkResource = {
        id = azurerm_storage_account.main.id
      }
      profile = {
        id = azapi_resource.nsp_profile.id
      }
    }
  }
}

data "azurerm_subscription" "current" {}
