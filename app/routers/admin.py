"""Administrative maintenance APIs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SearchBackfillRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, description="Maximum documents to scan in this batch.")
    dry_run: bool = Field(default=True, description="Preview updates without writing to Cosmos DB.")
    force: bool = Field(default=False, description="Regenerate even when metadata appears current.")
    include_chunks: bool = Field(default=True, description="Refresh chunk vectors when chunk text exists.")
    include_geocoding: bool = Field(default=True, description="Backfill missing Azure Maps lat/lon results first.")


class SingleSearchBackfillRequest(BaseModel):
    dry_run: bool = Field(default=True, description="Preview updates without writing to Cosmos DB.")
    force: bool = Field(default=False, description="Regenerate even when metadata appears current.")
    include_chunks: bool = Field(default=True, description="Refresh chunk vectors when chunk text exists.")
    include_geocoding: bool = Field(default=True, description="Backfill missing Azure Maps lat/lon results first.")


class IngestReprocessRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, description="Maximum source blobs to scan in this batch.")
    dry_run: bool = Field(default=True, description="Preview jobs without writing to Cosmos DB or enqueueing.")
    prefix: str = Field(default="", description="Optional blob-name prefix to limit the scan.")
    source_container: Literal["ingest", "failed"] = Field(
        default="ingest",
        description="Source container to scan for requeue candidates.",
    )


def _resolve_backfill_limit(limit: int | None) -> int:
    resolved = settings.backfill_default_limit if limit is None else limit
    if resolved > settings.backfill_max_limit:
        raise HTTPException(status_code=400, detail=f"limit cannot exceed {settings.backfill_max_limit}")
    return resolved


def _resolve_reprocess_limit(limit: int | None) -> int:
    resolved = settings.reprocess_default_limit if limit is None else limit
    if resolved > settings.reprocess_max_limit:
        raise HTTPException(status_code=400, detail=f"limit cannot exceed {settings.reprocess_max_limit}")
    return resolved


def _resolve_reprocess_source_container(source_container: Literal["ingest", "failed"]) -> str:
    return {
        "ingest": settings.storage_container_ingest,
        "failed": settings.storage_container_failed,
    }[source_container]


@router.get("/settings")
async def get_admin_settings():
    """Return admin UI limits backed by current app settings."""
    return {
        "backfill_default_limit": settings.backfill_default_limit,
        "backfill_max_limit": settings.backfill_max_limit,
        "reprocess_default_limit": settings.reprocess_default_limit,
        "reprocess_max_limit": settings.reprocess_max_limit,
        "containers": {
            "ingest": settings.storage_container_ingest,
            "failed": settings.storage_container_failed,
        },
    }


@router.post("/search-index/backfill")
async def backfill_search_index(request: Request, body: SearchBackfillRequest):
    """Backfill materialized search text and current embedding metadata for existing results."""
    service = request.app.state.search_backfill
    return service.backfill_batch(
        limit=_resolve_backfill_limit(body.limit),
        dry_run=body.dry_run,
        force=body.force,
        include_chunks=body.include_chunks,
        include_geocoding=body.include_geocoding,
    )


@router.post("/search-index/backfill/start", status_code=202)
async def start_backfill_search_index(request: Request, body: SearchBackfillRequest):
    """Start a persistent search-index backfill operation and return immediately."""
    service = request.app.state.admin_operations
    return service.start_search_backfill(
        limit=_resolve_backfill_limit(body.limit),
        dry_run=body.dry_run,
        force=body.force,
        include_chunks=body.include_chunks,
        include_geocoding=body.include_geocoding,
    )


@router.post("/search-index/backfill/{job_id}")
async def backfill_search_index_result(request: Request, job_id: str, body: SingleSearchBackfillRequest):
    """Backfill one result document by job ID."""
    service = request.app.state.search_backfill
    result = service.backfill_one(
        job_id=job_id,
        dry_run=body.dry_run,
        force=body.force,
        include_chunks=body.include_chunks,
        include_geocoding=body.include_geocoding,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/ingest/reprocess")
async def reprocess_ingest_blobs(request: Request, body: IngestReprocessRequest):
    """Dry-run or enqueue existing blobs from ingest or failed."""
    service = request.app.state.ingest_reprocess
    return await service.requeue_ingest_batch(
        limit=_resolve_reprocess_limit(body.limit),
        dry_run=body.dry_run,
        prefix=body.prefix,
        source_container=_resolve_reprocess_source_container(body.source_container),
    )


@router.post("/ingest/reprocess/start", status_code=202)
async def start_reprocess_ingest_blobs(request: Request, body: IngestReprocessRequest):
    """Start a persistent ingest/failed requeue operation and return immediately."""
    service = request.app.state.admin_operations
    return service.start_ingest_reprocess(
        limit=_resolve_reprocess_limit(body.limit),
        dry_run=body.dry_run,
        prefix=body.prefix,
        source_container=body.source_container,
        source_container_name=_resolve_reprocess_source_container(body.source_container),
    )


@router.get("/operations")
async def list_admin_operations(request: Request, limit: int = 20):
    """List recent admin maintenance operations."""
    service = request.app.state.admin_operations
    return {"operations": service.list_recent_operations(limit=limit)}


@router.get("/operations/{operation_id}")
async def get_admin_operation(request: Request, operation_id: str):
    """Get current status for an admin maintenance operation."""
    service = request.app.state.admin_operations
    operation = service.get_operation(operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="Operation not found")
    return operation
