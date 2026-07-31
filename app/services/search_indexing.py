"""Search text and embedding metadata helpers for Cosmos DB search."""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SEARCH_INDEX_VERSION = "2026-07-31"


class EmbeddingGenerator(Protocol):
    @property
    def embedding_model(self) -> str: ...

    @property
    def embedding_api_version(self) -> str: ...

    def generate_embedding(self, text: str) -> list[float]: ...


@dataclass
class SearchIndexAssessment:
    needs_update: bool
    reasons: list[str] = field(default_factory=list)
    chunk_vectors_stale: int = 0
    chunk_vectors_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "needs_update": self.needs_update,
            "reasons": self.reasons,
            "chunk_vectors_stale": self.chunk_vectors_stale,
            "chunk_vectors_total": self.chunk_vectors_total,
        }


@dataclass
class SearchIndexBuildResult:
    document: dict[str, Any]
    changed: bool
    reasons: list[str] = field(default_factory=list)
    generated_embeddings: int = 0
    failed_embeddings: int = 0
    chunk_vectors_generated: int = 0
    chunk_vectors_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "reasons": self.reasons,
            "generated_embeddings": self.generated_embeddings,
            "failed_embeddings": self.failed_embeddings,
            "chunk_vectors_generated": self.chunk_vectors_generated,
            "chunk_vectors_total": self.chunk_vectors_total,
        }


def build_search_text(consolidated: dict[str, Any]) -> str:
    """Build the materialized full-text field searched by Cosmos DB."""
    parts: list[str] = []

    def add(label: str, value: Any) -> None:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                parts.append(f"{label}: {normalized}")
        elif isinstance(value, (int, float)):
            parts.append(f"{label}: {value}")

    def add_values(label: str, values: Any) -> None:
        if not isinstance(values, list):
            return
        normalized = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                normalized.append(text)
        if normalized:
            parts.append(f"{label}: {', '.join(dict.fromkeys(normalized))}")

    add("Title", consolidated.get("title"))
    add("Document type", consolidated.get("doc_type"))
    add("Description", consolidated.get("description"))
    add("Summary", consolidated.get("summary"))
    add("Author", consolidated.get("author"))
    add("Date created", consolidated.get("date_created"))
    add_values("Keywords", consolidated.get("keywords"))

    for category in consolidated.get("categories") or []:
        if isinstance(category, dict):
            add("Category", category.get("category"))

    key_fields = consolidated.get("key_fields")
    if isinstance(key_fields, dict):
        add("Document purpose", key_fields.get("document_purpose"))
        add_values("Topics", key_fields.get("topics"))
        add_values("Key facts", key_fields.get("key_facts"))
        add_values("Actionable items", key_fields.get("actionable_items"))

        entities = key_fields.get("entities")
        if isinstance(entities, dict):
            for entity_type in ("people", "organizations", "dates", "amounts", "locations"):
                add_values(entity_type.replace("_", " ").title(), entities.get(entity_type))
            for location in entities.get("geocoded_locations") or []:
                if not isinstance(location, dict):
                    continue
                add("Geocoded location query", location.get("query"))
                add("Geocoded display name", location.get("display_name"))
                add("Geocoded formatted address", location.get("formatted_address"))
                latitude = location.get("latitude")
                longitude = location.get("longitude")
                if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
                    parts.append(f"Geocoded coordinates: {latitude}, {longitude}")

    for page_summary in consolidated.get("page_summaries") or []:
        if isinstance(page_summary, dict):
            add("Page summary", page_summary.get("summary"))
            add_values("Page key points", page_summary.get("key_points"))

    return "\n".join(dict.fromkeys(parts))


def assess_search_index(
    document: dict[str, Any],
    llm: EmbeddingGenerator,
    include_chunks: bool = True,
) -> SearchIndexAssessment:
    """Check whether a persisted result has current search text and embeddings."""
    reasons: list[str] = []
    desired_search_text = build_search_text(document)
    if document.get("search_text", "") != desired_search_text:
        reasons.append("search_text_missing_or_stale")

    if not _search_index_metadata_current(document, llm, desired_search_text, include_chunks=include_chunks):
        reasons.append("search_index_metadata_missing_or_stale")

    summary_text = desired_search_text or str(document.get("summary") or "").strip()
    if summary_text and not _embedding_current(
        vector=document.get("summary_vector"),
        metadata=document.get("summary_vector_metadata"),
        llm=llm,
        source_text=summary_text,
        source_field="search_text" if desired_search_text else "summary",
    ):
        reasons.append("summary_vector_missing_or_stale")

    key_fields = document.get("key_fields")
    purpose_text = ""
    if isinstance(key_fields, dict):
        purpose_text = str(key_fields.get("document_purpose") or "").strip()
    if purpose_text and not _embedding_current(
        vector=document.get("purpose_vector"),
        metadata=document.get("purpose_vector_metadata"),
        llm=llm,
        source_text=purpose_text,
        source_field="key_fields.document_purpose",
    ):
        reasons.append("purpose_vector_missing_or_stale")

    stale_chunks = 0
    total_chunks = 0
    if include_chunks:
        chunks = document.get("chunks")
        if isinstance(chunks, list):
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                text = str(chunk.get("text") or "").strip()
                if not text:
                    continue
                total_chunks += 1
                if not _embedding_current(
                    vector=chunk.get("vector"),
                    metadata=chunk.get("vector_metadata"),
                    llm=llm,
                    source_text=text,
                    source_field="chunks.text",
                ):
                    stale_chunks += 1
    if stale_chunks:
        reasons.append("chunk_vectors_missing_or_stale")

    return SearchIndexAssessment(
        needs_update=bool(reasons),
        reasons=reasons,
        chunk_vectors_stale=stale_chunks,
        chunk_vectors_total=total_chunks,
    )


def apply_search_index(
    document: dict[str, Any],
    llm: EmbeddingGenerator,
    pages: list[dict[str, Any]] | None = None,
    include_chunks: bool = True,
    force: bool = False,
    fail_fast: bool = False,
) -> SearchIndexBuildResult:
    """Build or refresh search_text, vectors, and vector-adjacent metadata."""
    updated = copy.deepcopy(document)
    assessment = assess_search_index(updated, llm, include_chunks=include_chunks)
    reasons = list(assessment.reasons)
    changed = False
    generated_embeddings = 0
    failed_embeddings = 0
    chunk_vectors_generated = 0
    chunk_vectors_total = 0

    desired_search_text = build_search_text(updated)
    if force or updated.get("search_text", "") != desired_search_text:
        updated["search_text"] = desired_search_text
        changed = True
        if "search_text_missing_or_stale" not in reasons:
            reasons.append("search_text_missing_or_stale")

    summary_text = desired_search_text or str(updated.get("summary") or "").strip()
    summary_source = "search_text" if desired_search_text else "summary"
    if summary_text and (
        force
        or not _embedding_current(
            vector=updated.get("summary_vector"),
            metadata=updated.get("summary_vector_metadata"),
            llm=llm,
            source_text=summary_text,
            source_field=summary_source,
        )
    ):
        try:
            vector = llm.generate_embedding(text=summary_text)
            updated["summary_vector"] = vector
            updated["summary_vector_metadata"] = _embedding_metadata(
                llm=llm,
                vector=vector,
                source_text=summary_text,
                source_field=summary_source,
            )
            changed = True
            generated_embeddings += 1
        except Exception:
            failed_embeddings += 1
            logger.exception("Failed to generate summary embedding for search index backfill")
            if fail_fast:
                raise

    key_fields = updated.get("key_fields")
    purpose_text = ""
    if isinstance(key_fields, dict):
        purpose_text = str(key_fields.get("document_purpose") or "").strip()
    if purpose_text and (
        force
        or not _embedding_current(
            vector=updated.get("purpose_vector"),
            metadata=updated.get("purpose_vector_metadata"),
            llm=llm,
            source_text=purpose_text,
            source_field="key_fields.document_purpose",
        )
    ):
        try:
            vector = llm.generate_embedding(text=purpose_text)
            updated["purpose_vector"] = vector
            updated["purpose_vector_metadata"] = _embedding_metadata(
                llm=llm,
                vector=vector,
                source_text=purpose_text,
                source_field="key_fields.document_purpose",
            )
            changed = True
            generated_embeddings += 1
        except Exception:
            failed_embeddings += 1
            logger.exception("Failed to generate purpose embedding for search index backfill")
            if fail_fast:
                raise

    if include_chunks:
        chunks = _ensure_chunks(updated, pages)
        for chunk in chunks:
            text = str(chunk.get("text") or "").strip()
            if not text:
                continue
            chunk_vectors_total += 1
            if force or not _embedding_current(
                vector=chunk.get("vector"),
                metadata=chunk.get("vector_metadata"),
                llm=llm,
                source_text=text,
                source_field="chunks.text",
            ):
                try:
                    vector = llm.generate_embedding(text=text)
                    chunk["vector"] = vector
                    chunk["vector_metadata"] = _embedding_metadata(
                        llm=llm,
                        vector=vector,
                        source_text=text,
                        source_field="chunks.text",
                    )
                    changed = True
                    generated_embeddings += 1
                    chunk_vectors_generated += 1
                except Exception:
                    failed_embeddings += 1
                    logger.exception("Failed to generate chunk embedding for search index backfill")
                    if fail_fast:
                        raise

    search_index_metadata = _search_index_metadata(
        document=updated,
        llm=llm,
        search_text=desired_search_text,
        include_chunks=include_chunks,
        chunk_vectors_total=chunk_vectors_total,
        failed_embeddings=failed_embeddings,
    )
    if force or updated.get("search_index_metadata") != search_index_metadata:
        updated["search_index_metadata"] = search_index_metadata
        changed = True

    return SearchIndexBuildResult(
        document=updated,
        changed=changed,
        reasons=reasons,
        generated_embeddings=generated_embeddings,
        failed_embeddings=failed_embeddings,
        chunk_vectors_generated=chunk_vectors_generated,
        chunk_vectors_total=chunk_vectors_total,
    )


def _ensure_chunks(document: dict[str, Any], pages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    chunks = document.get("chunks")
    if isinstance(chunks, list):
        return [chunk for chunk in chunks if isinstance(chunk, dict)]

    if not pages:
        return []

    generated_chunks: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        text = str(page.get("content") or "").strip()
        if text:
            generated_chunks.append({"chunk_index": index, "text": text})
    if generated_chunks:
        document["chunks"] = generated_chunks
    return generated_chunks


def _search_index_metadata_current(
    document: dict[str, Any],
    llm: EmbeddingGenerator,
    search_text: str,
    include_chunks: bool,
) -> bool:
    metadata = document.get("search_index_metadata")
    if not isinstance(metadata, dict):
        return False

    return (
        metadata.get("version") == SEARCH_INDEX_VERSION
        and metadata.get("status") == "complete"
        and metadata.get("embedding_model") == llm.embedding_model
        and metadata.get("embedding_api_version") == llm.embedding_api_version
        and metadata.get("include_chunks") == include_chunks
        and metadata.get("search_text_hash") == _text_hash(search_text)
    )


def _search_index_metadata(
    document: dict[str, Any],
    llm: EmbeddingGenerator,
    search_text: str,
    include_chunks: bool,
    chunk_vectors_total: int,
    failed_embeddings: int,
) -> dict[str, Any]:
    return {
        "version": SEARCH_INDEX_VERSION,
        "status": "complete" if failed_embeddings == 0 else "incomplete",
        "failed_embeddings": failed_embeddings,
        "embedding_model": llm.embedding_model,
        "embedding_api_version": llm.embedding_api_version,
        "include_chunks": include_chunks,
        "search_text_hash": _text_hash(search_text),
        "summary_vector_dimensions": _vector_dimensions(document.get("summary_vector")),
        "purpose_vector_dimensions": _vector_dimensions(document.get("purpose_vector")),
        "chunk_vectors_total": chunk_vectors_total,
        "updated_at": _utc_now(),
    }


def _embedding_current(
    vector: Any,
    metadata: Any,
    llm: EmbeddingGenerator,
    source_text: str,
    source_field: str,
) -> bool:
    if not isinstance(vector, list) or not vector:
        return False
    if not isinstance(metadata, dict):
        return False

    dimensions = _vector_dimensions(vector)
    return (
        metadata.get("provider") == "azure_openai"
        and metadata.get("model") == llm.embedding_model
        and metadata.get("deployment") == llm.embedding_model
        and metadata.get("api_version") == llm.embedding_api_version
        and metadata.get("dimensions") == dimensions
        and metadata.get("source_field") == source_field
        and metadata.get("source_hash") == _text_hash(source_text)
        and metadata.get("search_index_version") == SEARCH_INDEX_VERSION
    )


def _embedding_metadata(
    llm: EmbeddingGenerator,
    vector: list[float],
    source_text: str,
    source_field: str,
) -> dict[str, Any]:
    return {
        "provider": "azure_openai",
        "model": llm.embedding_model,
        "deployment": llm.embedding_model,
        "api_version": llm.embedding_api_version,
        "dimensions": len(vector),
        "source_field": source_field,
        "source_hash": _text_hash(source_text),
        "generated_at": _utc_now(),
        "search_index_version": SEARCH_INDEX_VERSION,
    }


def _text_hash(text: str) -> str:
    normalized = text.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _vector_dimensions(vector: Any) -> int:
    return len(vector) if isinstance(vector, list) else 0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
