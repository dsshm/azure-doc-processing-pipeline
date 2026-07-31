"""Processing job and step tracking models."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProcessingStep(BaseModel):
    name: str
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def start(self) -> None:
        self.status = StepStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def complete(self) -> None:
        self.status = StepStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)

    def fail(self, error: str) -> None:
        self.status = StepStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error = error


class ProcessingJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    file_name: str
    blob_url: str
    container: str = ""
    blob_name: str = ""
    status: JobStatus = JobStatus.QUEUED
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    steps: list[ProcessingStep] = Field(default_factory=lambda: [
        ProcessingStep(name="move_to_processing"),
        ProcessingStep(name="document_extraction"),
        ProcessingStep(name="llm_analysis"),
        ProcessingStep(name="geocode_locations"),
        ProcessingStep(name="build_search_index"),
        ProcessingStep(name="save_results"),
        ProcessingStep(name="move_original"),
    ])

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def fail(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error_message = error
        self.touch()

    def complete(self) -> None:
        self.status = JobStatus.COMPLETED
        self.touch()

    def get_step(self, name: str) -> ProcessingStep:
        step = next((s for s in self.steps if s.name == name), None)
        if step:
            return step
        step = ProcessingStep(name=name)
        self.steps.append(step)
        return step
