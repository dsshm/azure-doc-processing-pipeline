"""LLM analysis agent — wraps LLMPlugin for structured document analysis."""

from __future__ import annotations

import logging

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent

from app.plugins.llm_plugin import LLMPlugin

logger = logging.getLogger(__name__)

ANALYSIS_INSTRUCTIONS = """\
You are a Document Analysis Agent. Your job is to analyze extracted document
content using LLM capabilities.

When asked to analyze document pages:
1. Use analyze_page for each page to get per-page structured analysis
   (description, categories, entities, keywords).
2. After all pages are analyzed, use consolidate_analyses to merge
   the per-page results into a single DocumentAnalysisResult.
3. The final output must include:
   - title and doc_type (document classification)
   - summary (2-3 paragraph narrative)
   - categories with supporting evidence
   - entities (people, organizations, locations, dates, events)
   - keywords, key_facts, document_purpose, actionable_items
4. If a page fails analysis, skip it and continue with remaining pages.
"""


def create_analysis_agent(kernel: Kernel) -> ChatCompletionAgent:
    """Create and return the analysis agent with LLM plugin."""
    kernel.add_plugin(LLMPlugin(), plugin_name="LLM")

    return ChatCompletionAgent(
        kernel=kernel,
        name="AnalysisAgent",
        instructions=ANALYSIS_INSTRUCTIONS,
    )
