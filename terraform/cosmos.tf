# ---------------------------------------------------------------
# Azure Cosmos DB (NoSQL API, Serverless, local auth disabled)
# ---------------------------------------------------------------

resource "azurerm_cosmosdb_account" "main" {
  name                          = "cosmos-${local.name_prefix}-${local.name_suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  local_authentication_disabled    = true
  public_network_access_enabled = true
  ip_range_filter               = ["71.200.56.126"]
  tags                          = local.common_tags

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  capabilities {
    name = "EnableServerless"
  }
}

# Enable vector search capability via azapi to avoid account replacement.
# azurerm marks capabilities as ForceNew, but the API supports adding them in-place.
resource "azapi_update_resource" "cosmos_vector_search_capability" {
  type      = "Microsoft.DocumentDB/databaseAccounts@2024-05-15"
  name      = azurerm_cosmosdb_account.main.name
  parent_id = azurerm_resource_group.main.id

  body = {
    properties = {
      capabilities = [
        { name = "EnableServerless" },
        { name = "EnableNoSQLVectorSearch" }
      ]
    }
  }
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "docprocessing"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "jobs" {
  name                = "jobs"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/id"]
}

resource "azurerm_cosmosdb_sql_container" "results" {
  name                = "results"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/jobId"]
}

# ---------------------------------------------------------------
# Vector search policies for the results container.
# azurerm doesn't support vector embedding policy / vector indexes,
# so we overlay via azapi_update_resource.
# ---------------------------------------------------------------

resource "azapi_update_resource" "results_vector_policy" {
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15"
  name      = azurerm_cosmosdb_sql_container.results.name
  parent_id = "${azurerm_cosmosdb_account.main.id}/sqlDatabases/${azurerm_cosmosdb_sql_database.main.name}"

  body = {
    properties = {
      resource = {
        vectorEmbeddingPolicy = {
          vectorEmbeddings = [
            {
              path          = "/summary_vector"
              dataType      = "float32"
              distanceFunction = "cosine"
              dimensions    = 1536
            },
            {
              path          = "/purpose_vector"
              dataType      = "float32"
              distanceFunction = "cosine"
              dimensions    = 1536
            },
            {
              path          = "/chunks/vector"
              dataType      = "float32"
              distanceFunction = "cosine"
              dimensions    = 1536
            }
          ]
        }
        indexingPolicy = {
          indexingMode = "consistent"
          automatic    = true
          includedPaths = [{ path = "/*" }]
          excludedPaths = [
            { path = "/summary_vector/*" },
            { path = "/purpose_vector/*" },
            { path = "/chunks/vector/*" },
            { path = "/_etag/?" }
          ]
          vectorIndexes = [
            {
              path = "/summary_vector"
              type = "quantizedFlat"
            },
            {
              path = "/purpose_vector"
              type = "quantizedFlat"
            },
            {
              path = "/chunks/vector"
              type = "quantizedFlat"
            }
          ]
        }
      }
    }
  }

  depends_on = [
    azurerm_cosmosdb_sql_container.results,
    azapi_update_resource.cosmos_vector_search_capability,
  ]
}
