"""Semantic Kernel plugin for LLM analysis and summarisation.

Ported from bp_llm.py (LLMOperations) + services/llm_summary.py (DocumentSummarizer)
+ chunking intent from bp_doc_llm.py.
Auth: DefaultAzureCredential via azure_ad_token_provider.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any

import openai
import tiktoken
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from semantic_kernel.functions import kernel_function

from app.models.document import (
    Categories,
    ChunkAnalysis,
    DocumentAnalysisResult,
    DocumentKeyFields,
    EntityData,
    EntityItem,
    GeneralDescription,
    PageSummary,
)

logger = logging.getLogger(__name__)


class LLMPlugin:
    """Azure OpenAI analysis & summarisation exposed as SK functions."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_version: str | None = None,
        model_name: str | None = None,
        embedding_model: str | None = None,
        embedding_api_version: str | None = None,
    ):
        self._endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")
        self._api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        self._model = model_name or os.getenv("AZURE_OPENAI_MODEL_NAME", "gpt-5.1")
        self._embedding_model = embedding_model or os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self._embedding_api_version = (
            embedding_api_version
            or os.getenv("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-12-01-preview")
        )

        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

        self.client = openai.AzureOpenAI(
            azure_endpoint=self._endpoint,
            azure_ad_token_provider=token_provider,
            api_version=self._api_version,
        )
        self.embedding_client = openai.AzureOpenAI(
            azure_endpoint=self._endpoint,
            azure_ad_token_provider=token_provider,
            api_version=self._embedding_api_version,
        )

        # Summariser settings
        self._max_input_tokens_per_request = 15_000
        self._chunk_size = 10  # pages per hierarchical chunk

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    @property
    def embedding_api_version(self) -> str:
        return self._embedding_api_version

    # ------------------------------------------------------------------
    # Page‑level analysis
    # ------------------------------------------------------------------
    @kernel_function(
        name="analyze_page",
        description="Analyze a single document page with LLM structured output.",
    )
    def analyze_page(
        self,
        page_content: Annotated[str, "Text content of the page"],
        page_number: Annotated[int, "1‑based page number"],
        total_pages: Annotated[int, "Total pages in the document"],
    ) -> dict[str, Any]:
        prompt = (
            f"This is page {page_number} of {total_pages} from a document.\n\n"
            f'Text:\n"""{page_content}"""\n\n'
            "Instructions:\n"
            "1. Provide a brief general description of this page's content.\n"
            f"2. Identify relevant categories from: {list(Categories.__args__)}. "
            "For each, provide supporting evidence.\n"
            "3. Extract named entities (person, organization, location, date, event) "
            "with supporting evidence.\n"
            "4. If the source language is not English, provide a translation.\n"
        )

        response = self._create_chat_completion(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert document analyst. Provide a concise general "
                        "description, identify categories, and extract named entities."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "GeneralDescription",
                    "schema": GeneralDescription.model_json_schema(),
                },
            },
            temperature=0.2,
            max_completion_tokens=4000,
        )

        try:
            data = json.loads(response.choices[0].message.content)
            data["page_number"] = page_number
            data["page_text_length"] = len(page_content)
            return data
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("Error parsing LLM response for page %d: %s", page_number, exc)
            return {
                "description": f"Error analyzing page {page_number}",
                "author": None,
                "date_created": None,
                "confidence": 0.0,
                "categories": [],
                "entities": [],
                "keywords": None,
                "translation": None,
                "page_number": page_number,
                "page_text_length": len(page_content),
                "error": str(exc),
                "is_error": True,
            }

    # ------------------------------------------------------------------
    # Chunk‑level analysis  (from bp_doc_llm.py)
    # ------------------------------------------------------------------
    @kernel_function(
        name="analyze_chunk",
        description="Analyze a text chunk for entities, topics, key facts, and doc‑type indicators.",
    )
    def analyze_chunk(
        self,
        chunk_text: Annotated[str, "Text chunk to analyse"],
        chunk_index: Annotated[int, "0‑based chunk index"],
        total_chunks: Annotated[int, "Total number of chunks"],
    ) -> dict[str, Any]:
        system_prompt = (
            "You are a document analysis assistant. Analyze the given text chunk and extract:\n"
            "1. Key entities (people, organizations, dates, amounts, locations)\n"
            "2. Main topics and themes\n"
            "3. Important facts and details\n"
            "4. Document type indicators\n"
            "5. Brief summary"
        )
        user_prompt = f"Chunk {chunk_index + 1} of {total_chunks}:\n\n{chunk_text}\n\nAnalyze this text chunk."

        response = self._create_chat_completion(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_completion_tokens=1000,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "chunk_analysis",
                    "schema": ChunkAnalysis.model_json_schema(),
                },
            },
        )

        try:
            data = json.loads(response.choices[0].message.content)
            data["chunk_index"] = chunk_index
            data["chunk_text_length"] = len(chunk_text)
            return data
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse chunk %d response: %s", chunk_index, exc)
            return {
                "summary": f"Error parsing chunk {chunk_index}",
                "entities": EntityData().model_dump(),
                "topics": [],
                "key_facts": [],
                "doc_type_indicators": [],
                "chunk_index": chunk_index,
                "chunk_text_length": len(chunk_text),
                "parse_error": True,
            }

    # ------------------------------------------------------------------
    # Consolidation / reduction
    # ------------------------------------------------------------------
    @kernel_function(
        name="consolidate_analyses",
        description="Consolidate multiple page analyses into a single DocumentAnalysisResult.",
    )
    def consolidate_analyses(
        self,
        page_results: Annotated[list[dict[str, Any]], "List of per‑page analysis dicts"],
        file_name: Annotated[str, "Original file name"] = "document",
    ) -> dict[str, Any]:
        all_descriptions: list[str] = []
        all_categories: list[dict] = []
        all_entities: list[dict] = []
        all_keywords: list[str] = []
        authors: set[str] = set()
        dates: set[str] = set()
        confidence_scores: list[float] = []

        for result in page_results:
            if result.get("error") or result.get("is_error"):
                continue
            page_num = result.get("page_number", "?")
            desc = result.get("description", "")
            if desc:
                all_descriptions.append(f"Page {page_num}: {desc}")
            all_categories.extend(result.get("categories", []))
            all_entities.extend(result.get("entities", []))
            kw = result.get("keywords")
            if kw:
                all_keywords.extend(kw)
            author = result.get("author")
            if author:
                authors.add(author)
            dc = result.get("date_created")
            if dc:
                dates.add(str(dc))
            conf = result.get("confidence")
            if conf:
                confidence_scores.append(conf)

        # Deduplicate
        unique_entities: dict[str, dict] = {}
        for ent in all_entities:
            key = ent.get("entity", "").lower()
            if key and key not in unique_entities:
                unique_entities[key] = ent

        unique_categories: dict[str, dict] = {}
        for cat in all_categories:
            ck = cat.get("category", "")
            if ck not in unique_categories:
                unique_categories[ck] = cat
            else:
                existing = unique_categories[ck]
                merged = set(existing.get("supporting_evidence", [])) | set(cat.get("supporting_evidence", []))
                existing["supporting_evidence"] = list(merged)

        unique_keywords = list(dict.fromkeys(all_keywords)) if all_keywords else None
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

        # Build narrative summary via hierarchical reducer
        summary = self._reduce_to_document_summary(page_results, len(page_results))

        # Build the DocumentSummary‑style key fields via LLM reduction
        key_fields = self._reduce_to_key_fields(page_results, file_name)

        page_summaries = [
            PageSummary(
                page_number=r.get("page_number", 0),
                summary=r.get("description", ""),
                key_points=r.get("keywords", []) or [],
            ).model_dump()
            for r in page_results
            if not r.get("error") and not r.get("is_error")
        ]

        result = DocumentAnalysisResult(
            title=key_fields.get("title", f"Analysis of {file_name}"),
            doc_type=key_fields.get("docType", ""),
            description=all_descriptions[0] if all_descriptions else "",
            summary=summary,
            author=list(authors)[0] if authors else None,
            date_created=list(dates)[0] if dates else None,
            confidence=round(avg_confidence, 2),
            categories=[cat for cat in unique_categories.values()],
            entities=[ent for ent in unique_entities.values()],
            keywords=unique_keywords,
            page_summaries=page_summaries,
            key_fields=DocumentKeyFields(**key_fields.get("keyFields", {})) if key_fields.get("keyFields") else DocumentKeyFields(),
            metadata={
                "total_pages": len(page_results),
                "successful_pages": len([r for r in page_results if not r.get("error")]),
                "original_filename": file_name,
            },
        )
        return result.model_dump()

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------
    @kernel_function(name="generate_embedding", description="Generate a text embedding vector.")
    def generate_embedding(
        self,
        text: Annotated[str, "Text to embed"],
    ) -> list[float]:
        resp = self.embedding_client.embeddings.create(model=self._embedding_model, input=text.strip())
        return resp.data[0].embedding

    # ------------------------------------------------------------------
    # Internal helpers (hierarchical summarisation ported from llm_summary.py)
    # ------------------------------------------------------------------
    def _estimate_tokens(self, text: str) -> int:
        try:
            encoding = tiktoken.encoding_for_model(self._model)
            return len(encoding.encode(text))
        except Exception:
            return len(text) // 4

    def _reduce_to_document_summary(self, page_summaries: list[dict], total_pages: int) -> str:
        summaries_text = []
        for p in page_summaries:
            if not p.get("error") and not p.get("is_error"):
                desc = p.get("description", "")
                pn = p.get("page_number", "?")
                if desc:
                    summaries_text.append(f"Page {pn}: {desc}")

        if not summaries_text:
            return "Document analysis completed with no valid content."

        combined = "\n\n".join(summaries_text)
        est = self._estimate_tokens(combined)

        try:
            if est > self._max_input_tokens_per_request:
                logger.info("Large document (%d tokens). Hierarchical reduction.", est)
                return self._hierarchical_reduce(summaries_text, total_pages)
            logger.info("Standard reduction (%d tokens).", est)
            return self._single_pass_reduce(combined, total_pages)
        except Exception as exc:
            logger.error("Failed to generate summary: %s", exc)
            fallback = " ".join(summaries_text[:10])
            if len(summaries_text) > 10:
                fallback += f"... (and {len(summaries_text) - 10} more pages)"
            return fallback

    def _single_pass_reduce(self, combined: str, total_pages: int) -> str:
        prompt = (
            f"You are analyzing a {total_pages}‑page document. Below are summaries for each page.\n\n"
            f"Page Summaries:\n{combined}\n\n"
            "Synthesize into a cohesive 2‑3 paragraph summary. Focus on purpose, key info, overall content. "
            "Remove redundancy and page references. Write a natural narrative."
        )
        resp = self._create_chat_completion(
            model=self._model,
            messages=[
                {"role": "system", "content": "You are an expert document analyst who creates clear, concise summaries."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_completion_tokens=800,
        )
        return resp.choices[0].message.content.strip()

    def _hierarchical_reduce(self, summaries: list[str], total_pages: int) -> str:
        chunks = [summaries[i : i + self._chunk_size] for i in range(0, len(summaries), self._chunk_size)]
        intermediates: list[str] = []

        for idx, chunk in enumerate(chunks):
            chunk_text = "\n\n".join(chunk)
            sp = idx * self._chunk_size + 1
            ep = min((idx + 1) * self._chunk_size, total_pages)
            prompt = (
                f"Pages {sp}‑{ep} of {total_pages}.\n\n{chunk_text}\n\n"
                "Provide a concise 1‑2 paragraph summary capturing key info."
            )
            try:
                resp = self._create_chat_completion(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": "You are an expert document analyst."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_completion_tokens=400,
                )
                intermediates.append(f"Pages {sp}‑{ep}: {resp.choices[0].message.content.strip()}")
            except Exception as exc:
                logger.error("Chunk %d reduction failed: %s", idx, exc)
                intermediates.append(f"Pages {sp}‑{ep}: {' '.join(chunk[:3])}...")

        if len(intermediates) == 1:
            return intermediates[0].split(": ", 1)[1] if ": " in intermediates[0] else intermediates[0]

        final_combined = "\n\n".join(intermediates)
        return self._single_pass_reduce(final_combined, total_pages)

    def _reduce_to_key_fields(self, page_results: list[dict], file_name: str) -> dict[str, Any]:
        """Reduce page analyses into DocumentSummary‑style key fields."""
        # Aggregate flat entity lists
        agg: dict[str, list[str]] = {"people": [], "organizations": [], "dates": [], "amounts": [], "locations": []}
        topics: list[str] = []
        facts: list[str] = []
        doc_indicators: list[str] = []
        chunk_summaries: list[str] = []

        for r in page_results:
            if r.get("error") or r.get("is_error"):
                continue
            desc = r.get("description", "")
            if desc:
                chunk_summaries.append(desc)
            # Gather entities from EntityItem format into flat lists
            for ent in r.get("entities", []):
                etype = ent.get("type", "")
                ename = ent.get("entity", "")
                if etype == "person":
                    agg["people"].append(ename)
                elif etype == "organization":
                    agg["organizations"].append(ename)
                elif etype == "location":
                    agg["locations"].append(ename)
                elif etype == "date":
                    agg["dates"].append(ename)
            kw = r.get("keywords") or []
            topics.extend(kw)

        # Dedup
        for k in agg:
            agg[k] = list(set(agg[k]))
        topics = list(set(topics))

        input_data = {
            "filename": file_name,
            "chunk_summaries": chunk_summaries[:30],
            "aggregated_entities": agg,
            "aggregated_topics": topics[:30],
        }

        from app.models.document import DocumentKeyFields as _DKF  # noqa: avoid circular at module level

        system_prompt = (
            "You are a document analysis assistant. Create a consolidated DocumentSummary "
            "from the data below. Return valid JSON matching the schema."
        )
        user_prompt = (
            f"Document filename: {file_name}\n\n"
            f"Analysis data:\n{json.dumps(input_data, indent=2)}\n\n"
            "Return a JSON object with keys: title, docType, keyFields (with entities, topics, key_facts, document_purpose, actionable_items)."
        )

        try:
            resp = self._create_chat_completion(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_completion_tokens=1500,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content.strip())
        except Exception as exc:
            logger.error("Key‑fields reduction failed: %s", exc)
            return {
                "title": f"Analysis of {file_name}",
                "docType": "Unknown",
                "keyFields": {
                    "entities": agg,
                    "topics": topics,
                    "key_facts": facts,
                    "document_purpose": "",
                    "actionable_items": [],
                },
            }

    def _create_chat_completion(self, **kwargs: Any) -> Any:
        if self._uses_reasoning_chat_model():
            kwargs.pop("temperature", None)
        return self.client.chat.completions.create(**kwargs)

    def _uses_reasoning_chat_model(self) -> bool:
        normalized = self._model.lower().replace(".", "").replace("-", "")
        return normalized.startswith(("gpt5", "gpt51", "o1", "o3", "o4"))
