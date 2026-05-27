"""Semantic Kernel plugin for Azure Cosmos DB operations.

Handles job tracking and analysis result persistence.
Auth: DefaultAzureCredential (Cosmos DB RBAC — no keys).
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Optional

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential
from semantic_kernel.functions import kernel_function

from app.models.processing import JobStatus, ProcessingJob

logger = logging.getLogger(__name__)


class CosmosPlugin:
    """Cosmos DB CRUD for processing jobs and analysis results."""

    def __init__(
        self,
        endpoint: str | None = None,
        database_name: str | None = None,
        jobs_container: str | None = None,
        results_container: str | None = None,
    ):
        self._endpoint = endpoint or os.getenv("COSMOS_ENDPOINT", "")
        self._db_name = database_name or os.getenv("COSMOS_DATABASE_NAME", "docprocessing")
        self._jobs_container_name = jobs_container or os.getenv("COSMOS_CONTAINER_JOBS", "jobs")
        self._results_container_name = results_container or os.getenv("COSMOS_CONTAINER_RESULTS", "results")

        credential = DefaultAzureCredential()
        self._client = CosmosClient(url=self._endpoint, credential=credential)
        self._db = self._client.get_database_client(self._db_name)
        self._jobs = self._db.get_container_client(self._jobs_container_name)
        self._results = self._db.get_container_client(self._results_container_name)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------
    @kernel_function(name="create_job", description="Create a new processing job record.")
    def create_job(self, job: Annotated[ProcessingJob, "ProcessingJob instance"]) -> dict[str, Any]:
        doc = job.model_dump(mode="json")
        self._jobs.create_item(body=doc)
        logger.info("Created job %s for %s", job.id, job.file_name)
        return doc

    @kernel_function(name="update_job", description="Replace/update an existing processing job.")
    def update_job(self, job: Annotated[ProcessingJob, "ProcessingJob instance"]) -> dict[str, Any]:
        job.touch()
        doc = job.model_dump(mode="json")
        self._jobs.replace_item(item=job.id, body=doc)
        logger.info("Updated job %s → %s", job.id, job.status.value)
        return doc

    @kernel_function(name="get_job", description="Retrieve a job by ID.")
    def get_job(self, job_id: Annotated[str, "Job ID"]) -> Optional[dict[str, Any]]:
        try:
            return self._jobs.read_item(item=job_id, partition_key=job_id)
        except CosmosResourceNotFoundError:
            return None

    @kernel_function(name="delete_job", description="Delete a job and its associated result.")
    def delete_job(self, job_id: Annotated[str, "Job ID"]) -> bool:
        """Delete a job from the jobs container and its result (if any) from results."""
        try:
            self._jobs.delete_item(item=job_id, partition_key=job_id)
            logger.info("Deleted job %s", job_id)
        except CosmosResourceNotFoundError:
            logger.warning("Job %s not found for deletion", job_id)
            return False
        # Best-effort delete of the associated result
        try:
            self._results.delete_item(item=job_id, partition_key=job_id)
            logger.info("Deleted result for job %s", job_id)
        except CosmosResourceNotFoundError:
            pass
        return True

    @kernel_function(name="list_jobs", description="List jobs with optional status filter.")
    def list_jobs(
        self,
        status_filter: Annotated[str, "Filter by status (queued/processing/completed/failed)"] = "",
        limit: Annotated[int, "Max results"] = 50,
    ) -> list[dict[str, Any]]:
        if status_filter:
            query = "SELECT * FROM c WHERE c.status = @status ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
            params = [{"name": "@status", "value": status_filter}, {"name": "@limit", "value": limit}]
        else:
            query = "SELECT * FROM c ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
            params = [{"name": "@limit", "value": limit}]

        return list(self._jobs.query_items(query=query, parameters=params, enable_cross_partition_query=True))

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    @kernel_function(name="save_result", description="Save an analysis result linked to a job.")
    def save_result(
        self,
        job_id: Annotated[str, "Related job ID"],
        result: Annotated[dict[str, Any], "DocumentAnalysisResult dict"],
    ) -> dict[str, Any]:
        doc = {**result, "id": job_id, "jobId": job_id}
        self._results.upsert_item(body=doc)
        logger.info("Saved result for job %s", job_id)
        return doc

    @kernel_function(name="get_result", description="Retrieve an analysis result by job ID.")
    def get_result(self, job_id: Annotated[str, "Job ID"]) -> Optional[dict[str, Any]]:
        try:
            return self._results.read_item(item=job_id, partition_key=job_id)
        except CosmosResourceNotFoundError:
            return None

    @kernel_function(name="list_results", description="List completed analysis results.")
    def list_results(
        self,
        limit: Annotated[int, "Max results"] = 50,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM c ORDER BY c.metadata.processing_timestamp DESC OFFSET 0 LIMIT @limit"
        params = [{"name": "@limit", "value": limit}]
        return list(self._results.query_items(query=query, parameters=params, enable_cross_partition_query=True))

    _ALLOWED_VECTOR_FIELDS = {"summary_vector", "purpose_vector"}
    _FILTER_ALLOWED_PATTERN = None  # compiled on first use

    @kernel_function(name="vector_search", description="Search results by vector similarity.")
    def vector_search(
        self,
        query_vector: Annotated[list[float], "Embedding vector for the search query"],
        vector_field: Annotated[str, "Vector field to search: summary_vector, purpose_vector"] = "summary_vector",
        top: Annotated[int, "Number of results"] = 10,
        filters: Annotated[str, "Optional WHERE clause fragment (e.g. \"c.doc_type = 'invoice'\")"] = "",
    ) -> list[dict[str, Any]]:
        """Execute a vector similarity search against the results container using VectorDistance."""
        if vector_field not in self._ALLOWED_VECTOR_FIELDS:
            raise ValueError(f"vector_field must be one of {self._ALLOWED_VECTOR_FIELDS}")

        # Validate filter to prevent injection — allow only simple field comparisons
        import re
        if self._FILTER_ALLOWED_PATTERN is None:
            CosmosPlugin._FILTER_ALLOWED_PATTERN = re.compile(
                r"^c\.[a-zA-Z_]+\s*=\s*'[^']*'$"
            )
        where_clause = ""
        if filters:
            if not self._FILTER_ALLOWED_PATTERN.match(filters.strip()):
                raise ValueError("Invalid filter format. Expected: c.field = 'value'")
            where_clause = f"AND {filters}"
        query = (
            f"SELECT TOP @top c.id, c.jobId, c.title, c.doc_type, c.summary, "
            f"c.key_fields.document_purpose AS document_purpose, "
            f"VectorDistance(c.{vector_field}, @queryVector) AS score "
            f"FROM c WHERE c.summary_vector != null {where_clause} "
            f"ORDER BY VectorDistance(c.{vector_field}, @queryVector)"
        )
        params = [
            {"name": "@top", "value": top},
            {"name": "@queryVector", "value": query_vector},
        ]
        return list(self._results.query_items(
            query=query, parameters=params, enable_cross_partition_query=True,
        ))

    @kernel_function(name="vector_search_chunks", description="Search within document chunks by vector similarity.")
    def vector_search_chunks(
        self,
        query_vector: Annotated[list[float], "Embedding vector for the search query"],
        top: Annotated[int, "Number of results"] = 10,
    ) -> list[dict[str, Any]]:
        """Search across chunk-level vectors for granular passage retrieval."""
        query = (
            "SELECT TOP @top c.id, c.jobId, c.title, c.doc_type, "
            "chunk.chunk_index, chunk.text AS chunk_text, "
            "VectorDistance(chunk.vector, @queryVector) AS score "
            "FROM c JOIN chunk IN c.chunks "
            "WHERE c.chunks != null "
            "ORDER BY VectorDistance(chunk.vector, @queryVector)"
        )
        params = [
            {"name": "@top", "value": top},
            {"name": "@queryVector", "value": query_vector},
        ]
        return list(self._results.query_items(
            query=query, parameters=params, enable_cross_partition_query=True,
        ))
