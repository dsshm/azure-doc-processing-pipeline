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

variable "openai_model_name" {
  description = "Azure OpenAI chat model deployment name"
  type        = string
  default     = "gpt-4o"
}

variable "openai_model_version" {
  description = "Azure OpenAI chat model version"
  type        = string
  default     = "2024-11-20"
}

variable "embedding_model_name" {
  description = "Azure OpenAI embedding model deployment name"
  type        = string
  default     = "text-embedding-ada-002"
}

variable "embedding_model_version" {
  description = "Azure OpenAI embedding model version"
  type        = string
  default     = "2"
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
