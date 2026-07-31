# Terraform — Infrastructure

Provisions all Azure resources for the document processing pipeline.

## Quick Start

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars

terraform init
terraform plan
terraform apply
```

## What Gets Created

| Resource | Name Pattern | Purpose |
|----------|-------------|---------|
| Resource Group | `rg-{project}-{env}-{suffix}` | Contains everything |
| Virtual Network | `vnet-{project}-{env}-{suffix}` | Network isolation (3 subnets) |
| Storage Account | `st{project}{suffix}` | Blob storage (4 containers) |
| Cosmos DB | `cosmos-{project}-{env}-{suffix}` | Job tracking + results + vector/full-text/hybrid search |
| Azure OpenAI | `oai-{project}-{env}-{suffix}` | GPT-5.1 + text-embedding-3-small |
| Document Intelligence | `di-{project}-{env}-{suffix}` | Document extraction |
| Container Registry | `acr{project}{suffix}` | Docker image hosting |
| Container App Env | `cae-{project}-{env}-{suffix}` | Managed container runtime |
| Container App | `ca-{project}-{env}-{suffix}` | The application |
| Logic App Standard | `logic-{project}-{env}-{suffix}` | Key-protected search facade |
| Event Grid Topic | `evgt-{project}-{env}-{suffix}` | BlobCreated event routing |
| Log Analytics | `law-{project}-{env}-{suffix}` | Logging |
| Application Insights | `appi-{project}-{env}-{suffix}` | APM / monitoring |
| Private DNS Zones | 5 zones | Private endpoint DNS resolution |
| Private Endpoints | 4 endpoints | Storage, Cosmos, OpenAI, Doc Intel |
| Network Security Perimeter | `nsp-{project}-{env}-{suffix}` | Storage network protection |
| Entra ID App Registration | — | Easy Auth for Container App |

## Variables

All variables have defaults. At minimum, review these in `terraform.tfvars`:

| Variable | Default | Description |
|----------|---------|-------------|
| `location` | `eastus2` | Azure region |
| `project_name` | `docpipeline` | Naming prefix |
| `environment` | `dev` | Environment suffix |
| `tags` | `{}` | Tags for all resources |

See [variables.tf](variables.tf) for the full list including VNet CIDRs, model versions, search result limits, search-index backfill batch limits, container sizing, and Cosmos throughput mode.

## Post-Deployment

### Update IP allowlists

Set `allowed_ip_addresses` for public client/admin IPs that need portal or data-plane access to Storage. These IPs are applied to the Storage firewall, Cosmos DB firewall, and Network Security Perimeter inbound rules.

Set `cosmos_allowed_ip_addresses` for additional public IPs that only need Cosmos DB data-plane access.

Update `terraform.tfvars`, then run `terraform apply` again.

### Build the container image

```bash
# From the repo root (not the terraform/ directory)
az acr build \
  --registry $(terraform output -raw acr_login_server) \
  --resource-group $(terraform output -raw resource_group_name) \
  --image docpipeline:latest ..
```

### View outputs

```bash
terraform output
```

Key outputs: `container_app_url`, `logic_app_name`, `acr_login_server`, `resource_group_name`, `cosmos_endpoint`, `openai_endpoint`, `storage_blob_endpoint`.

### Deploy the Logic App workflow code

Terraform creates the Logic App Standard shell. Deploy the workflow source from the repository root:

```powershell
.\scripts\Deploy-LogicAppWorkflow.ps1 `
  -ResourceGroupName (terraform output -raw resource_group_name) `
  -LogicAppName (terraform output -raw logic_app_name)
```

## File Reference

| File | Manages |
|------|---------|
| `main.tf` | Resource group, random suffix, naming locals |
| `providers.tf` | Provider versions (azurerm ~>4.0, azapi ~>2.0, azuread ~>3.0) |
| `variables.tf` | All input variables |
| `outputs.tf` | Useful output values |
| `network.tf` | VNet, subnets, NSGs |
| `storage.tf` | Storage account + 4 blob containers |
| `cosmos.tf` | Cosmos DB account, database, containers, vector policies |
| `ai_services.tf` | Azure OpenAI + Document Intelligence + model deployments |
| `acr.tf` | Container Registry |
| `container_app.tf` | Container App Environment + Container App |
| `logic_app.tf` | Logic App Standard plan, app, and runtime storage |
| `identity.tf` | RBAC role assignments (MI → services) |
| `auth.tf` | Entra ID app registration + Easy Auth config |
| `event_grid.tf` | Event Grid system topic + BlobCreated subscription |
| `private_endpoints.tf` | Private DNS zones + VNet links + private endpoints |
| `nsp.tf` | Network Security Perimeter for storage |
| `monitoring.tf` | Log Analytics, App Insights, diagnostic settings |

## Notes

- The Cosmos DB vector search capability (`EnableNoSQLVectorSearch`) is added via `azapi_update_resource` to avoid a destructive account replacement that `azurerm` would trigger.
- All AI services have `public_network_access_enabled = false` and are accessed via private endpoints.
- The Container App is the only resource with public ingress (port 8000, HTTPS).
