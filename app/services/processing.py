"""Async background processing worker.

Consumes jobs from an asyncio queue and runs the pipeline orchestrator.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.agents.planner import PipelineOrchestrator
from app.config import settings
from app.models.processing import ProcessingJob

logger = logging.getLogger(__name__)


class ProcessingWorker:
    """Background worker that pulls from an asyncio.Queue and processes documents."""

    def __init__(self, orchestrator: PipelineOrchestrator | None = None, max_concurrent: int | None = None):
        self._queue: asyncio.Queue[ProcessingJob] = asyncio.Queue()
        self._orchestrator = orchestrator or PipelineOrchestrator()
        self._max_concurrent = max_concurrent or settings.max_concurrent_jobs
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._tasks: set[asyncio.Task] = set()
        self._running = False

    async def enqueue(self, job: ProcessingJob) -> None:
        """Add a job to the processing queue."""
        await self._queue.put(job)
        logger.info("Enqueued job %s (%s). Queue depth: %d", job.id, job.file_name, self._queue.qsize())

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        logger.info("Processing worker started (max_concurrent=%d)", self._max_concurrent)
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            await self._semaphore.acquire()
            task = asyncio.create_task(self._run_job(job))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        """Signal the worker to stop and wait for in-flight jobs."""
        self._running = False
        if self._tasks:
            logger.info("Waiting for %d in-flight jobs…", len(self._tasks))
            await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("Processing worker stopped")

    async def _run_job(self, job: ProcessingJob) -> None:
        try:
            await self._orchestrator.process(job)
        except Exception:
            logger.exception("Unhandled error processing job %s", job.id)
        finally:
            self._semaphore.release()
            self._queue.task_done()

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def active_jobs(self) -> int:
        return self._max_concurrent - self._semaphore._value
