"""Processing status API — list, detail, retry."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.processing import JobStatus, ProcessingJob, ProcessingStep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("")
async def list_jobs(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
):
    """List processing jobs with optional status filter."""
    cosmos = request.app.state.cosmos
    jobs = cosmos.list_jobs(status_filter=status or "", limit=limit)
    return {
        "count": len(jobs),
        "jobs": jobs,
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
    job.status = JobStatus.QUEUED
    job.error_message = None
    job.steps = [
        ProcessingStep(name="move_to_processing"),
        ProcessingStep(name="document_extraction"),
        ProcessingStep(name="llm_analysis"),
        ProcessingStep(name="save_results"),
        ProcessingStep(name="move_original"),
    ]
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
