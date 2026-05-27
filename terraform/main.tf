resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

locals {
  name_suffix = random_string.suffix.result
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = merge(var.tags, {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  })
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}-${local.name_suffix}"
  location = var.location
  tags     = local.common_tags
}
