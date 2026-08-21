"""Persistent admin operations for long-running maintenance tasks."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from app.plugins.cosmos_plugin import CosmosPlugin
    from app.services.reprocessing import IngestReprocessService
    from app.services.search_backfill import SearchIndexBackfillService

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
RESULT_SAMPLE_LIMIT = 200
PROGRESS_UPDATE_MIN_SECONDS = 2.0
PROGRESS_UPDATE_MIN_ITEMS = 25


class AdminOperationService:
    """Runs long maintenance operations outside the request/response lifecycle."""

    def __init__(
        self,
        cosmos: "CosmosPlugin",
        search_backfill: "SearchIndexBackfillService",
        ingest_reprocess: "IngestReprocessService",
    ):
        self.cosmos = cosmos
        self.search_backfill = search_backfill
        self.ingest_reprocess = ingest_reprocess
        self._tasks: dict[str, asyncio.Task] = {}

    def mark_interrupted_operations(self) -> None:
        """Mark persisted running operations as failed after app restart/revision."""
        for operation in self.cosmos.list_incomplete_operations():
            operation["status"] = "failed"
            operation["completed_at"] = _utc_now()
            operation["updated_at"] = operation["completed_at"]
            operation["message"] = "Operation was interrupted by an app restart or revision. Start it again to continue."
            self.cosmos.replace_operation(operation)

    def start_search_backfill(
        self,
        *,
        limit: int,
        dry_run: bool,
        force: bool,
        include_chunks: bool,
        include_geocoding: bool,
    ) -> dict[str, Any]:
        request = {
            "limit": limit,
            "dry_run": dry_run,
            "force": force,
            "include_chunks": include_chunks,
            "include_geocoding": include_geocoding,
        }
        operation = self._create_operation("search_index_backfill", request)
        self._schedule(operation["id"], self._run_search_backfill(operation["id"], request))
        return operation

    def start_ingest_reprocess(
        self,
        *,
        limit: int,
        dry_run: bool,
        prefix: str,
        source_container: str,
        source_container_name: str,
    ) -> dict[str, Any]:
        request = {
            "limit": limit,
            "dry_run": dry_run,
            "prefix": prefix,
            "source_container": source_container,
            "source_container_name": source_container_name,
        }
        operation = self._create_operation("ingest_reprocess", request)
        self._schedule(operation["id"], self._run_ingest_reprocess(operation["id"], request))
        return operation

    def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        return self.cosmos.get_operation(operation_id)

    def list_recent_operations(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.cosmos.list_recent_operations(limit=limit)

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    def _create_operation(self, operation_type: str, request: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now()
        operation = {
            "id": str(uuid4()),
            "type": operation_type,
            "status": "queued",
            "request": request,
            "progress": {},
            "summary": {},
            "results": [],
            "results_truncated": False,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "message": "Operation queued.",
        }
        return self.cosmos.create_operation(operation)

    def _schedule(self, operation_id: str, coroutine: Awaitable[None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks[operation_id] = task
        task.add_done_callback(lambda completed: self._tasks.pop(operation_id, None))

    async def _run_search_backfill(self, operation_id: str, request: dict[str, Any]) -> None:
        await self._run_operation(
            operation_id=operation_id,
            operation=lambda callback: asyncio.to_thread(
                self.search_backfill.backfill_batch,
                limit=int(request["limit"]),
                dry_run=bool(request["dry_run"]),
                force=bool(request["force"]),
                include_chunks=bool(request["include_chunks"]),
                include_geocoding=bool(request["include_geocoding"]),
                max_results=RESULT_SAMPLE_LIMIT,
                progress_callback=callback,
            ),
        )

    async def _run_ingest_reprocess(self, operation_id: str, request: dict[str, Any]) -> None:
        await self._run_operation(
            operation_id=operation_id,
            operation=lambda callback: self.ingest_reprocess.requeue_ingest_batch(
                limit=int(request["limit"]),
                dry_run=bool(request["dry_run"]),
                prefix=str(request["prefix"]),
                source_container=str(request["source_container_name"]),
                max_results=RESULT_SAMPLE_LIMIT,
                progress_callback=callback,
            ),
        )

    async def _run_operation(
        self,
        operation_id: str,
        operation: Callable[[Callable[[dict[str, Any]], None]], Awaitable[dict[str, Any]]],
    ) -> None:
        tracker = _ProgressTracker(self.cosmos, operation_id)
        try:
            self._update_operation(
                operation_id,
                {
                    "status": "running",
                    "started_at": _utc_now(),
                    "message": "Operation running.",
                },
            )
            result = await operation(tracker.update)
            self._complete_operation(operation_id, result)
        except asyncio.CancelledError:
            self._update_operation(
                operation_id,
                {
                    "status": "cancelled",
                    "completed_at": _utc_now(),
                    "message": "Operation was cancelled.",
                },
            )
            raise
        except Exception:
            logger.exception("Admin operation %s failed", operation_id)
            self._update_operation(
                operation_id,
                {
                    "status": "failed",
                    "completed_at": _utc_now(),
                    "message": "Operation failed. Check application logs for details.",
                },
            )

    def _complete_operation(self, operation_id: str, result: dict[str, Any]) -> None:
        summary = {key: value for key, value in result.items() if key != "results"}
        self._update_operation(
            operation_id,
            {
                "status": "completed",
                "completed_at": _utc_now(),
                "summary": summary,
                "progress": _summary_to_progress(summary),
                "results": result.get("results", [])[:RESULT_SAMPLE_LIMIT],
                "results_truncated": bool(result.get("results_truncated")),
                "message": str(result.get("message") or "Operation completed."),
            },
        )

    def _update_operation(self, operation_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        operation = self.cosmos.get_operation(operation_id)
        if operation is None:
            logger.warning("Admin operation %s disappeared before it could be updated", operation_id)
            return None
        operation.update(updates)
        operation["updated_at"] = _utc_now()
        return self.cosmos.replace_operation(operation)


class _ProgressTracker:
    def __init__(self, cosmos: "CosmosPlugin", operation_id: str):
        self.cosmos = cosmos
        self.operation_id = operation_id
        self._last_update_time = 0.0
        self._last_processed = 0

    def update(self, progress: dict[str, Any]) -> None:
        processed = int(progress.get("processed") or progress.get("scanned") or 0)
        now = time.monotonic()
        if (
            processed - self._last_processed < PROGRESS_UPDATE_MIN_ITEMS
            and now - self._last_update_time < PROGRESS_UPDATE_MIN_SECONDS
        ):
            return

        operation = self.cosmos.get_operation(self.operation_id)
        if operation is None or operation.get("status") in TERMINAL_STATUSES:
            return

        operation["progress"] = progress
        operation["updated_at"] = _utc_now()
        self.cosmos.replace_operation(operation)
        self._last_processed = processed
        self._last_update_time = now


def _summary_to_progress(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "processed",
        "scanned",
        "candidate_documents_scanned",
        "blobs_scanned",
        "updated",
        "would_update",
        "enqueued",
        "would_enqueue",
        "skipped",
        "skipped_active",
        "failed",
        "generated_embeddings",
        "geocoded_locations_added",
        "unsupported_type_count",
    )
    return {key: summary[key] for key in keys if key in summary}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
