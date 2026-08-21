variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus2"
}

variable "project_name" {
  description = "Short project name used as a prefix"
  type        = string
  default     = "docpipeline"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "allowed_ip_addresses" {
  description = "Public IP addresses allowed to reach shared limited public endpoints, including Storage firewall and Network Security Perimeter rules"
  type        = list(string)
  default     = ["71.200.56.126"]
}

variable "cosmos_allowed_ip_addresses" {
  description = "Additional public IP addresses allowed to reach Cosmos DB data-plane APIs only"
  type        = list(string)
  default     = []
}

variable "additional_nsp_subscription_ids" {
  description = "Additional subscription IDs allowed by the Network Security Perimeter inbound rule"
  type        = list(string)
  default     = ["4345216c-3da4-4537-97ff-2a9f5053a420"]
}

variable "vnet_address_space" {
  description = "Address space for the VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "container_app_subnet_cidr" {
  description = "CIDR for the Container Apps subnet"
  type        = string
  default     = "10.0.0.0/23"
}

variable "private_endpoints_subnet_cidr" {
  description = "CIDR for the private endpoints subnet"
  type        = string
  default     = "10.0.2.0/24"
}

variable "ai_services_subnet_cidr" {
  description = "CIDR for AI services subnet"
  type        = string
  default     = "10.0.3.0/24"
}

variable "logic_app_integration_subnet_cidr" {
  description = "CIDR for the shared App Service regional VNet integration subnet used by the Function App and optional Logic App"
  type        = string
  default     = "10.0.4.0/26"
}

variable "openai_model_name" {
  description = "Azure OpenAI chat model deployment name"
  type        = string
  default     = "gpt-5.1"
}

variable "openai_model_version" {
  description = "Azure OpenAI chat model version"
  type        = string
  default     = "2025-11-13"
}

variable "openai_model_sku_name" {
  description = "Azure OpenAI chat model deployment SKU name"
  type        = string
  default     = "GlobalStandard"
}

variable "openai_model_capacity" {
  description = "Azure OpenAI chat model deployment capacity in thousands of TPM"
  type        = number
  default     = 30
}

variable "openai_api_version" {
  description = "Azure OpenAI chat/completions API version"
  type        = string
  default     = "2025-04-01-preview"
}

variable "embedding_model_name" {
  description = "Azure OpenAI embedding model deployment name"
  type        = string
  default     = "text-embedding-3-small"
}

variable "embedding_model_version" {
  description = "Azure OpenAI embedding model version"
  type        = string
  default     = "1"
}

variable "embedding_model_sku_name" {
  description = "Azure OpenAI embedding model deployment SKU name"
  type        = string
  default     = "GlobalStandard"
}

variable "embedding_model_capacity" {
  description = "Azure OpenAI embedding model deployment capacity in thousands of TPM"
  type        = number
  default     = 30
}

variable "openai_embedding_api_version" {
  description = "Azure OpenAI embeddings API version"
  type        = string
  default     = "2024-12-01-preview"
}

variable "container_image" {
  description = "Container image name (without registry prefix). Set after first ACR push."
  type        = string
  default     = "docpipeline:latest"
}

variable "container_cpu" {
  description = "Container CPU cores"
  type        = number
  default     = 1.0
}

variable "container_memory" {
  description = "Container memory in Gi"
  type        = string
  default     = "2Gi"
}

variable "container_min_replicas" {
  type    = number
  default = 1
}

variable "container_max_replicas" {
  type    = number
  default = 3
}

variable "search_default_top" {
  description = "Default number of results returned by search endpoints when top is omitted"
  type        = number
  default     = 30
}

variable "search_max_top" {
  description = "Maximum top value accepted by search endpoints"
  type        = number
  default     = 1000
}

variable "backfill_default_limit" {
  description = "Default number of result documents scanned by each search-index backfill batch"
  type        = number
  default     = 25
}

variable "backfill_max_limit" {
  description = "Maximum number of result documents accepted by each search-index backfill batch"
  type        = number
  default     = 200
}

variable "reprocess_default_limit" {
  description = "Default number of ingest blobs scanned by each requeue batch"
  type        = number
  default     = 100
}

variable "reprocess_max_limit" {
  description = "Maximum number of ingest blobs accepted by each requeue batch"
  type        = number
  default     = 5000
}

variable "logic_app_sku_name" {
  description = "Logic App Standard Workflow Service Plan SKU"
  type        = string
  default     = "WS1"

  validation {
    condition     = contains(["WS1", "WS2", "WS3"], var.logic_app_sku_name)
    error_message = "logic_app_sku_name must be one of WS1, WS2, or WS3."
  }
}

variable "search_function_sku_name" {
  description = "Azure Functions Elastic Premium SKU for the Power Platform search facade"
  type        = string
  default     = "EP1"

  validation {
    condition     = contains(["EP1", "EP2", "EP3"], var.search_function_sku_name)
    error_message = "search_function_sku_name must be one of EP1, EP2, or EP3."
  }
}

variable "cosmos_throughput_mode" {
  description = "Cosmos DB capacity mode"
  type        = string
  default     = "Serverless"
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
