# Document Processing Pipeline

An event-driven document processing pipeline running as a **FastAPI Container App** on Azure. The system automates the ingestion, extraction, analysis, and indexing of documents — turning unstructured files into structured, searchable data with no manual intervention.

### How it works

1. A user uploads a document (PDF, Word, image, etc.) to the **Azure Blob Storage** `ingest` container.
2. **Azure Event Grid** detects the `BlobCreated` event and sends a webhook to the Container App.
3. The app queues a processing job and a background worker runs a 5-step pipeline:
   - **Move** the blob from `ingest` → `processing` (prevents duplicate triggers).
   - **Extract** text, tables, barcodes, and layout using **Azure Document Intelligence** (prebuilt-layout model).
   - **Analyze** the extracted content with **Azure OpenAI GPT-4o** — entity extraction, category classification, keyword tagging, and hierarchical summarization (page-level → section → document).
   - **Generate vector embeddings** using **Azure OpenAI text-embedding-ada-002** (1536-dimensional) for the document summary, purpose, and individual text chunks.
   - **Store** structured results and embeddings in **Azure Cosmos DB** (NoSQL, serverless) with vector indexes for semantic search.
4. The original document is archived to the `originaldocument` container.
5. Users can monitor jobs on the **status dashboard**, search documents semantically via the **vector search API**, and download original files via SAS-protected URLs.

### Azure services used

| Service | Role |
|---------|------|
| **Azure Container Apps** | Hosts the FastAPI application (Uvicorn, 2 workers, VNet-integrated) |
| **Azure Blob Storage** | Document lifecycle — `ingest`, `processing`, `completed`, `originaldocument` containers |
| **Azure Event Grid** | Triggers processing on blob upload (`BlobCreated` system topic) |
| **Azure Document Intelligence** | OCR / layout extraction from 13+ file types |
| **Azure OpenAI Service** | GPT-4o for analysis; text-embedding-ada-002 for vector embeddings |
| **Azure Cosmos DB** (NoSQL, Serverless) | Job tracking, analysis results, and vector search via `VectorDistance()` |
| **Azure Container Registry** | Stores the Docker image; pulled by Container Apps via managed identity |
| **Microsoft Entra ID** | Easy Auth on the Container App; RBAC for all service-to-service auth (no API keys) |

## Features

- **Automated ingestion** — drop a file in the `ingest` container, processing starts automatically via Event Grid
- **Document Intelligence extraction** — text, tables, barcodes, layout from PDFs, images, Office docs (13+ file types)
- **LLM analysis** — per-page entity/category/keyword extraction, hierarchical summarization for large documents
- **Vector embeddings** — summary, purpose, and chunk-level embeddings (text-embedding-ada-002, 1536 dimensions)
- **Cosmos DB vector search** — semantic search across documents and chunks using `VectorDistance()`
- **Status dashboard** — real-time job monitoring, retry failed jobs, delete jobs
- **Zero API keys** — 100% managed identity with RBAC, no secrets in config
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
| `POST` | `/api/search/chunks` | Chunk-level vector search (`{query, top}`) |

All endpoints except `/api/events/*` and `/health` are protected by Entra ID Easy Auth.

## Prerequisites

- **Azure subscription** with permissions to create resources
- **Azure CLI** (`az`) — [install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Terraform** >= 1.5 — [install](https://developer.hashicorp.com/terraform/install)
- **Docker** (for local development) — [install](https://docs.docker.com/get-docker/)
- **Python** 3.11+ (for local development without Docker)

> **💡 Tip — Azure Cloud Shell**: If you don't want to install the Azure CLI or Terraform locally, you can run the infrastructure deployment entirely from [Azure Cloud Shell](https://learn.microsoft.com/en-us/azure/cloud-shell/overview) (Bash). It comes with `az`, `terraform`, and `git` pre-installed. Clone this repo in Cloud Shell, then follow the Terraform steps below. Docker and Python are only needed for local development and are **not** required for deploying infrastructure.

## Deployment

### 1. Provision infrastructure with Terraform

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
```

## Environment Variables

All configuration is via environment variables. **No API keys** — the app uses `DefaultAzureCredential` (managed identity in Azure, `az login` locally).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Yes | — | Document Intelligence endpoint URL |
| `AZURE_OPENAI_ENDPOINT` | Yes | — | Azure OpenAI endpoint URL |
| `AZURE_STORAGE_ACCOUNT_URL` | Yes | — | Storage account blob endpoint |
| `COSMOS_ENDPOINT` | Yes | — | Cosmos DB account endpoint |
| `AZURE_OPENAI_API_VERSION` | No | `2024-12-01-preview` | OpenAI API version |
| `AZURE_OPENAI_MODEL_NAME` | No | `gpt-4o` | Chat model deployment name |
| `AZURE_OPENAI_EMBEDDING_MODEL` | No | `text-embedding-ada-002` | Embedding model deployment |
| `COSMOS_DATABASE_NAME` | No | `docprocessing` | Cosmos DB database name |
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
│   │   └── planner.py            # PipelineOrchestrator — 5-step processing pipeline
│   ├── models/
│   │   ├── document.py           # DocumentAnalysisResult schema (output)
│   │   └── processing.py         # ProcessingJob, ProcessingStep (job tracking)
│   ├── plugins/                  # Azure service wrappers
│   │   ├── blob_plugin.py        # Azure Blob Storage operations
│   │   ├── cosmos_plugin.py      # Cosmos DB CRUD + vector search
│   │   ├── doc_intel_plugin.py   # Azure Document Intelligence
│   │   └── llm_plugin.py         # Azure OpenAI analysis + embeddings
│   ├── routers/                  # API endpoint handlers
│   │   ├── events.py             # Event Grid webhook
│   │   ├── status.py             # Job list / detail / retry / delete
│   │   ├── documents.py          # Analysis results + original download
│   │   └── search.py             # Vector similarity search
│   ├── services/
│   │   └── processing.py         # Background async worker (asyncio.Queue)
│   └── web/static/
│       └── index.html            # Status dashboard (single-page HTML)
├── terraform/                    # Infrastructure as Code (see terraform/README.md)
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

The `results` container has vector indexes (quantizedFlat, cosine, 1536d) on:
- `/summary_vector` — embedding of the document summary
- `/purpose_vector` — embedding of the document purpose
- `/chunks/vector` — per-chunk embeddings for granular retrieval

## Authentication & RBAC

The Container App uses **system-assigned managed identity** with these roles:

| Role | Scope |
|------|-------|
| Storage Blob Data Contributor | Storage Account |
| Storage Blob Delegator | Storage Account |
| Cosmos DB Built-in Data Contributor | Cosmos DB |
| Cognitive Services OpenAI User | Azure OpenAI |
| Cognitive Services User | Document Intelligence |
| AcrPull (user-assigned MI) | Container Registry |

Entra ID Easy Auth protects the web UI and API. Event Grid webhook and health endpoints are excluded from auth.
