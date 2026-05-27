"""Document extraction agent — wraps DocIntelPlugin for SK agent use."""

from __future__ import annotations

import logging
import os
from typing import Any

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from app.plugins.doc_intel_plugin import DocIntelPlugin

logger = logging.getLogger(__name__)

EXTRACTION_INSTRUCTIONS = """\
You are a Document Extraction Agent. Your job is to extract structured content
from documents using Azure Document Intelligence.

When asked to process a document:
1. Use the analyze_document tool with the provided document bytes.
2. Select the appropriate model_id based on file type:
   - PDF, DOCX, PPTX, XLSX → "prebuilt-layout"
   - Images (JPG, PNG, TIFF, BMP, GIF) → "prebuilt-layout"
3. Return the complete extraction results including pages, tables, and barcodes.
4. If extraction fails, report the error clearly.
"""


def create_extraction_agent(kernel: Kernel) -> ChatCompletionAgent:
    """Create and return the extraction agent with DocIntel plugin."""
    kernel.add_plugin(DocIntelPlugin(), plugin_name="DocIntel")

    return ChatCompletionAgent(
        kernel=kernel,
        name="ExtractionAgent",
        instructions=EXTRACTION_INSTRUCTIONS,
    )
