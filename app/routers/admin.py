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
