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
| Cosmos DB | `cosmos-{project}-{env}-{suffix}` | Job tracking + results + vector search |
| Azure OpenAI | `oai-{project}-{env}-{suffix}` | GPT-4o + text-embedding-ada-002 |
| Document Intelligence | `di-{project}-{env}-{suffix}` | Document extraction |
| Container Registry | `acr{project}{suffix}` | Docker image hosting |
| Container App Env | `cae-{project}-{env}-{suffix}` | Managed container runtime |
| Container App | `ca-{project}-{env}-{suffix}` | The application |
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

See [variables.tf](variables.tf) for the full list including VNet CIDRs, model versions, container sizing, and Cosmos throughput mode.

## Post-Deployment

### Update IP allowlists

Two files contain a hardcoded IP address (`71.200.56.126`) that must be updated:

1. **`cosmos.tf` line ~13** — `ip_range_filter` on the Cosmos DB account
2. **`nsp.tf` line ~30** — `addressPrefixes` in the NSP inbound access rule

Replace with your public IP, then run `terraform apply` again.

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

Key outputs: `container_app_url`, `acr_login_server`, `resource_group_name`, `cosmos_endpoint`, `openai_endpoint`, `storage_blob_endpoint`.

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
