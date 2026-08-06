"""Orchestrator that drives the document processing pipeline.

Uses SK plugins directly in a deterministic sequence rather than
chat-based agent negotiation — the pipeline steps are fixed:

  1. Move blob from INGEST → PROCESSING
  2. Download & extract via Document Intelligence
  3. Per-page LLM analysis → consolidated result
  4. Enrich extracted locations with Azure Maps fuzzy search
  5. Build full-text search content and vector embeddings
  6. Save result JSON to COMPLETED container + Cosmos DB
  7. Move original from PROCESSING → ORIGINALDOCUMENT
  8. On failure, move the source blob from INGEST/PROCESSING → FAILED
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from azure.core.exceptions import AzureError

from app.config import settings
from app.models.processing import JobStatus, ProcessingJob
from app.plugins.blob_plugin import BlobPlugin
from app.plugins.cosmos_plugin import CosmosPlugin
from app.plugins.doc_intel_plugin import DocIntelPlugin
from app.plugins.llm_plugin import LLMPlugin
from app.plugins.maps_plugin import AzureMapsPlugin
from app.services.geocoding import apply_geocoding
from app.services.search_indexing import apply_search_index

logger = logging.getLogger(__name__)

# Supported file extensions
IMG_TYPES = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".gif"}
DOC_TYPES = {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".txt"}
SUPPORTED_TYPES = IMG_TYPES | DOC_TYPES


class PipelineOrchestrator:
    """Deterministic pipeline that processes a single document end-to-end."""

    def __init__(
        self,
        blob: BlobPlugin | None = None,
        cosmos: CosmosPlugin | None = None,
        doc_intel: DocIntelPlugin | None = None,
        llm: LLMPlugin | None = None,
        maps: AzureMapsPlugin | None = None,
    ):
        self.blob = blob or BlobPlugin()
        self.cosmos = cosmos or CosmosPlugin()
        self.doc_intel = doc_intel or DocIntelPlugin()
        self.llm = llm or LLMPlugin()
        self.maps = maps or AzureMapsPlugin()

    async def process(self, job: ProcessingJob) -> ProcessingJob:
        """Run the full pipeline for *job*.  Updates Cosmos DB along the way."""
        try:
            job.status = JobStatus.PROCESSING
            self.cosmos.update_job(job)

            # --- Step 1: move to PROCESSING ---
            step = job.get_step("move_to_processing")
            step.start()
            if self.blob.blob_exists(
                container=settings.storage_container_processing,
                blob_name=job.blob_name,
            ):
                logger.info("Blob already in processing container (retry), skipping move")
            else:
                source_container = job.container or settings.storage_container_ingest
                self.blob.move_blob(
                    source_container=source_container,
                    dest_container=settings.storage_container_processing,
                    blob_name=job.blob_name,
                )
                job.container = settings.storage_container_processing
                job.blob_url = self.blob.get_blob_url(
                    container=settings.storage_container_processing,
                    blob_name=job.blob_name,
                )
            step.complete()
            self.cosmos.update_job(job)

            # --- Step 2: extract with Document Intelligence ---
            step = job.get_step("document_extraction")
            step.start()
            file_data = self.blob.download_blob(
                container=settings.storage_container_processing,
                blob_name=job.blob_name,
            )
            if not file_data:
                raise ValueError("Downloaded file is empty")

            ext = os.path.splitext(job.file_name)[1].lower()
            if ext not in SUPPORTED_TYPES:
                raise ValueError(f"Unsupported file type: {ext}")

            extraction = self.doc_intel.analyze_document(
                document_data=file_data,
                model_id="prebuilt-layout",
            )
            step.complete()
            self.cosmos.update_job(job)

            # --- Step 3: LLM analysis ---
            step = job.get_step("llm_analysis")
            step.start()
            pages = extraction.get("pages", [])
            if not pages and extraction.get("content"):
                pages = [{"page_number": 1, "content": extraction["content"]}]

            page_analyses: list[dict[str, Any]] = []
            for page in pages:
                content = page.get("content", "")
                if not content:
                    continue
                analysis = self.llm.analyze_page(
                    page_content=content,
                    page_number=page.get("page_number", 1),
                    total_pages=len(pages),
                )
                page_analyses.append(analysis)

            consolidated = self.llm.consolidate_analyses(
                page_results=page_analyses,
                file_name=job.file_name,
            )

            step.complete()
            self.cosmos.update_job(job)

            # --- Step 4: location geocoding ---
            step = job.get_step("geocode_locations")
            step.start()
            consolidated = apply_geocoding(consolidated, self.maps).document
            step.complete()
            self.cosmos.update_job(job)

            # --- Step 5: build search text + vector embeddings ---
            step = job.get_step("build_search_index")
            step.start()
            consolidated = apply_search_index(
                document=consolidated,
                llm=self.llm,
                pages=pages,
                fail_fast=False,
            ).document
            step.complete()
            self.cosmos.update_job(job)

            # --- Step 6: save results ---
            step = job.get_step("save_results")
            step.start()

            result_json = json.dumps(consolidated, default=str).encode("utf-8")
            result_blob_name = f"{job.id}/{job.file_name}.json"
            self.blob.upload_blob(
                container=settings.storage_container_completed,
                blob_name=result_blob_name,
                data=result_json,
                content_type="application/json",
            )
            self.cosmos.save_result(job_id=job.id, result=consolidated)
            step.complete()
            self.cosmos.update_job(job)

            # --- Step 7: move original to ORIGINALDOCUMENT ---
            step = job.get_step("move_original")
            step.start()
            self.blob.move_blob(
                source_container=settings.storage_container_processing,
                dest_container=settings.storage_container_original,
                blob_name=job.blob_name,
            )
            job.container = settings.storage_container_original
            job.blob_url = self.blob.get_blob_url(
                container=settings.storage_container_original,
                blob_name=job.blob_name,
            )
            step.complete()

            job.complete()
            self.cosmos.update_job(job)
            logger.info("Pipeline completed for job %s (%s)", job.id, job.file_name)
            return job

        except Exception as exc:
            logger.exception("Pipeline failed for job %s: %s", job.id, exc)
            # Mark whichever step was running as failed
            for s in job.steps:
                if s.status.value == "running":
                    s.fail(str(exc))
            job.fail(str(exc))
            self._move_failed_blob(job)
            try:
                self.cosmos.update_job(job)
            except Exception:
                logger.error("Failed to persist job failure state for %s", job.id)
            return job

    def _move_failed_blob(self, job: ProcessingJob) -> None:
        step = job.get_step("move_to_failed")
        step.start()

        try:
            if self.blob.blob_exists(settings.storage_container_processing, job.blob_name):
                source_container = settings.storage_container_processing
            elif self.blob.blob_exists(settings.storage_container_ingest, job.blob_name):
                source_container = settings.storage_container_ingest
            elif self.blob.blob_exists(settings.storage_container_failed, job.blob_name):
                message = "Blob is already in the failed container."
                logger.info("%s job=%s blob=%s", message, job.id, job.blob_name)
                job.container = settings.storage_container_failed
                job.blob_url = self.blob.get_blob_url(
                    container=settings.storage_container_failed,
                    blob_name=job.blob_name,
                )
                step.skip(message)
                return
            else:
                message = (
                    "Blob was not found in processing, ingest, or failed during failure cleanup; "
                    "it may already have been archived or manually moved."
                )
                logger.warning("%s job=%s blob=%s", message, job.id, job.blob_name)
                step.skip(message)
                return

            self.blob.move_blob(
                source_container=source_container,
                dest_container=settings.storage_container_failed,
                blob_name=job.blob_name,
            )
            job.container = settings.storage_container_failed
            job.blob_url = self.blob.get_blob_url(
                container=settings.storage_container_failed,
                blob_name=job.blob_name,
            )
            step.complete()
        except (AzureError, ValueError) as move_exc:
            logger.exception("Failed to move blob to failed container for job %s", job.id)
            step.fail(str(move_exc))
