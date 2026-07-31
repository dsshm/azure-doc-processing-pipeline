"""Administrative maintenance APIs."""

from __future__ import annotations

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


def _resolve_backfill_limit(limit: int | None) -> int:
    resolved = settings.backfill_default_limit if limit is None else limit
    if resolved > settings.backfill_max_limit:
        raise HTTPException(status_code=400, detail=f"limit cannot exceed {settings.backfill_max_limit}")
    return resolved


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
