"""Semantic Kernel plugin wrapping Azure Document Intelligence.

Ported from bp_docIntel.py – AzDocIntel class.
Auth: DefaultAzureCredential only (managed identity).
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature
from azure.identity import DefaultAzureCredential
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)


class DocIntelPlugin:
    """Azure AI Document Intelligence operations exposed as SK functions."""

    def __init__(self, endpoint: str | None = None):
        credential = DefaultAzureCredential()
        self._endpoint = endpoint or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
        self.client = DocumentIntelligenceClient(
            endpoint=self._endpoint,
            credential=credential,
        )

    # ------------------------------------------------------------------
    @kernel_function(
        name="analyze_document",
        description="Analyze a document with Azure Document Intelligence and return structured extraction (pages, tables, barcodes).",
    )
    def analyze_document(
        self,
        document_data: Annotated[bytes, "Raw document bytes"],
        model_id: Annotated[str, "Doc Intelligence model ID"] = "prebuilt-layout",
    ) -> dict[str, Any]:
        poller = self.client.begin_analyze_document(
            model_id=model_id,
            body=document_data,
            features=[DocumentAnalysisFeature.BARCODES],
        )
        results = poller.result()

        pages: list[dict[str, Any]] = []
        barcodes: list[dict[str, Any]] = []

        for page in results.pages:
            page_number = page.page_number
            page_content = ""

            # Method 1: spans
            if page.spans and results.content:
                try:
                    parts = []
                    for span in page.spans:
                        start = span.offset
                        end = start + span.length
                        parts.append(results.content[start:end])
                    page_content = "".join(parts)
                except Exception:
                    page_content = ""

            # Method 2: lines
            if not page_content and page.lines:
                try:
                    page_content = "\n".join(line.content for line in page.lines)
                except Exception:
                    page_content = ""

            # Method 3: words
            if not page_content and page.words:
                try:
                    page_content = " ".join(word.content for word in page.words)
                except Exception:
                    page_content = ""

            pages.append(
                {
                    "page_number": page_number,
                    "width": page.width,
                    "height": page.height,
                    "content": page_content,
                }
            )

            for bc in getattr(page, "barcodes", None) or []:
                barcodes.append(
                    {
                        "page_number": page_number,
                        "kind": bc.kind,
                        "value": bc.value,
                        "polygon": bc.polygon,
                        "confidence": bc.confidence,
                    }
                )

        # Tables
        tables: list[dict[str, Any]] = []
        for table in results.tables or []:
            rows: dict[int, dict[int, str]] = {}
            max_row = max((c.row_index for c in table.cells), default=-1)
            max_col = max((c.column_index for c in table.cells), default=-1)

            for r in range(max_row + 1):
                rows[r] = {c: "" for c in range(max_col + 1)}
            for cell in table.cells:
                rows[cell.row_index][cell.column_index] = (cell.content or "").strip()

            csv_rows = [
                [rows[r][c] for c in range(max_col + 1)] for r in range(max_row + 1)
            ]
            tables.append(
                {
                    "page_number": (
                        table.bounding_regions[0].page_number
                        if table.bounding_regions
                        else None
                    ),
                    "row_count": max_row + 1,
                    "column_count": max_col + 1,
                    "rows": csv_rows,
                    "polygon": (
                        table.bounding_regions[0].polygon
                        if table.bounding_regions
                        else None
                    ),
                }
            )

        return {
            "content": results.content or "",
            "pages": pages,
            "tables": tables,
            "barcodes": barcodes,
        }
