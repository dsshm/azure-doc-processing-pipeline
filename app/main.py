"""FastAPI application entry point.

- Lifespan: initialises Azure clients via DefaultAzureCredential,
  starts the background processing worker.
- Mounts static files for the status dashboard.
- Includes API routers: events, status, documents.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.plugins.blob_plugin import BlobPlugin
from app.plugins.cosmos_plugin import CosmosPlugin
from app.plugins.llm_plugin import LLMPlugin
from app.agents.planner import PipelineOrchestrator
from app.services.processing import ProcessingWorker
from app.routers import events, status, documents, search

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Initialising services…")

    # Shared plugin instances (managed identity auth)
    blob = BlobPlugin()
    cosmos = CosmosPlugin()
    llm = LLMPlugin()
    orchestrator = PipelineOrchestrator(blob=blob, cosmos=cosmos, llm=llm)
    worker = ProcessingWorker(orchestrator=orchestrator)

    # Attach to app state so routers can access them
    app.state.blob = blob
    app.state.cosmos = cosmos
    app.state.llm = llm
    app.state.worker = worker

    # Start background worker
    worker_task = asyncio.create_task(worker.start())

    logger.info("Application ready")
    yield

    # Shutdown
    logger.info("Shutting down…")
    await worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Document Intelligence Pipeline",
    description="Container-based document processing with Semantic Kernel orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Static web dashboard ---
static_dir = Path(__file__).parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

# --- API routers ---
app.include_router(events.router)
app.include_router(status.router)
app.include_router(documents.router)
app.include_router(search.router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Redirect to the dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")
