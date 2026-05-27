"""Document query API — list completed results, get single, get original doc SAS URL."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
async def list_documents(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
):
    """List completed analysis results from Cosmos DB."""
    cosmos = request.app.state.cosmos
    results = cosmos.list_results(limit=limit)
    return {"count": len(results), "documents": results}


@router.get("/{job_id}")
async def get_document(request: Request, job_id: str):
    """Get a single analysis result."""
    cosmos = request.app.state.cosmos
    result = cosmos.get_result(job_id=job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document result not found")
    return result


@router.get("/{job_id}/original")
async def get_original_document(request: Request, job_id: str):
    """Redirect to a time-limited user-delegation SAS URL for the original document."""
    cosmos = request.app.state.cosmos

    # Look up the job to find the blob name
    job = cosmos.get_job(job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    blob_name = job.get("blob_name", "")
    if not blob_name:
        raise HTTPException(status_code=404, detail="Original blob name not recorded")

    blob_plugin: object = request.app.state.blob
    sas_url = blob_plugin.generate_user_delegation_sas(
        container=settings.storage_container_original,
        blob_name=blob_name,
    )
    return RedirectResponse(url=sas_url, status_code=302)
