output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "storage_account_name" {
  value = azurerm_storage_account.main.name
}

output "storage_blob_endpoint" {
  value = azurerm_storage_account.main.primary_blob_endpoint
}

output "cosmos_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "openai_endpoint" {
  value = azurerm_cognitive_account.openai.endpoint
}

output "docintel_endpoint" {
  value = azurerm_cognitive_account.docintel.endpoint
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "container_app_fqdn" {
  value = var.deploy_container_app ? azurerm_container_app.main[0].ingress[0].fqdn : null
}

output "container_app_url" {
  value = var.deploy_container_app ? "https://${azurerm_container_app.main[0].ingress[0].fqdn}" : null
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}

output "app_insights_connection_string" {
  value     = azurerm_application_insights.main.connection_string
  sensitive = true
}
