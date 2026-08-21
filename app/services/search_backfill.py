"""Application service for search-index backfill/reprocess operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from azure.cosmos.exceptions import CosmosAccessConditionFailedError

from app.services.geocoding import apply_geocoding, assess_geocoding
from app.services.search_indexing import (
    SEARCH_INDEX_VERSION,
    apply_search_index,
    assess_search_index,
)

if TYPE_CHECKING:
    from app.plugins.cosmos_plugin import CosmosPlugin
    from app.plugins.llm_plugin import LLMPlugin
    from app.plugins.maps_plugin import AzureMapsPlugin

logger = logging.getLogger(__name__)


class SearchIndexBackfillService:
    """Backfill materialized search fields and embedding metadata for existing results."""

    def __init__(self, cosmos: "CosmosPlugin", llm: "LLMPlugin", maps: "AzureMapsPlugin"):
        self.cosmos = cosmos
        self.llm = llm
        self.maps = maps

    def backfill_batch(
        self,
        limit: int,
        dry_run: bool = True,
        force: bool = False,
        include_chunks: bool = True,
        include_geocoding: bool = True,
        max_results: int | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        candidates = self.cosmos.list_search_index_backfill_candidates(
            limit=limit,
            search_index_version=SEARCH_INDEX_VERSION,
            embedding_model=self.llm.embedding_model,
            embedding_api_version=self.llm.embedding_api_version,
            force=force,
            include_chunks=include_chunks,
            include_geocoding=include_geocoding,
        )

        results: list[dict[str, Any]] = []
        updated = 0
        would_update = 0
        skipped = 0
        failed = 0
        generated_embeddings = 0
        geocoded_locations_added = 0

        for document in candidates:
            outcome = self._backfill_document(
                document=document,
                dry_run=dry_run,
                force=force,
                include_chunks=include_chunks,
                include_geocoding=include_geocoding,
            )
            status = outcome["status"]
            if status == "updated":
                updated += 1
                generated_embeddings += int(outcome.get("generated_embeddings") or 0)
                geocoded_locations_added += int(outcome.get("geocoded_locations_added") or 0)
            elif status == "would_update":
                would_update += 1
            elif status == "skipped":
                skipped += 1
            elif status == "failed":
                failed += 1
            if max_results is None or len(results) < max_results:
                results.append(outcome)
            _notify_backfill_progress(
                progress_callback,
                candidate_count=len(candidates),
                processed=updated + would_update + skipped + failed,
                updated=updated,
                would_update=would_update,
                skipped=skipped,
                failed=failed,
                generated_embeddings=generated_embeddings,
                geocoded_locations_added=geocoded_locations_added,
            )

        candidate_count = len(candidates)
        if force:
            scan_mode = "all_results"
        elif include_geocoding:
            scan_mode = "stale_or_missing_geocode_candidates"
        else:
            scan_mode = "stale_candidates"
        if force:
            message = "Force mode scanned result documents regardless of whether their search index is current."
        elif candidate_count == 0:
            if include_geocoding:
                message = (
                    "No stale search-index or missing-geocode candidate documents were found. "
                    "This does not mean Cosmos DB has zero result documents."
                )
            else:
                message = (
                    "No stale search-index candidate documents were found. "
                    "This does not mean Cosmos DB has zero result documents."
                )
        else:
            message = (
                "Scanned stale search-index and missing-geocode candidate documents."
                if include_geocoding
                else "Scanned stale search-index candidate documents."
            )

        return {
            "dry_run": dry_run,
            "force": force,
            "include_chunks": include_chunks,
            "include_geocoding": include_geocoding,
            "limit": limit,
            "scan_mode": scan_mode,
            "message": message,
            "search_index_version": SEARCH_INDEX_VERSION,
            "embedding_model": self.llm.embedding_model,
            "embedding_api_version": self.llm.embedding_api_version,
            "candidate_documents_scanned": candidate_count,
            "scanned": candidate_count,
            "updated": updated,
            "would_update": would_update,
            "skipped": skipped,
            "failed": failed,
            "generated_embeddings": generated_embeddings,
            "geocoded_locations_added": geocoded_locations_added,
            "results_truncated": max_results is not None and candidate_count > len(results),
            "results": results,
        }

    def backfill_one(
        self,
        job_id: str,
        dry_run: bool = True,
        force: bool = False,
        include_chunks: bool = True,
        include_geocoding: bool = True,
    ) -> dict[str, Any]:
        document = self.cosmos.get_result(job_id=job_id)
        if document is None:
            return {
                "job_id": job_id,
                "status": "not_found",
                "message": "Result document was not found.",
            }
        return self._backfill_document(
            document=document,
            dry_run=dry_run,
            force=force,
            include_chunks=include_chunks,
            include_geocoding=include_geocoding,
        )

    def _backfill_document(
        self,
        document: dict[str, Any],
        dry_run: bool,
        force: bool,
        include_chunks: bool,
        include_geocoding: bool,
    ) -> dict[str, Any]:
        job_id = str(document.get("jobId") or document.get("id") or "")
        assessment = assess_search_index(document, self.llm, include_chunks=include_chunks)
        geocoding_assessment = assess_geocoding(document, self.maps) if include_geocoding else None
        geocoding_needs_update = bool(geocoding_assessment and geocoding_assessment.needs_update)
        if not force and not assessment.needs_update and not geocoding_needs_update:
            return {
                "job_id": job_id,
                "status": "skipped",
                "assessment": assessment.to_dict(),
                "geocoding_assessment": geocoding_assessment.to_dict() if geocoding_assessment else None,
            }

        if dry_run:
            return {
                "job_id": job_id,
                "status": "would_update",
                "assessment": assessment.to_dict(),
                "geocoding_assessment": geocoding_assessment.to_dict() if geocoding_assessment else None,
            }

        try:
            working_document = document
            geocoding_result = None
            if include_geocoding:
                geocoding_result = apply_geocoding(
                    working_document,
                    self.maps,
                    fail_when_unconfigured=True,
                    fail_fast=True,
                )
                working_document = geocoding_result.document

            build_result = apply_search_index(
                document=working_document,
                llm=self.llm,
                include_chunks=include_chunks,
                force=force,
                fail_fast=True,
            )
            changed = bool(build_result.changed or (geocoding_result and geocoding_result.changed))
            if not changed:
                return {
                    "job_id": job_id,
                    "status": "skipped",
                    "assessment": assessment.to_dict(),
                    "geocoding_assessment": geocoding_assessment.to_dict() if geocoding_assessment else None,
                    **(geocoding_result.to_dict() if geocoding_result else {}),
                    **build_result.to_dict(),
                }

            self.cosmos.replace_result_document(build_result.document)
            return {
                "job_id": job_id,
                "status": "updated",
                "assessment": assessment.to_dict(),
                "geocoding_assessment": geocoding_assessment.to_dict() if geocoding_assessment else None,
                **(geocoding_result.to_dict() if geocoding_result else {}),
                **build_result.to_dict(),
            }
        except CosmosAccessConditionFailedError:
            logger.warning("Search backfill skipped %s because it changed concurrently", job_id)
            return {
                "job_id": job_id,
                "status": "failed",
                "error": "Result changed concurrently; retry the backfill.",
                "assessment": assessment.to_dict(),
                "geocoding_assessment": geocoding_assessment.to_dict() if geocoding_assessment else None,
            }
        except Exception as exc:
            logger.exception("Search backfill failed for %s", job_id)
            return {
                "job_id": job_id,
                "status": "failed",
                "error": str(exc),
                "assessment": assessment.to_dict(),
                "geocoding_assessment": geocoding_assessment.to_dict() if geocoding_assessment else None,
            }


def _notify_backfill_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    candidate_count: int,
    processed: int,
    updated: int,
    would_update: int,
    skipped: int,
    failed: int,
    generated_embeddings: int,
    geocoded_locations_added: int,
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        {
            "processed": processed,
            "candidate_documents_scanned": candidate_count,
            "updated": updated,
            "would_update": would_update,
            "skipped": skipped,
            "failed": failed,
            "generated_embeddings": generated_embeddings,
            "geocoded_locations_added": geocoded_locations_added,
        }
    )
