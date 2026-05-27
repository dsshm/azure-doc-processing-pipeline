# ---------------------------------------------------------------
# Entra ID Authentication (Easy Auth) for Container App
# Any user in the tenant can authenticate.
# ---------------------------------------------------------------

data "azuread_client_config" "current" {}

# App registration created WITHOUT redirect URIs to avoid cycle
# (CA needs app secret -> app needs CA FQDN for redirect URI)
resource "azuread_application" "container_app" {
  display_name = "ca-${local.name_prefix}-${local.name_suffix}"

  sign_in_audience = "AzureADMyOrg"

  web {
    implicit_grant {
      id_token_issuance_enabled = true
    }
  }

  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph

    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d" # User.Read
      type = "Scope"
    }
  }
}

# Redirect URI added separately — depends on CA FQDN, breaks the cycle
resource "azuread_application_redirect_uris" "container_app" {
  application_id = azuread_application.container_app.id
  type           = "Web"

  redirect_uris = [
    "https://${azurerm_container_app.main.ingress[0].fqdn}/.auth/login/aad/callback"
  ]
}

resource "azuread_service_principal" "container_app" {
  client_id = azuread_application.container_app.client_id
}

resource "azuread_application_password" "container_app" {
  application_id = azuread_application.container_app.id
  display_name   = "container-app-auth"
  end_date       = "2027-04-20T00:00:00Z"
}

resource "azapi_resource" "container_app_auth" {
  type      = "Microsoft.App/containerApps/authConfigs@2024-03-01"
  name      = "current"
  parent_id = azurerm_container_app.main.id

  body = {
    properties = {
      platform = {
        enabled = true
      }
      globalValidation = {
        unauthenticatedClientAction = "RedirectToLoginPage"
        redirectToProvider           = "azureactivedirectory"
        excludedPaths                = ["/api/events/*", "/health"]
      }
      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId                = azuread_application.container_app.client_id
            clientSecretSettingName = "microsoft-provider-authentication-secret"
            openIdIssuer            = "https://sts.windows.net/${data.azuread_client_config.current.tenant_id}/v2.0"
          }
          validation = {
            allowedAudiences = [
              "api://${azuread_application.container_app.client_id}"
            ]
          }
        }
      }
      login = {
        tokenStore = {
          enabled = false
        }
      }
    }
  }

  depends_on = [azurerm_container_app.main]
}
