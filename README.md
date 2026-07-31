# Document Processing Pipeline

An event-driven document processing pipeline running as a **FastAPI Container App** on Azure. The system automates the ingestion, extraction, analysis, and indexing of documents — turning unstructured files into structured, searchable data with no manual intervention.

### How it works

1. A user uploads a document (PDF, Word, image, etc.) to the **Azure Blob Storage** `ingest` container.
2. **Azure Event Grid** detects the `BlobCreated` event and sends a webhook to the Container App.
3. The app queues a processing job and a background worker runs a 7-step pipeline:
   - **Move** the blob from `ingest` → `processing` (prevents duplicate triggers).
   - **Extract** text, tables, barcodes, and layout using **Azure Document Intelligence** (prebuilt-layout model).
   - **Analyze** the extracted content with **Azure OpenAI GPT-5.1** — entity extraction, category classification, keyword tagging, and hierarchical summarization (page-level → section → document).
   - **Geocode extracted locations** using **Azure Maps Fuzzy Search** and attach latitude/longitude results to `key_fields.entities.geocoded_locations`.
   - **Build search content and vector embeddings** using **Azure OpenAI text-embedding-3-small** (1536-dimensional). The result-level search text includes extracted entities, addresses, and geocoded coordinates so Cosmos DB full-text and hybrid search can find addresses, buildings, cities, and related document context.
   - **Store** structured results and embeddings in **Azure Cosmos DB** (NoSQL, serverless) with vector indexes for semantic search.
4. The original document is archived to the `originaldocument` container.
5. Users can monitor jobs on the **status dashboard**, search documents via the Container App API or **Logic App Standard** facade, and download original files via SAS-protected URLs.

### Azure services used

| Service | Role |
|---------|------|
| **Azure Container Apps** | Hosts the FastAPI application (Uvicorn, 2 workers, VNet-integrated) |
| **Azure Blob Storage** | Document lifecycle — `ingest`, `processing`, `completed`, `originaldocument` containers |
| **Azure Event Grid** | Triggers processing on blob upload (`BlobCreated` system topic) |
| **Azure Document Intelligence** | OCR / layout extraction from 13+ file types |
| **Azure OpenAI Service** | GPT-5.1 for analysis; text-embedding-3-small for vector embeddings |
| **Azure Maps** | Fuzzy-search geocoding for extracted location entities |
| **Azure Cosmos DB** (NoSQL, Serverless) | Job tracking, analysis results, vector search via `VectorDistance()`, and full-text/hybrid search |
| **Azure Logic Apps Standard** | Key-protected HTTP facade for Power Platform or simple search clients |
| **Azure Container Registry** | Stores the Docker image; pulled by Container Apps via managed identity |
| **Microsoft Entra ID** | Easy Auth on the Container App; RBAC for service-to-service auth |

## Features

- **Automated ingestion** — drop a file in the `ingest` container, processing starts automatically via Event Grid
- **Document Intelligence extraction** — text, tables, barcodes, layout from PDFs, images, Office docs (13+ file types)
- **LLM analysis** — per-page entity/category/keyword extraction, hierarchical summarization for large documents
- **Search text + vector embeddings** — result-level `search_text`, summary/search-text vector, purpose vector, and chunk-level vectors (text-embedding-3-small, 1536 dimensions)
- **Location geocoding** — extracted `locations` entities are enriched with Azure Maps latitude/longitude pins
- **Cosmos DB full-text, vector, and hybrid search** — BM25 full-text ranking and RRF hybrid ranking with `VectorDistance()`
- **Status dashboard** — real-time job monitoring, retry failed jobs, delete jobs
- **Managed identity first** — service-to-service access uses RBAC; the Logic App HTTP trigger is invoked with a key-protected callback URL for simple clients
- **Entra ID Easy Auth** — all endpoints (except webhooks and health) require AAD login

## Supported File Types

The pipeline accepts any file type supported by the Azure Document Intelligence prebuilt-layout model. Text is extracted along with layout structure, tables, and barcodes where applicable.

| Format | Extensions | Notes |
|--------|------------|-------|
| PDF | `.pdf` | Native text and scanned (OCR) |
| Microsoft Word | `.docx`, `.doc` | Text and embedded tables |
| Microsoft Excel | `.xlsx` | Tabular data extraction |
| Microsoft PowerPoint | `.pptx` | Slide text and tables |
| Plain Text | `.txt` | Direct text ingestion |
| Images | `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.tif`, `.gif` | OCR-based text extraction |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard (redirect to status UI) |
| `GET` | `/health` | Health check |
| `POST` | `/api/events/blob` | Event Grid webhook (BlobCreated) |
| `GET` | `/api/status` | List jobs (`?status=queued\|processing\|completed\|failed`, `?limit=`) |
| `GET` | `/api/status/{job_id}` | Job detail with processing steps |
| `POST` | `/api/status/{job_id}/retry` | Re-queue a failed job |
| `DELETE` | `/api/status/{job_id}` | Delete job and its results |
| `GET` | `/api/documents` | List completed analysis results |
| `GET` | `/api/documents/{job_id}` | Get full analysis result |
| `GET` | `/api/documents/{job_id}/original` | Download original document (SAS URL redirect) |
| `POST` | `/api/search` | Vector similarity search (`{query, vector_field, top, filter}`) |
| `POST` | `/api/search/full-text` | Cosmos DB full-text search over `search_text` (`{query, top}`) |
| `POST` | `/api/search/hybrid` | Cosmos DB hybrid search with vector + full-text RRF ranking; results must also match full text (`{query, vector_field, top}`) |
| `POST` | `/api/search/chunks` | Chunk-level vector search (`{query, top}`) |
| `POST` | `/api/admin/search-index/backfill` | Dry-run or execute a bounded batch backfill for existing Cosmos results (`{dry_run, limit, force, include_geocoding, include_chunks}`) |
| `POST` | `/api/admin/search-index/backfill/{job_id}` | Dry-run or execute backfill for one result document |

All endpoints except `/api/events/*` and `/health` are protected by Entra ID Easy Auth.

Search endpoints default `top` to `SEARCH_DEFAULT_TOP` (`30`) when omitted. Clients can pass `top` through in the request body up to `SEARCH_MAX_TOP` (`1000` by default); requests over the cap are rejected with HTTP 400.

## Prerequisites

- **Azure subscription** with permissions to create resources
- **Azure CLI** (`az`) — [install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Terraform** >= 1.5 — [install](https://developer.hashicorp.com/terraform/install) if using the existing Terraform deployment
- **Docker** (for local development) — [install](https://docs.docker.com/get-docker/)
- **Python** 3.11+ (for local development without Docker)

> **💡 Tip — Azure Cloud Shell**: If you don't want to install the Azure CLI or Terraform locally, you can run the infrastructure deployment entirely from [Azure Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/overview) (Bash). It comes with `az`, `terraform`, and `git` pre-installed. Clone this repo in Cloud Shell, then follow the Terraform steps below. Docker and Python are only needed for local development and are **not** required for deploying infrastructure.

## Deployment

### 1. Provision infrastructure

#### Option A: Bicep deployment (includes Azure Maps)

The `bicep/` folder mirrors the existing Terraform topology and adds Azure Maps. It creates or targets a resource group from a subscription-scope deployment.

```bash
az account set --subscription <subscription_id>
az deployment sub what-if \
  --location eastus2 \
  --template-file bicep/main.bicep \
  --parameters bicep/main.bicepparam

az deployment sub create \
  --location eastus2 \
  --template-file bicep/main.bicep \
  --parameters bicep/main.bicepparam
```

Use `bicep/main.example.bicepparam` as a starting template. Keep environment-specific parameter files local, for example `bicep/local.main.bicepparam`.

For public-internet Storage portal/blob access, add client/admin IPs to `allowedIpAddresses`; these IPs are applied to the Storage firewall and Network Security Perimeter rules. For public-internet Cosmos DB data reads that do not need Storage access, add IPs to `cosmosAllowedIpAddresses`; these IPs are applied only to the Cosmos DB account firewall.

The Bicep deployment also provisions a **Logic App Standard** resource on a Workflow Standard plan (`WS1` by default). Deploy the workflow code after the infrastructure finishes:

```powershell
$resourceGroupName = az deployment sub show `
  --name main `
  --query properties.outputs.resourceGroupName.value -o tsv

$logicAppName = az deployment sub show `
  --name main `
  --query properties.outputs.logicAppName.value -o tsv

.\scripts\Deploy-LogicAppWorkflow.ps1 `
  -ResourceGroupName $resourceGroupName `
  -LogicAppName $logicAppName
```

The deploy script returns the `SearchDocuments` HTTP trigger URL, including the `sig` query-string key. Treat that URL as a secret. Clients can call it without Entra auth:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri '<logic_app_trigger_url_with_sig>' `
  -ContentType 'application/json' `
  -Body '{"query":"nashville","mode":"hybrid","top":10}'
```

> **Easy Auth note**: Terraform creates the Entra app registration and client secret. Bicep does not emit a new secret value, so Easy Auth is disabled by default in the Bicep params. To enable it, create or reuse an Entra app registration and set `enableEasyAuth`, `easyAuthClientId`, and the secure `easyAuthClientSecret` parameter.

#### Option B: Existing Terraform deployment

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

| Variable | Example | Description |
|----------|---------|-------------|
| `location` | `"eastus2"` | Azure region for all resources |
| `project_name` | `"docpipeline"` | Short name used in resource naming (e.g. `rg-docpipeline-dev-xxxx`) |
| `environment` | `"dev"` | Environment label (`dev`, `staging`, `prod`) |
| `container_image` | `"docpipeline:latest"` | ACR image tag — leave commented out on first run, update after the initial ACR build in step 3 |
| `tags` | `{ owner = "your-team" }` | Tags applied to every resource |

Then run:

```bash
terraform init
terraform plan    # review what will be created
terraform apply   # type "yes" to confirm
```

> **Important**: After `terraform apply`, note the outputs — you'll need `acr_login_server`, `resource_group_name`, and the service endpoints for configuration. Run `terraform output` at any time to see them again.

Terraform also creates the Logic App Standard shell. From the repository root, deploy the workflow code after `terraform apply`:

```powershell
.\scripts\Deploy-LogicAppWorkflow.ps1 `
  -ResourceGroupName (terraform -chdir=terraform output -raw resource_group_name) `
  -LogicAppName (terraform -chdir=terraform output -raw logic_app_name)
```

> **📘 See [terraform/README.md](terraform/README.md)** for the full list of resources created, all configurable variables, post-deployment steps, and file-by-file documentation of the Terraform modules.

### 2. Update IP allowlists

Two places have hardcoded IP addresses that you need to update for your network:

- **`terraform/cosmos.tf`** — `ip_range_filter` on the Cosmos DB account
- **`terraform/nsp.tf`** — `addressPrefixes` in the NSP home access rule

Replace these with your public IP (find it at https://ifconfig.me).

### 3. Build and push the container image

```bash
# From the repo root
az acr build \
  --registry <acr_login_server> \
  --resource-group <resource_group_name> \
  --image docpipeline:latest .
```

### 4. Verify deployment

The Container App will automatically pull the new image. Check the dashboard:

```
https://<container_app_url>/
```

You can also verify the health endpoint:

```bash
curl https://<container_app_url>/health
# {"status":"healthy"}
```

### 5. Process a document

Upload any supported file to the `ingest` blob container:

```bash
az storage blob upload \
  --account-name <storage_account_name> \
  --container-name ingest \
  --file ./my-document.pdf \
  --auth-mode login
```

The pipeline will trigger automatically. Monitor progress on the dashboard.

## Local Development

### Option A: Docker Compose

```bash
cp .env.example .env
# Fill in values from your Terraform outputs (run `terraform -chdir=terraform output`)

docker compose up --build
```

The app will be available at `http://localhost:8000`. Note that Event Grid webhooks won't fire locally — you can test the API directly.

### Option B: Python Virtual Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in values

# Authenticate to Azure for DefaultAzureCredential
az login

uvicorn app.main:app --reload --port 8000
```

### Testing the API locally

```bash
# Health check
curl http://localhost:8000/health

# List jobs
curl http://localhost:8000/api/status

# Semantic search
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "water rights agreement", "top": 5}'

# Full-text search
curl -X POST http://localhost:8000/api/search/full-text \
  -H "Content-Type: application/json" \
  -d '{"query": "1200 Villa Place Nashville", "top": 30}'

# Hybrid vector + full-text search
curl -X POST http://localhost:8000/api/search/hybrid \
  -H "Content-Type: application/json" \
  -d '{"query": "restaurant near Franklin TN", "top": 30}'
```

### Testing Cosmos full-text/vector/hybrid search with PowerShell

Use `scripts\Test-DocumentSearch.ps1` when you want to test the raw Cosmos query path without going through the Container App. The script:

1. Gets Entra tokens with Azure CLI.
2. Calls Azure OpenAI embeddings for your phrase when the selected mode needs vectors.
3. Uses the Python Cosmos SDK from PowerShell for Cosmos DB full-text, vector, hybrid, and chunk queries.

```powershell
az login
az account set --subscription <subscription_id>

.\scripts\Test-DocumentSearch.ps1 `
  -Query "nashville" `
  -ResourceGroupName <resource_group_name> `
  -Mode All `
  -Top 10
```

With only the New York and Beverly Hills test PDFs indexed, `nashville` should return **0 full-text and 0 hybrid results** because hybrid search now requires a `search_text` match before applying RRF ranking. Vector-only mode is nearest-neighbor search and can still return the closest indexed document unless you pass `-MaxVectorDistance` to apply a client-side distance cutoff.

For full-text-only testing, use `-Mode FullText`; that path does not call Azure OpenAI. Vector, hybrid, and chunk modes require the caller to have `Cognitive Services OpenAI User` on the Azure OpenAI account and network access to the Azure OpenAI endpoint. The script uses `-EmbeddingApiVersion 2024-12-01-preview` by default for `text-embedding-3-small`; `-OpenAIApiVersion` remains as a backward-compatible alias. Install local script dependencies with `pip install -r requirements.txt` if `azure-cosmos` or `azure-identity` is missing. Cosmos full-text/hybrid search requires the newer Cosmos SDK pipeline, so use `azure-cosmos` 4.16.3 or later.

## Environment Variables

All configuration is via environment variables. **No API keys** — the app uses `DefaultAzureCredential` (managed identity in Azure, `az login` locally).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Yes | — | Document Intelligence endpoint URL |
| `AZURE_OPENAI_ENDPOINT` | Yes | — | Azure OpenAI endpoint URL |
| `AZURE_STORAGE_ACCOUNT_URL` | Yes | — | Storage account blob endpoint |
| `COSMOS_ENDPOINT` | Yes | — | Cosmos DB account endpoint |
| `AZURE_MAPS_CLIENT_ID` | Yes for geocoding | — | Azure Maps account client ID (`properties.uniqueId`) for Entra auth |
| `AZURE_MAPS_ENDPOINT` | No | `https://atlas.microsoft.com` | Azure Maps endpoint |
| `AZURE_MAPS_COUNTRY_SET` | No | `US` | Country filter for fuzzy search |
| `AZURE_MAPS_LANGUAGE` | No | `en-US` | Preferred Azure Maps response language |
| `AZURE_MAPS_FUZZY_SEARCH_LIMIT` | No | `1` | Number of fuzzy-search results requested per location |
| `AZURE_MAPS_MAX_FUZZY_LEVEL` | No | `1` | Maximum typo tolerance for fuzzy search |
| `AZURE_MAPS_TIMEOUT_SECONDS` | No | `10` | Azure Maps request timeout |
| `AZURE_OPENAI_API_VERSION` | No | `2025-04-01-preview` | OpenAI API version |
| `AZURE_OPENAI_MODEL_NAME` | No | `gpt-5.1` | Chat model deployment name |
| `AZURE_OPENAI_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Embedding model deployment |
| `AZURE_OPENAI_EMBEDDING_API_VERSION` | No | `2024-12-01-preview` | Embeddings API version |
| `COSMOS_DATABASE_NAME` | No | `docprocessing` | Cosmos DB database name |
| `SEARCH_DEFAULT_TOP` | No | `30` | Default result count when search requests omit `top` |
| `SEARCH_MAX_TOP` | No | `1000` | Maximum `top` accepted by search endpoints |
| `BACKFILL_DEFAULT_LIMIT` | No | `25` | Default number of result documents scanned per search-index backfill batch |
| `BACKFILL_MAX_LIMIT` | No | `200` | Maximum backfill batch size accepted by the admin endpoint |
| `MAX_CONCURRENT_JOBS` | No | `5` | Max parallel processing jobs |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `AZURE_TENANT_ID` | No | — | For local dev if auto-detect fails |
| `AZURE_CLIENT_ID` | No | — | For local dev if auto-detect fails |

## Project Structure

```
├── app/                          # FastAPI application (runs in the container)
│   ├── main.py                   # App entry point, lifespan, router registration
│   ├── config.py                 # Settings from environment variables
│   ├── agents/
│   │   └── planner.py            # PipelineOrchestrator — 7-step processing pipeline
│   ├── models/
│   │   ├── document.py           # DocumentAnalysisResult schema (output)
│   │   └── processing.py         # ProcessingJob, ProcessingStep (job tracking)
│   ├── plugins/                  # Azure service wrappers
│   │   ├── blob_plugin.py        # Azure Blob Storage operations
│   │   ├── cosmos_plugin.py      # Cosmos DB CRUD + vector search
│   │   ├── doc_intel_plugin.py   # Azure Document Intelligence
│   │   ├── llm_plugin.py         # Azure OpenAI analysis + embeddings
│   │   └── maps_plugin.py        # Azure Maps fuzzy-search geocoding
│   ├── routers/                  # API endpoint handlers
│   │   ├── events.py             # Event Grid webhook
│   │   ├── status.py             # Job list / detail / retry / delete
│   │   ├── documents.py          # Analysis results + original download
│   │   └── search.py             # Vector similarity search
│   ├── services/
│   │   └── processing.py         # Background async worker (asyncio.Queue)
│   └── web/static/
│       └── index.html            # Status dashboard (single-page HTML)
├── terraform/                    # Existing Terraform Infrastructure as Code
├── bicep/                        # Bicep deployment equivalent plus Azure Maps
├── logicapp/                      # Logic App Standard workflow project
│   └── SearchDocuments/           # Key-protected search facade workflow
├── scripts/                      # Operational helper scripts and search/Logic App utilities
├── queries/                      # Log Analytics KQL queries
├── legacy/                       # Archived Azure Functions code (reference only)
├── Dockerfile                    # Multi-stage Python 3.11 build
├── docker-compose.yml            # Local development
├── requirements.txt              # Python dependencies
└── .env.example                  # Environment variable template
```

## Blob Container Lifecycle

| Container | Purpose |
|-----------|---------|
| `ingest` | Landing zone — upload files here to trigger processing |
| `processing` | Working area — files moved here during pipeline execution |
| `completed` | Results — JSON analysis output stored as `{job_id}/{filename}.json` |
| `originaldocument` | Archive — original files moved here after successful processing |

## Cosmos DB Collections

**Database**: `docprocessing`

| Container | Partition Key | Contents |
|-----------|---------------|----------|
| `jobs` | `/id` | Processing job records (status, steps, timestamps) |
| `results` | `/jobId` | Analysis results with vector embeddings |

Location enrichments are stored on each result at `key_fields.entities.geocoded_locations`. Each item includes the original query, latitude, longitude, formatted address, display name, result type, score, and source.

Each result also stores `search_text`, a normalized full-text field that includes the title, summary, key fields, extracted entities, page summaries, geocoded addresses, display names, and coordinates.

The `results` container has vector indexes (quantizedFlat, cosine, 1536d) on:
- `/summary_vector` — embedding of `search_text` when present, otherwise the document summary
- `/purpose_vector` — embedding of the document purpose
- `/chunks/vector` — per-chunk embeddings for granular retrieval

The `results` container has a full-text policy and full-text index on:
- `/search_text` — result-level text for BM25 full-text and RRF hybrid search

Hybrid search requires `FullTextContainsAny(c.search_text, ...)` before applying RRF over `VectorDistance()` and `FullTextScore()`. This keeps location searches precise: if only New York and Beverly Hills address documents are indexed, searching for `nashville` returns no full-text or hybrid hits instead of returning the nearest unrelated vector. Existing items processed before `search_text` was introduced need a backfill/reprocess before they appear in full-text or hybrid search results.

### Search-index backfill / reprocess

The app includes an operator-triggered backfill path for existing Cosmos results. It does not rerun Document Intelligence or LLM extraction; it rebuilds the search material that can be derived from the stored result document:

- missing or invalid Azure Maps `key_fields.entities.geocoded_locations` entries, using stored location/entity text
- `search_text`
- `summary_vector`
- `purpose_vector`
- existing `chunks[].vector` values when chunk text exists
- vector-adjacent metadata (`summary_vector_metadata`, `purpose_vector_metadata`, `chunks[].vector_metadata`)
- top-level `search_index_metadata`

Run a dry-run first:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$containerAppUrl/api/admin/search-index/backfill" `
  -ContentType 'application/json' `
  -Body '{"dry_run":true,"limit":25,"include_geocoding":true,"include_chunks":true}'
```

The batch endpoint scans stale search-index or missing-geocode candidates by default, not every Cosmos result document. `candidate_documents_scanned: 0` means there are no remaining documents that need backfill for the current search-index version/model/API settings or missing geocodes. It does **not** mean the results container is empty. Use `"force": true` when you intentionally want to inspect or regenerate current documents.

Execute the batch:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$containerAppUrl/api/admin/search-index/backfill" `
  -ContentType 'application/json' `
  -Body '{"dry_run":false,"limit":25,"include_geocoding":true,"include_chunks":true}'
```

When `include_geocoding` is enabled, the execute path runs Azure Maps first for documents that have extracted location/entity text but no usable lat/lon results. If geocoding changes the document, the app rebuilds `search_text` and regenerates any vector whose source-text hash is no longer current so the new coordinates are represented in full-text and hybrid search.

Backfill one document by job ID:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$containerAppUrl/api/admin/search-index/backfill/<job_id>" `
  -ContentType 'application/json' `
  -Body '{"dry_run":false}'
```

Embeddings are not reliably identifiable from the vector values themselves. `text-embedding-ada-002` and `text-embedding-3-small` can both produce 1536-dimensional vectors, so dimension checks alone are insufficient. New and backfilled results store the embedding deployment, API version, dimensions, source field, source-text hash, generated timestamp, and search-index version next to each vector. Anything missing that metadata, or whose metadata does not match the current deployment/API/source hash, is regenerated by the backfill.

Cosmos DB full-text search can index existing string fields by changing the container `fullTextPolicy` and `indexingPolicy.fullTextIndexes`, but paths must be explicit and index updates rebuild asynchronously. It is not a wildcard full-text index across arbitrary nested strings. Keeping `search_text` as a materialized field gives one stable path for BM25 and hybrid RRF queries while preserving control over which fields, entities, geocoded addresses, and coordinates are searchable.

## Logic App facade for Power Platform

The Bicep deployment creates a **Logic App Standard** resource on a Workflow Standard plan, not a Consumption workflow. This is the supported single-tenant model for new Logic Apps. If you need full App Service isolation, deploy the Standard app into an ASE v3 plan; legacy Logic Apps ISE is not the recommended path for new workloads.

The workflow source lives in `logicapp\SearchDocuments\workflow.json`. It is a thin facade:

1. A caller invokes the `SearchDocuments` HTTP trigger with the callback URL `sig` key.
2. The workflow validates `query` and `top`.
3. The workflow routes `mode`:
   - `hybrid` -> `POST /api/search/hybrid`
   - `full-text` -> `POST /api/search/full-text`
   - `vector` -> `POST /api/search`
4. The Container App generates embeddings for vector/hybrid modes and queries Cosmos DB.
5. The workflow returns the Container App status code and response body unchanged.

Request body:

```json
{
  "query": "nashville",
  "top": 10,
  "mode": "hybrid",
  "vector_field": "summary_vector"
}
```

`mode` defaults to `hybrid`, `top` defaults to `SEARCH_DEFAULT_TOP`, and `vector_field` defaults to `summary_vector`.

Deploy or update workflow code:

```powershell
.\scripts\Deploy-LogicAppWorkflow.ps1 `
  -ResourceGroupName <resource_group_name> `
  -LogicAppName <logic_app_name>
```

The script returns the HTTP trigger callback URL. This URL is key-protected; rotate/regenerate the trigger key if the URL is exposed. Store it as a secret in Power Platform or whichever client calls the workflow.

Direct Cosmos access from Logic Apps is possible, but Cosmos DB REST calls with Entra ID require Cosmos-specific `type=aad&ver=1.0&sig=<token>` authorization header encoding. `scripts\Test-DocumentSearch.ps1` demonstrates that lower-level flow for testing. The deployed Logic App intentionally delegates embedding and Cosmos query construction to the Container App so there is one implementation of the search logic.

## Monitoring and KQL

Cosmos DB `DataPlaneRequests` diagnostics are sent to the solution Log Analytics workspace using resource-specific tables. Firewall-denied data-plane requests are `403` responses, commonly with substatus `5301`.

Use `queries/cosmos-firewall-blocks.kql` in the solution Log Analytics workspace to identify blocked client IPs, affected accounts/containers, operations, and activity IDs.

```powershell
$workspaceId = az monitor log-analytics workspace show `
  --resource-group <resource_group_name> `
  --workspace-name <log_analytics_workspace_name> `
  --query customerId -o tsv

az monitor log-analytics query `
  --workspace $workspaceId `
  --analytics-query "@queries\cosmos-firewall-blocks.kql" `
  --timespan P1D `
  -o table
```

Use the `@file` form with Azure CLI; passing the multi-line query through a PowerShell variable can truncate execution to the first line.

## Authentication & RBAC

The Container App uses **system-assigned managed identity** with these roles:

| Role | Scope |
|------|-------|
| Storage Blob Data Contributor | Storage Account |
| Storage Blob Delegator | Storage Account |
| Cosmos DB Built-in Data Contributor | Cosmos DB |
| Cognitive Services OpenAI User | Azure OpenAI |
| Cognitive Services User | Document Intelligence |
| Azure Maps Search and Render Data Reader | Azure Maps |
| AcrPull (user-assigned MI) | Container Registry |

Entra ID Easy Auth protects the web UI and API. Event Grid webhook and health endpoints are excluded from auth.

The Logic App Standard HTTP trigger is protected by its callback URL signature (`sig` query string). The workflow currently calls the Container App facade, so it does not need direct Cosmos/OpenAI RBAC assignments. If you change the workflow to query Cosmos or Azure OpenAI directly, assign the Logic App system identity `Cosmos DB Built-in Data Reader` and `Cognitive Services OpenAI User`.

### Grant Cosmos DB read access to users

Use the helper script to grant least-privilege read access to Cosmos DB data for future users:

```powershell
.\scripts\Grant-CosmosDataReader.ps1 -User user1@contoso.com,user2@contoso.com
```

The script assigns:

- `Cosmos DB Built-in Data Reader` for Cosmos DB for NoSQL data-plane read/query access.
- `Cosmos DB Account Reader Role` for Azure account metadata/portal discovery, unless `-SkipAccountReaderRole` is specified.

### Grant Cosmos DB editor access to users

Use the editor helper when users need to create, update, or delete documents and manage databases/containers:

```powershell
.\scripts\Grant-CosmosDataEditor.ps1 -User user1@contoso.com,user2@contoso.com
```

The script assigns:

- `Cosmos DB Built-in Data Contributor` for Cosmos DB for NoSQL data-plane create/read/update/query/delete item access.
- `Cosmos DB Operator` for Azure control-plane database/container management, unless `-SkipCosmosOperatorRole` is specified.

### Grant Storage Blob access to users

Azure Owner or Contributor grants management-plane access to the storage account, but it does not grant data-plane access to list/read/write blobs when shared key access is disabled. Use the helper script for portal or SDK access to blob containers:

```powershell
.\scripts\Grant-StorageBlobDataAccess.ps1 -User user1@contoso.com,user2@contoso.com -Role Reader
```

Use `-Role Contributor` when the user also needs to upload, overwrite, or delete blobs. Use `-ContainerName <name>` to scope access to a single container instead of the full storage account.
