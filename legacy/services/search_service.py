"""
Azure AI Search Service for Document Indexing and Hybrid Search

This service manages the Azure AI Search resources needed to index
LLM-generated JSON summaries stored in Azure Blob Storage using a
pull-based indexer with integrated vectorization for hybrid search.
"""

import os
import logging
from typing import Any, Dict, List, Optional

from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    ComplexField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
    SearchIndexerDataSourceConnection,
    SearchIndexerDataContainer,
    SearchIndexer,
    SearchIndexerSkillset,
    FieldMapping,
    IndexingParameters,
    IndexingParametersConfiguration,
    AzureOpenAIEmbeddingSkill,  # noqa: F401 – kept for potential future use
    InputFieldMappingEntry,
    OutputFieldMappingEntry,  # noqa: F401 – kept for potential future use
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
)
from azure.search.documents.models import (
    VectorizableTextQuery,
    QueryType,
)

logger = logging.getLogger(__name__)


class SearchService:
    """Service for managing Azure AI Search index, indexer, and search operations."""

    def __init__(self):
        self._endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        self._index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "llm-summaries")
        self._datasource_name = f"{self._index_name}-datasource"
        self._indexer_name = f"{self._index_name}-indexer"
        self._skillset_name = f"{self._index_name}-skillset"

        # Storage config for blob data source
        self._storage_connection_string = os.getenv("AZURE_SEARCH_STORAGE_CONNECTION_STRING")
        self._storage_container = os.getenv("AZURE_SEARCH_STORAGE_CONTAINER")
        self._storage_blob_prefix = os.getenv("AZURE_SEARCH_BLOB_PREFIX", "")

        # Azure OpenAI config for integrated vectorization
        self._openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self._openai_key = os.getenv("AZURE_OPENAI_KEY")
        self._openai_embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
        self._openai_embedding_deployment = os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", self._openai_embedding_model
        )
        self._openai_model_dimensions = int(os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536"))

        # Build credential
        search_key = os.getenv("AZURE_SEARCH_KEY")
        if search_key:
            self._credential = AzureKeyCredential(search_key)
        else:
            self._credential = DefaultAzureCredential()

    # ------------------------------------------------------------------ #
    #  Clients (lazy)
    # ------------------------------------------------------------------ #

    def _index_client(self) -> SearchIndexClient:
        return SearchIndexClient(endpoint=self._endpoint, credential=self._credential)

    def _indexer_client(self) -> SearchIndexerClient:
        return SearchIndexerClient(endpoint=self._endpoint, credential=self._credential)

    def _search_client(self) -> SearchClient:
        return SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=self._credential,
        )

    # ------------------------------------------------------------------ #
    #  Index definition
    # ------------------------------------------------------------------ #

    def _build_index(self) -> SearchIndex:
        """Build the search index schema for LLM summary documents."""

        fields = [
            SimpleField(
                name="id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SearchableField(
                name="title",
                type=SearchFieldDataType.String,
                analyzer_name="en.microsoft",
            ),
            SimpleField(
                name="docType",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SearchableField(
                name="summary",
                type=SearchFieldDataType.String,
                analyzer_name="en.microsoft",
            ),
            SearchableField(
                name="document_purpose",
                type=SearchFieldDataType.String,
            ),
            SearchableField(
                name="topics",
                type=SearchFieldDataType.String,
                collection=True,
                filterable=True,
                facetable=True,
            ),
            SearchableField(
                name="key_facts",
                type=SearchFieldDataType.String,
                collection=True,
            ),
            SearchableField(
                name="actionable_items",
                type=SearchFieldDataType.String,
                collection=True,
            ),
            # Entity fields (flattened from keyFields.entities)
            SearchableField(
                name="people",
                type=SearchFieldDataType.String,
                collection=True,
                filterable=True,
                facetable=True,
            ),
            SearchableField(
                name="organizations",
                type=SearchFieldDataType.String,
                collection=True,
                filterable=True,
                facetable=True,
            ),
            SearchableField(
                name="locations",
                type=SearchFieldDataType.String,
                collection=True,
                filterable=True,
                facetable=True,
            ),
            SearchableField(
                name="dates",
                type=SearchFieldDataType.String,
                collection=True,
                filterable=True,
            ),
            SearchableField(
                name="amounts",
                type=SearchFieldDataType.String,
                collection=True,
            ),
            # Metadata
            SimpleField(
                name="original_filename",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="processing_timestamp",
                type=SearchFieldDataType.String,
                filterable=True,
                sortable=True,
            ),
            SimpleField(
                name="total_text_length",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
            ),
            # Vector fields for hybrid search (pre-computed in pipeline)
            SearchField(
                name="summary_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self._openai_model_dimensions,
                vector_search_profile_name="vector-profile",
            ),
            SearchField(
                name="purpose_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self._openai_model_dimensions,
                vector_search_profile_name="vector-profile",
            ),
        ]

        # Vector search configuration
        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(name="hnsw-config"),
            ],
            profiles=[
                VectorSearchProfile(
                    name="vector-profile",
                    algorithm_configuration_name="hnsw-config",
                    vectorizer_name="openai-vectorizer",
                ),
            ],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="openai-vectorizer",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=self._openai_endpoint,
                        deployment_name=self._openai_embedding_deployment,
                        model_name=self._openai_embedding_model,
                        api_key=self._openai_key,
                    ),
                ),
            ],
        )

        # Semantic search configuration
        semantic_config = SemanticConfiguration(
            name="default-semantic",
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="title"),
                content_fields=[
                    SemanticField(field_name="summary"),
                    SemanticField(field_name="document_purpose"),
                ],
                keywords_fields=[
                    SemanticField(field_name="topics"),
                    SemanticField(field_name="key_facts"),
                ],
            ),
        )

        return SearchIndex(
            name=self._index_name,
            fields=fields,
            vector_search=vector_search,
            semantic_search=SemanticSearch(configurations=[semantic_config]),
        )

    def _build_chunks_index(self) -> SearchIndex:
        """Build a child index for chunk-level vector search."""
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
            SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, sortable=True, filterable=True),
            SearchableField(name="chunk_text", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SimpleField(name="title", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="docType", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SearchField(
                name="chunk_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self._openai_model_dimensions,
                vector_search_profile_name="vector-profile",
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[
                VectorSearchProfile(
                    name="vector-profile",
                    algorithm_configuration_name="hnsw-config",
                    vectorizer_name="openai-vectorizer",
                ),
            ],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="openai-vectorizer",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=self._openai_endpoint,
                        deployment_name=self._openai_embedding_deployment,
                        model_name=self._openai_embedding_model,
                        api_key=self._openai_key,
                    ),
                ),
            ],
        )

        semantic_config = SemanticConfiguration(
            name="chunk-semantic",
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="title"),
                content_fields=[SemanticField(field_name="chunk_text")],
            ),
        )

        return SearchIndex(
            name=f"{self._index_name}-chunks",
            fields=fields,
            vector_search=vector_search,
            semantic_search=SemanticSearch(configurations=[semantic_config]),
        )

    # ------------------------------------------------------------------ #
    #  Data source
    # ------------------------------------------------------------------ #

    def _build_data_source(self) -> SearchIndexerDataSourceConnection:
        """Create a blob storage data source connection."""
        return SearchIndexerDataSourceConnection(
            name=self._datasource_name,
            type="azureblob",
            connection_string=self._storage_connection_string,
            container=SearchIndexerDataContainer(
                name=self._storage_container,
                query=self._storage_blob_prefix or None,
            ),
        )

    # ------------------------------------------------------------------ #
    #  Skillset (integrated vectorization)
    # ------------------------------------------------------------------ #

    def _build_skillset(self) -> SearchIndexerSkillset:
        """Build a skillset with index projections to split pre-computed chunks into a child index."""
        # No embedding skills needed — vectors are pre-computed in the pipeline.
        # The skillset exists solely for the index projection that fans out chunks.
        return SearchIndexerSkillset(
            name=self._skillset_name,
            description="Project pre-computed document chunks into child index",
            skills=[],
            index_projections=SearchIndexerIndexProjection(
                selectors=[
                    SearchIndexerIndexProjectionSelector(
                        target_index_name=f"{self._index_name}-chunks",
                        parent_key_field_name="parent_id",
                        source_context="/document/chunks/*",
                        mappings=[
                            InputFieldMappingEntry(name="chunk_index", source="/document/chunks/*/chunk_index"),
                            InputFieldMappingEntry(name="chunk_text", source="/document/chunks/*/text"),
                            InputFieldMappingEntry(name="chunk_vector", source="/document/chunks/*/vector"),
                            InputFieldMappingEntry(name="title", source="/document/title"),
                            InputFieldMappingEntry(name="docType", source="/document/docType"),
                        ],
                    ),
                ],
                parameters=SearchIndexerIndexProjectionsParameters(
                    projection_mode="generatedKeyAsId",
                ),
            ),
        )

    # ------------------------------------------------------------------ #
    #  Indexer
    # ------------------------------------------------------------------ #

    def _build_indexer(self) -> SearchIndexer:
        """Build the indexer that connects data source → skillset → index."""

        field_mappings = [
            FieldMapping(
                source_field_name="metadata_storage_path",
                target_field_name="id",
                mapping_function={"name": "base64Encode"},
            ),
        ]

        return SearchIndexer(
            name=self._indexer_name,
            data_source_name=self._datasource_name,
            target_index_name=self._index_name,
            skillset_name=self._skillset_name,
            field_mappings=field_mappings,
            parameters=IndexingParameters(
                configuration=IndexingParametersConfiguration(
                    parsing_mode="json",
                    query_timeout=None,
                ),
            ),
        )

    # ------------------------------------------------------------------ #
    #  Setup (create / update all resources)
    # ------------------------------------------------------------------ #

    def setup(self) -> Dict[str, str]:
        """Create or update the data source, index, skillset, and indexer."""
        results = {}

        # 1. Index (document-level)
        index_client = self._index_client()
        index_def = self._build_index()
        index_client.create_or_update_index(index_def)
        results["index"] = self._index_name
        logger.info(f"Index '{self._index_name}' created/updated")

        # 1b. Chunks index (chunk-level)
        chunks_index_def = self._build_chunks_index()
        index_client.create_or_update_index(chunks_index_def)
        chunks_index_name = f"{self._index_name}-chunks"
        results["chunks_index"] = chunks_index_name
        logger.info(f"Chunks index '{chunks_index_name}' created/updated")

        # 2. Data source
        indexer_client = self._indexer_client()
        ds = self._build_data_source()
        indexer_client.create_or_update_data_source_connection(ds)
        results["data_source"] = self._datasource_name
        logger.info(f"Data source '{self._datasource_name}' created/updated")

        # 3. Skillset
        skillset = self._build_skillset()
        indexer_client.create_or_update_skillset(skillset)
        results["skillset"] = self._skillset_name
        logger.info(f"Skillset '{self._skillset_name}' created/updated")

        # 4. Indexer
        indexer = self._build_indexer()
        indexer_client.create_or_update_indexer(indexer)
        results["indexer"] = self._indexer_name
        logger.info(f"Indexer '{self._indexer_name}' created/updated")

        return results

    # ------------------------------------------------------------------ #
    #  Indexer operations
    # ------------------------------------------------------------------ #

    def run_indexer(self) -> None:
        """Trigger an on-demand indexer run."""
        client = self._indexer_client()
        client.run_indexer(self._indexer_name)
        logger.info(f"Indexer '{self._indexer_name}' triggered")

    def get_indexer_status(self) -> Dict[str, Any]:
        """Get current indexer status and execution history."""
        client = self._indexer_client()
        status = client.get_indexer_status(self._indexer_name)

        last_result = None
        if status.last_result:
            last_result = {
                "status": str(status.last_result.status),
                "error_message": status.last_result.error_message,
                "item_count": status.last_result.item_count,
                "failed_item_count": status.last_result.failed_item_count,
                "start_time": status.last_result.start_time.isoformat() if status.last_result.start_time else None,
                "end_time": status.last_result.end_time.isoformat() if status.last_result.end_time else None,
            }

        return {
            "name": self._indexer_name,
            "status": str(status.status),
            "last_result": last_result,
        }

    def reset_indexer(self) -> None:
        """Reset the indexer so it re-processes all documents."""
        client = self._indexer_client()
        client.reset_indexer(self._indexer_name)
        logger.info(f"Indexer '{self._indexer_name}' reset")

    # ------------------------------------------------------------------ #
    #  Search
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        *,
        search_mode: str = "hybrid",
        filters: Optional[str] = None,
        top: int = 10,
        select: Optional[List[str]] = None,
        facets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a search query against the index.

        Args:
            query: The search text.
            search_mode: One of 'fulltext', 'vector', or 'hybrid'.
            filters: OData filter expression.
            top: Maximum results to return.
            select: Fields to include in results.
            facets: Fields to facet on.

        Returns:
            Dict with results list and optional facet data.
        """
        client = self._search_client()

        kwargs: Dict[str, Any] = {
            "search_text": query if search_mode in ("fulltext", "hybrid") else None,
            "filter": filters,
            "top": top,
            "select": select or [
                "id", "title", "docType", "summary", "document_purpose",
                "topics", "people", "organizations", "locations",
                "original_filename", "processing_timestamp",
            ],
            "facets": facets,
        }

        # Add vector query for vector / hybrid modes
        if search_mode in ("vector", "hybrid"):
            kwargs["vector_queries"] = [
                VectorizableTextQuery(
                    text=query,
                    k_nearest_neighbors=top,
                    fields="summary_vector,purpose_vector",
                ),
            ]

        # Use semantic ranking for hybrid
        if search_mode == "hybrid":
            kwargs["query_type"] = QueryType.SEMANTIC
            kwargs["semantic_configuration_name"] = "default-semantic"

        response = client.search(**kwargs)

        results = []
        for doc in response:
            item = {k: v for k, v in doc.items() if k != "@search.score"}
            item["score"] = doc.get("@search.score")
            item["reranker_score"] = doc.get("@search.reranker_score")
            results.append(item)

        output: Dict[str, Any] = {"results": results, "count": len(results)}

        if response.get_facets():
            output["facets"] = {
                k: [{"value": f.value, "count": f.count} for f in v]
                for k, v in response.get_facets().items()
            }

        return output

    def search_chunks(
        self,
        query: str,
        *,
        search_mode: str = "hybrid",
        filters: Optional[str] = None,
        top: int = 10,
    ) -> Dict[str, Any]:
        """Search the chunks index for granular passage-level retrieval.

        Returns matching text chunks with their parent document IDs for
        RAG grounding or precise document section retrieval.
        """
        chunks_index = f"{self._index_name}-chunks"
        client = SearchClient(
            endpoint=self._endpoint,
            index_name=chunks_index,
            credential=self._credential,
        )

        kwargs: Dict[str, Any] = {
            "search_text": query if search_mode in ("fulltext", "hybrid") else None,
            "filter": filters,
            "top": top,
            "select": ["id", "parent_id", "chunk_index", "chunk_text", "title", "docType"],
        }

        if search_mode in ("vector", "hybrid"):
            kwargs["vector_queries"] = [
                VectorizableTextQuery(
                    text=query,
                    k_nearest_neighbors=top,
                    fields="chunk_vector",
                ),
            ]

        if search_mode == "hybrid":
            kwargs["query_type"] = QueryType.SEMANTIC
            kwargs["semantic_configuration_name"] = "chunk-semantic"

        response = client.search(**kwargs)

        results = []
        for doc in response:
            item = {k: v for k, v in doc.items() if k != "@search.score"}
            item["score"] = doc.get("@search.score")
            item["reranker_score"] = doc.get("@search.reranker_score")
            results.append(item)

        return {"results": results, "count": len(results)}
