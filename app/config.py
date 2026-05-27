"""Application configuration via environment variables. No API keys — managed identity only."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # --- Azure Identity ---
    azure_tenant_id: str = Field(default="", description="Azure AD tenant ID (optional, for local dev)")
    azure_client_id: str = Field(default="", description="Azure AD client ID (optional, for local dev)")

    # --- Azure Document Intelligence ---
    azure_document_intelligence_endpoint: str = Field(..., description="Document Intelligence endpoint URL")

    # --- Azure OpenAI ---
    azure_openai_endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    azure_openai_api_version: str = Field(default="2024-12-01-preview")
    azure_openai_model_name: str = Field(default="gpt-4o")
    azure_openai_embedding_model: str = Field(default="text-embedding-ada-002")

    # --- Azure Storage ---
    azure_storage_account_url: str = Field(..., description="Storage account blob endpoint, e.g. https://<name>.blob.core.windows.net")
    storage_container_ingest: str = Field(default="ingest")
    storage_container_processing: str = Field(default="processing")
    storage_container_completed: str = Field(default="completed")
    storage_container_original: str = Field(default="originaldocument")

    # --- Azure Cosmos DB ---
    cosmos_endpoint: str = Field(..., description="Cosmos DB account endpoint")
    cosmos_database_name: str = Field(default="docprocessing")
    cosmos_container_jobs: str = Field(default="jobs")
    cosmos_container_results: str = Field(default="results")

    # --- Application ---
    max_concurrent_jobs: int = Field(default=5, description="Max parallel processing jobs")
    log_level: str = Field(default="INFO")
    port: int = Field(default=8000)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()  # type: ignore[call-arg]
