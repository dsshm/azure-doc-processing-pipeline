# ---------------------------------------------------------------
# Container App Environment + Container App
# ---------------------------------------------------------------

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name_prefix}-${local.name_suffix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id   = azurerm_subnet.container_apps.id
  tags                       = local.common_tags

  lifecycle {
    ignore_changes = [infrastructure_resource_group_name]
  }
}

resource "azurerm_container_app" "main" {
  name                         = "ca-${local.name_prefix}-${local.name_suffix}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  depends_on = [azurerm_role_assignment.acr_pull]

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.acr_pull.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.acr_pull.id
  }

  secret {
    name  = "microsoft-provider-authentication-secret"
    value = azuread_application_password.container_app.value
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.container_min_replicas
    max_replicas = var.container_max_replicas

    container {
      name   = "docpipeline"
      image  = "${azurerm_container_registry.main.login_server}/docpipeline:latest"
      cpu    = var.container_cpu
      memory = var.container_memory

      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = azurerm_storage_account.main.primary_blob_endpoint
      }
      env {
        name  = "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"
        value = azurerm_cognitive_account.docintel.endpoint
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }
      env {
        name  = "AZURE_OPENAI_API_VERSION"
        value = "2024-12-01-preview"
      }
      env {
        name  = "AZURE_OPENAI_MODEL_NAME"
        value = var.openai_model_name
      }
      env {
        name  = "AZURE_OPENAI_EMBEDDING_MODEL"
        value = var.embedding_model_name
      }
      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.main.endpoint
      }
      env {
        name  = "COSMOS_DATABASE_NAME"
        value = azurerm_cosmosdb_sql_database.main.name
      }
      env {
        name  = "STORAGE_CONTAINER_INGEST"
        value = "ingest"
      }
      env {
        name  = "STORAGE_CONTAINER_PROCESSING"
        value = "processing"
      }
      env {
        name  = "STORAGE_CONTAINER_COMPLETED"
        value = "completed"
      }
      env {
        name  = "STORAGE_CONTAINER_ORIGINAL"
        value = "originaldocument"
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
    }
  }
}
