"""Merged document analysis output schema.

Combines GeneralDescription (bp_llm.py) and DocumentSummary (bp_doc_llm.py)
into a single unified model.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared literals
# ---------------------------------------------------------------------------

Categories = Literal[
    "map",
    "geography",
    "history",
    "blueprint",
    "engineering",
]

EntityTypes = Literal[
    "person",
    "organization",
    "location",
    "date",
    "event",
]

# ---------------------------------------------------------------------------
# Sub‑models
# ---------------------------------------------------------------------------


class CategoryEvidence(BaseModel):
    category: Categories = Field(..., description="The category that applies.")
    confidence: float = Field(..., description="Confidence score.")
    supporting_evidence: list[str] = Field(default_factory=list, description="Evidence strings.")


class EntityEvidence(BaseModel):
    quote: str = Field(..., description="Quoted text supporting the entity.")
    start_char: Optional[int] = Field(None, description="Start character index.")
    end_char: Optional[int] = Field(None, description="End character index.")


class EntityItem(BaseModel):
    entity: str = Field(..., description="Named entity value.")
    type: EntityTypes = Field(..., description="Entity type.")
    confidence: float = Field(..., description="Confidence score.")
    supporting_evidence: list[EntityEvidence] = Field(default_factory=list)


class Translation(BaseModel):
    text: str = Field(..., description="Translated text.")
    original_text: str = Field(..., description="Original text.")
    source_language: str = Field(...)
    target_language: str = Field(...)


class PageSummary(BaseModel):
    page_number: int = Field(...)
    summary: str = Field(...)
    key_points: list[str] = Field(default_factory=list)


class GeocodedLocation(BaseModel):
    """Latitude/longitude enrichment for extracted location entities."""

    query: str = Field(..., description="Location text sent to Azure Maps.")
    latitude: float = Field(..., description="Latitude returned by Azure Maps.")
    longitude: float = Field(..., description="Longitude returned by Azure Maps.")
    formatted_address: str = Field(default="", description="Best formatted address from the search result.")
    display_name: str = Field(default="", description="POI or address label from the search result.")
    result_type: str = Field(default="", description="Azure Maps result type, such as POI or Point Address.")
    score: Optional[float] = Field(default=None, description="Azure Maps fuzzy-search score.")
    source: str = Field(default="azure_maps_fuzzy_search")


class EntityData(BaseModel):
    """Flat entity lists used in DocumentSummary keyFields."""

    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    geocoded_locations: list[GeocodedLocation] = Field(default_factory=list)


class DocumentKeyFields(BaseModel):
    entities: EntityData = Field(default_factory=EntityData)
    topics: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    document_purpose: str = Field(default="")
    actionable_items: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chunk model (used by DocumentAnalysisResult)
# ---------------------------------------------------------------------------


class DocumentChunk(BaseModel):
    """A text chunk from the source document with its embedding."""

    chunk_index: int = Field(..., description="0-based position within the document.")
    text: str = Field(..., description="Raw text of the chunk.")
    vector: Optional[list[float]] = Field(default=None, description="Embedding of the chunk text.")
    vector_metadata: Optional[dict] = Field(default=None, description="Embedding provenance for vector.")


# ---------------------------------------------------------------------------
# Merged top‑level model
# ---------------------------------------------------------------------------


class DocumentAnalysisResult(BaseModel):
    """Unified output schema merging GeneralDescription + DocumentSummary."""

    # --- from DocumentSummary ---
    title: str = Field(default="", description="Descriptive title.")
    doc_type: str = Field(default="", description="Document type (contract, invoice, report, …).")

    # --- from GeneralDescription ---
    description: str = Field(default="", description="General description of document content.")
    summary: str = Field(default="", description="Comprehensive 2‑3 paragraph narrative summary.")
    author: Optional[str] = Field(default=None)
    date_created: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0)

    categories: list[CategoryEvidence] = Field(default_factory=list)
    entities: list[EntityItem] = Field(default_factory=list)
    keywords: Optional[list[str]] = Field(default=None)
    translation: Optional[Translation] = Field(default=None)
    page_summaries: Optional[list[PageSummary]] = Field(default=None)

    # --- from DocumentSummary keyFields ---
    key_fields: DocumentKeyFields = Field(default_factory=DocumentKeyFields)

    # --- vector embeddings ---
    search_text: str = Field(default="", description="Normalized text used for full-text and hybrid search.")
    summary_vector: Optional[list[float]] = Field(default=None, description="Embedding of search_text when present, otherwise summary.")
    summary_vector_metadata: Optional[dict] = Field(default=None, description="Embedding provenance for summary_vector.")
    purpose_vector: Optional[list[float]] = Field(default=None, description="Embedding of document_purpose.")
    purpose_vector_metadata: Optional[dict] = Field(default=None, description="Embedding provenance for purpose_vector.")
    chunks: Optional[list[DocumentChunk]] = Field(default=None, description="Text chunks with embeddings for granular retrieval.")
    search_index_metadata: dict = Field(default_factory=dict, description="Search index backfill/version metadata.")

    # --- processing metadata ---
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Chunk‑level analysis model (used by LLM plugin internally)
# ---------------------------------------------------------------------------


class ChunkAnalysis(BaseModel):
    summary: str = Field(...)
    entities: EntityData = Field(default_factory=EntityData)
    topics: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    doc_type_indicators: list[str] = Field(default_factory=list)


class GeneralDescription(BaseModel):
    """Per‑page structured LLM output (kept for SK structured output calls)."""

    description: str = Field(...)
    author: Optional[str] = Field(default=None)
    date_created: Optional[str] = Field(default=None)
    confidence: float = Field(...)
    categories: list[CategoryEvidence] = Field(default_factory=list)
    entities: list[EntityItem] = Field(default_factory=list)
    keywords: Optional[list[str]] = Field(default=None)
    translation: Optional[Translation] = Field(default=None)
    page_summaries: Optional[list[PageSummary]] = Field(default=None)
