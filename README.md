# IBWC Document Intelligence Azure Function

This repository contains an Azure Functions Python project that provides document and vision analysis, OpenAI integration, and storage helpers for processing case files and producing structured analysis.

## What this function does
- Uses Azure OpenAI (via the Azure OpenAI or Cognitive Services endpoint) to run LLM-driven analysis.
- Uses Azure AI Vision and Document Intelligence for image and document extraction and analysis.
- Reads/writes case artifacts using Azure Blob Storage / ADLS and stores structured results in Cosmos DB (services are wrapped in the `services/` package).

## Prerequisites (Deployment)
These prerequisites are for deploying and running this project in Azure. Local development prerequisites are listed under the "Local development" section.

- Azure resources (minimum)
  - Resource Group
  - Storage Account (used by the Function App)
  - Function App (Linux/Windows, Functions v4, Python runtime)
  - Document Intelligence (Cognitive Services resource or Form Recognizer-like resource)
  - (Optional) Key Vault for secrets, and Cosmos DB / Blob Storage if you intend to enable services in `services/`

- Identity & permissions (deployment)
  - If using Managed Identity (recommended): enable a system-assigned or user-assigned managed identity on the Function App and grant it the appropriate RBAC roles (Storage Blob Data Reader / Contributor; necessary roles on Cognitive Services or access via Key Vault).
  - If using a service principal for automation (CI/CD): create an Azure AD app, note AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET, and grant RBAC roles to the principal.

## Required environment variables
The function reads configuration from environment variables. For local development these are stored in `local.settings.json` (do NOT commit this file). This project uses Document Intelligence via `bp_docIntel.py` and supports Managed Identity or service-principal based authentication. The environment variables referenced by the code are summarized below:

| Variable | Required | Description | Example |
|---|---:|---|---|
| AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT | Yes | Document Intelligence (Form Recognizer / Document Intelligence) endpoint URL for your resource | https://my-docintel-resource.cognitiveservices.azure.com/ |
| AZURE_DOCUMENT_INTELLIGENCE_KEY | Yes | API key for Document Intelligence. This project is currently configured to use key-based authentication for Document Intelligence. | <document-intelligence-key> |
| AZURE_TENANT_ID | Optional (local/CI) | Azure AD tenant ID used for service principal authentication. Not required for current key-based setup. | 00000000-0000-0000-0000-000000000000 |
| AZURE_CLIENT_ID | Optional (local/CI) | Azure AD app (service principal) client/app ID. Not required for current key-based setup. | 11111111-1111-1111-1111-111111111111 |
| AZURE_CLIENT_SECRET | Optional (local/CI) | Service principal client secret. Not required for current key-based setup. | <very-secret-value> |ß

Note: Do not commit secrets or `local.settings.json` to source control. Prefer storing keys and secrets in Azure Key Vault and referencing them from Function App configuration (or grant the Function App a Managed Identity and assign appropriate RBAC roles).

## Authentication requirements
This project uses the Azure SDKs which support two main authentication options:

1. Managed Identity (Recommended)
   - Assign a system-assigned or user-assigned Managed Identity to the Function App in Azure.
   - Grant that identity the necessary role permissions on resources (Blob Storage contributor/reader, Cognitive Services or specific resource roles, Cosmos DB permissions, etc.).
   - Locally, you can use the Azure CLI to sign in and the Azure Identity libraries (DefaultAzureCredential) will pick it up for development.

   Benefits:
   - No tenant/client secrets stored in config or source control.
   - Easier to rotate credentials and follow least-privilege principles.

2. Service Principal (Service Principal credentials)
   - Create an Azure AD app and service principal and grant required roles to it.
   - Provide AZURE_TENANT_ID, AZURE_CLIENT_ID and AZURE_CLIENT_SECRET in `local.settings.json` or the Function App settings in Azure.

   Note: Use a service principal only when you can't use Managed Identity (for CI pipelines or automation you may prefer a service principal). Keep secrets in Key Vault or secure pipelines.

Authentication in code:
- The code uses `DefaultAzureCredential` (see `services/blob_service.py` and other modules). This will try multiple credentials including Managed Identity, Azure CLI, and environment variables.

## Deployment
Below are typical deployment steps for this Azure Functions project.

### Deploy using Azure CLI
1. Log in to Azure CLI and select your subscription:

```bash
az login
az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"
```

2. Create a resource group (if needed):

```bash
az group create --name myResourceGroup --location eastus2
```

3. Create a storage account (required for Functions):

```bash
az storage account create --name mystorageacct --location eastus2 --resource-group myResourceGroup --sku Standard_LRS
```

4. Create the Function App with a managed identity (recommended):

```bash
az functionapp create \
  --resource-group myResourceGroup \
  --consumption-plan-location eastus2 \
  --name my-function-app-name \
  --storage-account mystorageacct \
  --runtime python \
  --functions-version 4 \
  --assign-identity
```

This command assigns a system-managed identity to the Function App. To use a user-assigned identity instead, create the identity first and pass `--assign-identity [resource-id]`.

5. Configure application settings (secrets should come from Key Vault ideally):

```bash
az functionapp config appsettings set --name my-function-app-name --resource-group myResourceGroup --settings \
  AZURE_OPENAI_ENDPOINT="https://<your-resource>.cognitiveservices.azure.com/" \
  AZURE_OPENAI_KEY="<key-or-empty-if-using-MSI>" \
  AZURE_AI_VISION_ENDPOINT="https://<your-resource>.cognitiveservices.azure.com/" \
  AZURE_AI_VISION_KEY="<key-or-empty-if-using-MSI>" \
  AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://<your-resource>.cognitiveservices.azure.com/" \
  AZURE_DOCUMENT_INTELLIGENCE_KEY="<key-or-empty-if-using-MSI>"
```

If using Managed Identity, you can leave service keys empty and rely on role assignments. Alternatively, store keys in Azure Key Vault and reference them from app settings.

6. Deploy the code (from repo root) using Azure Functions Core Tools or `az functionapp` deployment methods. Using zip deploy:

```bash
# from repo root
azip="$(pwd)/functionapp.zip"
zip -r "$azip" . -x "*.git*" 
az functionapp deployment source config-zip --resource-group myResourceGroup --name my-function-app-name --src "$azip"
```

Or use `func azure functionapp publish` (Core Tools must be installed):

```bash
func azure functionapp publish my-function-app-name --python
```

### Deploy using Azure Portal
1. Create or navigate to your Function App in the Azure Portal.
2. In "Identity", enable System-assigned managed identity or add a user-assigned identity.
3. In "Configuration", add application settings for the environment variables listed above. For secrets, prefer referencing Key Vault using the `@Microsoft.KeyVault(SecretUri=...)` syntax or use managed identity + Key Vault.
4. Under "Deployment", choose your preferred deployment method (Zip Deploy, GitHub Actions, or Azure DevOps). Upload the zip package or configure the pipeline.
5. Assign RBAC roles for the Function App's managed identity to the resources it needs (Storage Blob Data Reader/Contributor, Cognitive Services roles, Cosmos DB roles, etc.).

## Local development
Local development prerequisites

- Python 3.10+ (matching the Functions worker runtime)
- Azure Functions Core Tools (v4) for local debugging and publishing
- Azure CLI (for auth during local runs)
- A Python virtual environment tool (venv)

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

2. Copy `local.settings.json` (if you don't have one) and add required keys. Do NOT commit `local.settings.json`.
  Alternatively, copy the example file shipped with this repo:

  ```bash
  cp local.settings.example.json local.settings.json
  # Edit local.settings.json and fill in real values. Do NOT commit this file.
  ```
3. Run locally:

```bash
func start
```

The project uses `DefaultAzureCredential`, so for local development either:
- Set AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET in `local.settings.json`, or
- Use `az login` and let DefaultAzureCredential pick up credentials from the Azure CLI, or
- Use developer tooling that supports Managed Identity emulation.

## Notes & next steps
- Rotate any keys found in `local.settings.json` and move secret storage to Key Vault.
- Add CI/CD pipeline (GitHub Actions/Azure DevOps) that uses managed identity or service principal stored in a secrets store.

---

If you'd like, I can also:
- Add a small `docs/DEPLOY.md` with a deployment checklist and sample RBAC assignments.
- Create a GitHub Actions workflow that demonstrates secure deployment using a service principal or GitHub environment secrets.


