"""Search API — vector, full-text, and hybrid search over Cosmos DB results."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query.")
    vector_field: str = Field(default="summary_vector", description="Vector field: summary_vector or purpose_vector.")
    top: int | None = Field(default=None, ge=1)
    filter: str = Field(default="", description="Optional WHERE clause fragment.")


class ChunkSearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query.")
    top: int | None = Field(default=None, ge=1)


class FullTextSearchRequest(BaseModel):
    query: str = Field(..., description="Keyword, address, building, city, or natural language search text.")
    top: int | None = Field(default=None, ge=1)


class HybridSearchRequest(BaseModel):
    query: str = Field(..., description="Keyword, address, building, city, or natural language search text.")
    vector_field: str = Field(default="summary_vector", description="Vector field: summary_vector or purpose_vector.")
    top: int | None = Field(default=None, ge=1)


def _resolve_top(requested_top: int | None) -> int:
    top = settings.search_default_top if requested_top is None else requested_top
    if top > settings.search_max_top:
        raise HTTPException(status_code=400, detail=f"top cannot exceed {settings.search_max_top}")
    return top


def _validate_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="query must not be empty")
    return normalized


@router.post("")
async def search_documents(request: Request, body: SearchRequest):
    """Search documents by semantic similarity using Cosmos DB vector search.

    Embeds the query text, then runs VectorDistance against the chosen vector field.
    """
    llm = request.app.state.llm
    cosmos = request.app.state.cosmos

    if body.vector_field not in ("summary_vector", "purpose_vector"):
        raise HTTPException(status_code=400, detail="vector_field must be 'summary_vector' or 'purpose_vector'")

    query_text = _validate_query(body.query)
    top = _resolve_top(body.top)
    query_vector = llm.generate_embedding(text=query_text)

    results = cosmos.vector_search(
        query_vector=query_vector,
        vector_field=body.vector_field,
        top=top,
        filters=body.filter,
    )
    return {"count": len(results), "results": results}


@router.post("/full-text")
async def search_full_text(request: Request, body: FullTextSearchRequest):
    """Search documents by Cosmos DB full-text BM25 scoring."""
    cosmos = request.app.state.cosmos
    query_text = _validate_query(body.query)
    top = _resolve_top(body.top)

    results = cosmos.full_text_search(
        query_text=query_text,
        top=top,
    )
    return {"count": len(results), "results": results}


@router.post("/hybrid")
async def search_hybrid(request: Request, body: HybridSearchRequest):
    """Search documents by hybrid vector similarity and full-text BM25 ranking."""
    llm = request.app.state.llm
    cosmos = request.app.state.cosmos

    if body.vector_field not in ("summary_vector", "purpose_vector"):
        raise HTTPException(status_code=400, detail="vector_field must be 'summary_vector' or 'purpose_vector'")

    query_text = _validate_query(body.query)
    top = _resolve_top(body.top)
    query_vector = llm.generate_embedding(text=query_text)

    results = cosmos.hybrid_search(
        query_text=query_text,
        query_vector=query_vector,
        vector_field=body.vector_field,
        top=top,
    )
    return {"count": len(results), "results": results}


@router.post("/chunks")
async def search_chunks(request: Request, body: ChunkSearchRequest):
    """Search within document chunks for granular passage-level retrieval.

    Embeds the query text, then runs VectorDistance against chunk vectors.
    """
    llm = request.app.state.llm
    cosmos = request.app.state.cosmos

    query_text = _validate_query(body.query)
    top = _resolve_top(body.top)
    query_vector = llm.generate_embedding(text=query_text)

    results = cosmos.vector_search_chunks(
        query_vector=query_vector,
        top=top,
    )
    return {"count": len(results), "results": results}
