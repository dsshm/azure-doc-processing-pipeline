"""Event Grid webhook endpoint.

Handles:
  - Event Grid subscription validation handshake
  - Microsoft.Storage.BlobCreated events for the INGEST container
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.models.processing import ProcessingJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/blob")
async def handle_blob_event(request: Request) -> Response:
    """Receive Event Grid events for new blobs in the INGEST container."""
    body: list[dict[str, Any]] | dict[str, Any] = await request.json()

    # Event Grid sends an array; CloudEvents schema sends a single object
    events = body if isinstance(body, list) else [body]

    for event in events:
        event_type = event.get("eventType", "")

        # --- Subscription validation handshake ---
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            validation_code = event.get("data", {}).get("validationCode", "")
            logger.info("Event Grid validation handshake (code=%s)", validation_code)
            return Response(
                content=f'{{"validationResponse": "{validation_code}"}}',
                media_type="application/json",
                status_code=200,
            )

        # --- Blob created ---
        if event_type == "Microsoft.Storage.BlobCreated":
            await _handle_blob_created(event, request)

    return Response(status_code=200)


async def _handle_blob_created(event: dict[str, Any], request: Request) -> None:
    data = event.get("data", {})
    blob_url: str = data.get("url", "")

    if not blob_url:
        logger.warning("BlobCreated event with no URL — skipping")
        return

    # Only process blobs in the INGEST container
    parsed = urlparse(blob_url)
    path_parts = parsed.path.strip("/").split("/", 1)
    if len(path_parts) < 2:
        logger.warning("Cannot parse container/blob from URL: %s", blob_url)
        return

    container = path_parts[0]
    blob_name = path_parts[1]

    if container != settings.storage_container_ingest:
        logger.debug("Ignoring blob in container '%s' (not ingest)", container)
        return

    file_name = blob_name.rsplit("/", 1)[-1] if "/" in blob_name else blob_name

    job = ProcessingJob(
        file_name=file_name,
        blob_url=blob_url,
        container=container,
        blob_name=blob_name,
    )

    # Persist to Cosmos + enqueue
    worker = request.app.state.worker
    cosmos = request.app.state.cosmos
    cosmos.create_job(job)
    await worker.enqueue(job)

    logger.info("Enqueued job %s for blob %s", job.id, blob_name)
