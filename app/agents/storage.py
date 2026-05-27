"""Storage agent — wraps BlobPlugin + CosmosPlugin for blob lifecycle and persistence."""

from __future__ import annotations

import logging

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent

from app.plugins.blob_plugin import BlobPlugin
from app.plugins.cosmos_plugin import CosmosPlugin

logger = logging.getLogger(__name__)

STORAGE_INSTRUCTIONS = """\
You are a Storage Agent. Your job is to manage document lifecycle in Azure
Blob Storage and persist processing state / results in Cosmos DB.

Capabilities:
1. Move blobs between containers (ingest → processing → originaldocument).
2. Upload analysis result JSON to the completed container.
3. Create and update processing job records in Cosmos DB.
4. Save final DocumentAnalysisResult to Cosmos DB results container.
5. Generate user-delegation SAS URLs for original document access.
6. List blobs in any container.
"""


def create_storage_agent(kernel: Kernel) -> ChatCompletionAgent:
    """Create and return the storage agent with Blob + Cosmos plugins."""
    kernel.add_plugin(BlobPlugin(), plugin_name="Blob")
    kernel.add_plugin(CosmosPlugin(), plugin_name="Cosmos")

    return ChatCompletionAgent(
        kernel=kernel,
        name="StorageAgent",
        instructions=STORAGE_INSTRUCTIONS,
    )
