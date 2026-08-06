"""Application service for requeueing blobs that remain in operator-selected source containers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from app.agents.planner import SUPPORTED_TYPES
from app.config import settings
from app.models.processing import ProcessingJob

if TYPE_CHECKING:
    from app.plugins.blob_plugin import BlobPlugin
    from app.plugins.cosmos_plugin import CosmosPlugin
    from app.services.processing import ProcessingWorker


class IngestReprocessService:
    """Requeue existing blobs when Event Grid missed events or files are parked in failed."""

    def __init__(self, blob: "BlobPlugin", cosmos: "CosmosPlugin", worker: "ProcessingWorker"):
        self.blob = blob
        self.cosmos = cosmos
        self.worker = worker

    async def requeue_ingest_batch(
        self,
        limit: int,
        dry_run: bool = True,
        prefix: str = "",
        source_container: str | None = None,
    ) -> dict[str, Any]:
        resolved_source_container = source_container or settings.storage_container_ingest
        blob_names = self.blob.list_blobs(
            container=resolved_source_container,
            prefix=prefix,
            limit=limit,
        )

        results: list[dict[str, Any]] = []
        enqueued = 0
        would_enqueue = 0
        skipped_active = 0
        unsupported_type_count = 0

        for blob_name in blob_names:
            file_name = blob_name.rsplit("/", 1)[-1] if "/" in blob_name else blob_name
            extension = os.path.splitext(file_name)[1].lower()
            supported_type = extension in SUPPORTED_TYPES
            if not supported_type:
                unsupported_type_count += 1

            active_job = self.cosmos.find_active_job_by_blob_name(blob_name)
            if active_job:
                skipped_active += 1
                results.append(
                    {
                        "blob_name": blob_name,
                        "file_name": file_name,
                        "source_container": resolved_source_container,
                        "status": "skipped_active_job",
                        "active_job_id": active_job.get("id"),
                    }
                )
                continue

            if dry_run:
                would_enqueue += 1
                results.append(
                    {
                        "blob_name": blob_name,
                        "file_name": file_name,
                        "source_container": resolved_source_container,
                        "status": "would_enqueue" if supported_type else "would_enqueue_unsupported_type",
                        "supported_type": supported_type,
                    }
                )
                continue

            job = ProcessingJob(
                file_name=file_name,
                blob_url=self.blob.get_blob_url(
                    container=resolved_source_container,
                    blob_name=blob_name,
                ),
                container=resolved_source_container,
                blob_name=blob_name,
            )
            self.cosmos.create_job(job)
            await self.worker.enqueue(job)
            enqueued += 1
            results.append(
                {
                    "blob_name": blob_name,
                    "file_name": file_name,
                    "source_container": resolved_source_container,
                    "status": "enqueued" if supported_type else "enqueued_unsupported_type",
                    "supported_type": supported_type,
                    "job_id": job.id,
                }
            )

        return {
            "dry_run": dry_run,
            "limit": limit,
            "prefix": prefix,
            "source_container": resolved_source_container,
            "ingest_container": settings.storage_container_ingest,
            "failed_container": settings.storage_container_failed,
            "blobs_scanned": len(blob_names),
            "would_enqueue": would_enqueue,
            "enqueued": enqueued,
            "skipped_active": skipped_active,
            "unsupported_type_count": unsupported_type_count,
            "message": (
                "Dry run only. Unsupported extensions are still queued on execute so the pipeline can move them to failed."
                if dry_run
                else f"Queued {resolved_source_container} blobs for processing. Run again until blobs_scanned is 0 for the selected prefix."
            ),
            "results": results,
        }
