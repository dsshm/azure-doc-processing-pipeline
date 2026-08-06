"""Application configuration via environment variables. No API keys — managed identity only."""

from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    # --- Azure Identity ---
    azure_tenant_id: str = Field(default="", description="Azure AD tenant ID (optional, for local dev)")
    azure_client_id: str = Field(default="", description="Azure AD client ID (optional, for local dev)")

    # --- Azure Document Intelligence ---
    azure_document_intelligence_endpoint: str = Field(..., description="Document Intelligence endpoint URL")

    # --- Azure OpenAI ---
    azure_openai_endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    azure_openai_api_version: str = Field(default="2025-04-01-preview")
    azure_openai_model_name: str = Field(default="gpt-5.1")
    azure_openai_embedding_model: str = Field(default="text-embedding-3-small")
    azure_openai_embedding_api_version: str = Field(default="2024-12-01-preview")

    # --- Azure Maps ---
    azure_maps_endpoint: str = Field(default="https://atlas.microsoft.com")
    azure_maps_client_id: str = Field(default="", description="Azure Maps account client ID for Entra auth")
    azure_maps_country_set: str = Field(default="US")
    azure_maps_language: str = Field(default="en-US")
    azure_maps_fuzzy_search_limit: int = Field(default=1)
    azure_maps_max_fuzzy_level: int = Field(default=1)
    azure_maps_timeout_seconds: int = Field(default=10)

    # --- Azure Storage ---
    azure_storage_account_url: str = Field(..., description="Storage account blob endpoint, e.g. https://<name>.blob.core.windows.net")
    storage_container_ingest: str = Field(default="ingest")
    storage_container_processing: str = Field(default="processing")
    storage_container_completed: str = Field(default="completed")
    storage_container_original: str = Field(default="originaldocument")
    storage_container_failed: str = Field(default="failed")

    # --- Azure Cosmos DB ---
    cosmos_endpoint: str = Field(..., description="Cosmos DB account endpoint")
    cosmos_database_name: str = Field(default="docprocessing")
    cosmos_container_jobs: str = Field(default="jobs")
    cosmos_container_results: str = Field(default="results")

    # --- Application ---
    search_default_top: int = Field(default=30, description="Default search result count when request omits top")
    search_max_top: int = Field(default=1000, description="Maximum accepted search result count")
    backfill_default_limit: int = Field(default=25, description="Default search index backfill batch size")
    backfill_max_limit: int = Field(default=200, description="Maximum search index backfill batch size")
    reprocess_default_limit: int = Field(default=100, description="Default ingest reprocess batch size")
    reprocess_max_limit: int = Field(default=5000, description="Maximum ingest reprocess batch size")
    max_concurrent_jobs: int = Field(default=5, description="Max parallel processing jobs")
    log_level: str = Field(default="INFO")
    port: int = Field(default=8000)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_search_limits(self) -> "Settings":
        if self.search_default_top < 1:
            raise ValueError("SEARCH_DEFAULT_TOP must be at least 1.")
        if self.search_max_top < 1:
            raise ValueError("SEARCH_MAX_TOP must be at least 1.")
        if self.search_default_top > self.search_max_top:
            raise ValueError("SEARCH_DEFAULT_TOP cannot exceed SEARCH_MAX_TOP.")
        if self.backfill_default_limit < 1:
            raise ValueError("BACKFILL_DEFAULT_LIMIT must be at least 1.")
        if self.backfill_max_limit < 1:
            raise ValueError("BACKFILL_MAX_LIMIT must be at least 1.")
        if self.backfill_default_limit > self.backfill_max_limit:
            raise ValueError("BACKFILL_DEFAULT_LIMIT cannot exceed BACKFILL_MAX_LIMIT.")
        if self.reprocess_default_limit < 1:
            raise ValueError("REPROCESS_DEFAULT_LIMIT must be at least 1.")
        if self.reprocess_max_limit < 1:
            raise ValueError("REPROCESS_MAX_LIMIT must be at least 1.")
        if self.reprocess_default_limit > self.reprocess_max_limit:
            raise ValueError("REPROCESS_DEFAULT_LIMIT cannot exceed REPROCESS_MAX_LIMIT.")
        return self


settings = Settings()  # type: ignore[call-arg]
