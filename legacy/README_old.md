# Document Intelligence Azure Function (Legacy)

This repository contains an Azure Functions Python project that provides document analysis, LLM-driven summarization, and structured content extraction for processing documents.

## What this function does
- **Document Intelligence**: Extracts text, tables, barcodes, and structural information from PDFs and images using Azure AI Document Intelligence
- **LLM Analysis**: Performs page-by-page analysis with Azure OpenAI, extracting entities, categories, keywords, and generating intelligent summaries
- **Hierarchical Summarization**: Automatically handles large multi-page documents using intelligent reduction techniques to avoid token limits
- **Structured Output**: Returns JSON-formatted analysis with Pydantic-validated schemas for reliable data extraction
- **Storage Integration**: Reads documents from Azure Blob Storage using managed identity or key-based authentication

## Architecture

### Endpoints

#### `/api/analyze` (Document Intelligence)
Analyzes documents using Azure AI Document Intelligence to extract:
- Full text content with page segmentation
- Tables with structured row/column data
- Barcodes (QR codes, etc.)
- Page dimensions and layout information

**Input**: JSON with `file_url` pointing to a blob storage document
**Output**: Structured JSON with content, pages, tables, and barcodes

#### `/api/describe` (LLM Analysis)
Performs intelligent document analysis using Azure OpenAI:
- **Page-by-page analysis**: Extracts entities, categories, keywords from each page
- **Document-level summary**: Intelligently consolidates page analyses into cohesive narrative
- **Hierarchical reduction**: Automatically chunks large documents (10 pages per batch) to handle any document size
- **Entity extraction**: Identifies people, organizations, locations, dates, events with supporting evidence
- **Category classification**: Maps, geography, history, blueprints, engineering documents
- **Multi-language support**: Detects and can translate non-English content

**Input**: 
- Direct format: `{"pages": [{"page_number": 1, "content": "..."}]}`
- Document Intelligence format: Output from `/api/analyze` endpoint (nested under `analysis` key)

**Output**: Consolidated analysis with document summary, entities, categories, keywords, and per-page analyses

### Services Architecture

#### `services/blob_service.py`
- Downloads files from Azure Blob Storage
- Supports managed identity (DefaultAzureCredential) or connection string authentication
- Parses blob URLs and handles container/path extraction

#### `services/llm_summary.py` (NEW)
- **`DocumentSummarizer` class**: Handles intelligent multi-page document summarization
- **Token estimation**: Uses tiktoken to estimate input size
- **Single-pass reduction**: For small documents (<15k tokens)
- **Hierarchical reduction**: For large documents, reduces in batches then consolidates
- **Configurable chunking**: Default 10 pages per chunk, adjustable for performance tuning

## Prerequisites (Deployment)

### Azure Resources (Required)
- **Resource Group**
- **Storage Account** (for Function App runtime)
- **Function App** (Linux/Windows, Functions v4, Python 3.10+)
- **Azure AI Document Intelligence** (Cognitive Services resource)
- **Azure OpenAI** (with gpt-4o or gpt-4 deployment)
- **(Optional)** Key Vault for secrets management

### Identity & Permissions
**Recommended: Managed Identity**
- Enable system-assigned or user-assigned managed identity on Function App
- Grant RBAC roles:
  - **Storage Blob Data Reader** on storage accounts with documents
  - **Cognitive Services OpenAI User** on Azure OpenAI resource
  - **Cognitive Services User** on Document Intelligence resource

**Alternative: Service Principal**
- Create Azure AD app registration
- Store credentials (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`) in Key Vault or secure environment
- Grant same RBAC roles as managed identity

## Required Environment Variables

### Document Intelligence
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Yes | Document Intelligence endpoint | `https://<resource>.cognitiveservices.azure.com/` |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Yes* | API key (or use Managed Identity) | `<key>` |

*Can be omitted if using Managed Identity with proper RBAC roles

### Azure OpenAI (LLM Analysis)
| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint | `https://<resource>.openai.azure.com/` |
| `AZURE_OPENAI_KEY` | Yes* | API key (or use Managed Identity) | `<key>` |
| `AZURE_OPENAI_API_VERSION` | Yes | API version | `2024-12-01-preview` |
| `AZURE_OPENAI_MODEL_NAME` | Yes | Chat model deployment name | `gpt-4o` |
| `AZURE_OPENAI_EMBEDDING_MODEL` | Optional | Embedding model deployment name | `text-embedding-ada-002` |

*Can be omitted if using Managed Identity with proper RBAC roles

### Optional (Service Principal Authentication)
| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_TENANT_ID` | No | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | No | Service principal client ID |
| `AZURE_CLIENT_SECRET` | No | Service principal secret |

**Note**: Do NOT commit `local.settings.json` to source control. Use Azure Key Vault references: `@Microsoft.KeyVault(SecretUri=...)`

## Key Features

### Intelligent Document Processing Pipeline

1. **Document Intelligence Extraction** (`/api/analyze`)
   - Extracts text with page boundaries using span offsets
   - Preserves document structure (lines, words, tables)
   - Handles multi-page PDFs and images
   - Barcode detection and decoding

2. **LLM Analysis** (`/api/describe`)
   - Accepts Document Intelligence output directly (nested `analysis` structure)
   - Page-by-page entity and category extraction
   - Automatic token limit management with hierarchical reduction
   - Consolidated document-level summary generation
   - Structured JSON output with Pydantic validation

3. **Hierarchical Summarization** (for large documents)
   - Automatically reduces large documents in batches
   - Consolidates summaries while preserving key information
   - Avoids token limit issues with intelligent chunking


