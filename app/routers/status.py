"""Processing status API — list, detail, retry."""

from __future__ import annotations

import logging
from typing import Optional

from azure.core.exceptions import AzureError
from fastapi import APIRouter, HTTPException, Query, Request

from app.config import settings
from app.models.processing import JobStatus, ProcessingJob, default_processing_steps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("")
async def list_jobs(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    continuation_token: Optional[str] = Query(None, description="Opaque page cursor from a previous response"),
):
    """List one page of processing jobs with optional status filter."""
    cosmos = request.app.state.cosmos
    try:
        page = cosmos.list_jobs_page(
            status_filter=status or "",
            limit=limit,
            continuation_token=continuation_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    jobs = page["jobs"]
    next_token = page["continuation_token"]
    return {
        "count": len(jobs),
        "page_count": len(jobs),
        "jobs": jobs,
        "continuation_token": next_token,
        "has_more": bool(next_token),
        "queue_depth": request.app.state.worker.queue_depth,
        "active_jobs": request.app.state.worker.active_jobs,
    }


@router.get("/summary")
async def get_status_summary(request: Request):
    """Get total job counts without loading job documents."""
    cosmos = request.app.state.cosmos
    status_counts = cosmos.count_jobs_by_status()
    total_count = cosmos.count_jobs()
    result_documents_count = cosmos.count_results()
    return {
        "total_count": total_count,
        "result_documents_count": result_documents_count,
        "status_counts": status_counts,
        "queue_depth": request.app.state.worker.queue_depth,
        "active_jobs": request.app.state.worker.active_jobs,
    }


@router.get("/{job_id}")
async def get_job(request: Request, job_id: str):
    """Get a single job with step details."""
    cosmos = request.app.state.cosmos
    job = cosmos.get_job(job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/retry")
async def retry_job(request: Request, job_id: str):
    """Re-queue a failed job for processing."""
    cosmos = request.app.state.cosmos
    raw = cosmos.get_job(job_id=job_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Job not found")

    if raw.get("status") != JobStatus.FAILED.value:
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    # Rebuild job and reset
    job = ProcessingJob(**{k: v for k, v in raw.items() if k in ProcessingJob.model_fields})
    blob = request.app.state.blob
    try:
        if blob.blob_exists(settings.storage_container_failed, job.blob_name):
            blob.move_blob(
                source_container=settings.storage_container_failed,
                dest_container=settings.storage_container_processing,
                blob_name=job.blob_name,
            )
            job.container = settings.storage_container_processing
            job.blob_url = blob.get_blob_url(
                container=settings.storage_container_processing,
                blob_name=job.blob_name,
            )
        elif blob.blob_exists(settings.storage_container_processing, job.blob_name):
            job.container = settings.storage_container_processing
            job.blob_url = blob.get_blob_url(
                container=settings.storage_container_processing,
                blob_name=job.blob_name,
            )
        elif blob.blob_exists(settings.storage_container_ingest, job.blob_name):
            job.container = settings.storage_container_ingest
            job.blob_url = blob.get_blob_url(
                container=settings.storage_container_ingest,
                blob_name=job.blob_name,
            )
        else:
            raise HTTPException(
                status_code=409,
                detail="Original blob was not found in failed, processing, or ingest containers",
            )
    except AzureError as exc:
        logger.exception("Retry failed while preparing blob for job %s", job.id)
        raise HTTPException(status_code=502, detail=f"Failed to prepare blob for retry: {exc}") from exc

    job.status = JobStatus.QUEUED
    job.error_message = None
    job.steps = default_processing_steps()
    cosmos.update_job(job)

    worker = request.app.state.worker
    await worker.enqueue(job)

    return {"message": "Job re-queued", "job_id": job.id}


@router.delete("/{job_id}")
async def delete_job(request: Request, job_id: str):
    """Delete a job and its associated analysis result."""
    cosmos = request.app.state.cosmos
    raw = cosmos.get_job(job_id=job_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Job not found")

    status = raw.get("status")
    if status == JobStatus.PROCESSING.value:
        raise HTTPException(status_code=400, detail="Cannot delete a job that is currently processing")

    cosmos.delete_job(job_id=job_id)
    return {"message": "Job deleted", "job_id": job_id}
