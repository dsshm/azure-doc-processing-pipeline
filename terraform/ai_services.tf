# ---------------------------------------------------------------
# Azure OpenAI  +  Azure Document Intelligence
# ---------------------------------------------------------------

# --- Azure OpenAI ---
resource "azurerm_cognitive_account" "openai" {
  name                          = "oai-${local.name_prefix}-${local.name_suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  local_auth_enabled            = false
  custom_subdomain_name         = "oai-${local.name_prefix}-${local.name_suffix}"
  public_network_access_enabled = false
  tags                          = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = var.openai_model_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  sku {
    name     = var.openai_model_sku_name
    capacity = var.openai_model_capacity
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = var.embedding_model_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.embedding_model_name
    version = var.embedding_model_version
  }

  sku {
    name     = var.embedding_model_sku_name
    capacity = var.embedding_model_capacity
  }
}

# --- Azure Document Intelligence ---
resource "azurerm_cognitive_account" "docintel" {
  name                          = "di-${local.name_prefix}-${local.name_suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  kind                          = "FormRecognizer"
  sku_name                      = "S0"
  local_auth_enabled            = false
  custom_subdomain_name         = "di-${local.name_prefix}-${local.name_suffix}"
  public_network_access_enabled = false
  tags                          = local.common_tags
}
