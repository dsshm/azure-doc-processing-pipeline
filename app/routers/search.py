"""Vector search API — search documents and chunks via Cosmos DB vector search."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query.")
    vector_field: str = Field(default="summary_vector", description="Vector field: summary_vector or purpose_vector.")
    top: int = Field(default=10, ge=1, le=50)
    filter: str = Field(default="", description="Optional WHERE clause fragment.")


class ChunkSearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query.")
    top: int = Field(default=10, ge=1, le=50)


@router.post("")
async def search_documents(request: Request, body: SearchRequest):
    """Search documents by semantic similarity using Cosmos DB vector search.

    Embeds the query text, then runs VectorDistance against the chosen vector field.
    """
    llm = request.app.state.llm
    cosmos = request.app.state.cosmos

    if body.vector_field not in ("summary_vector", "purpose_vector"):
        raise HTTPException(status_code=400, detail="vector_field must be 'summary_vector' or 'purpose_vector'")

    query_vector = llm.generate_embedding(text=body.query)

    results = cosmos.vector_search(
        query_vector=query_vector,
        vector_field=body.vector_field,
        top=body.top,
        filters=body.filter,
    )
    return {"count": len(results), "results": results}


@router.post("/chunks")
async def search_chunks(request: Request, body: ChunkSearchRequest):
    """Search within document chunks for granular passage-level retrieval.

    Embeds the query text, then runs VectorDistance against chunk vectors.
    """
    llm = request.app.state.llm
    cosmos = request.app.state.cosmos

    query_vector = llm.generate_embedding(text=body.query)

    results = cosmos.vector_search_chunks(
        query_vector=query_vector,
        top=body.top,
    )
    return {"count": len(results), "results": results}
