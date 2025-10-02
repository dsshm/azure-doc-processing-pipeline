import logging
import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import azure.functions as func

# Import service classes instead of direct Azure SDK usage
from services import ADLSService, CosmosService
import openai
from pydantic import BaseModel, Field

bp_doc_llm = func.Blueprint()
 
# Reuse DI pipeline from bp_docIntel for combined flow
from bp_docIntel import process_single_pdf


# Pydantic models for structured LLM output
class EntityData(BaseModel):
    """Extracted entities from document chunk."""
    people: List[str] = Field(default_factory=list, description="Names of people mentioned")
    organizations: List[str] = Field(default_factory=list, description="Organizations mentioned")
    dates: List[str] = Field(default_factory=list, description="Important dates")
    amounts: List[str] = Field(default_factory=list, description="Monetary amounts or quantities")
    locations: List[str] = Field(default_factory=list, description="Geographic locations")


class ChunkAnalysis(BaseModel):
    """Analysis result for a single text chunk."""
    summary: str = Field(description="Brief summary of this chunk's content")
    entities: EntityData = Field(description="Extracted entities from the chunk")
    topics: List[str] = Field(default_factory=list, description="Main topics and themes")
    key_facts: List[str] = Field(default_factory=list, description="Important facts and details")
    doc_type_indicators: List[str] = Field(default_factory=list, description="Indicators of document type")


class DocumentKeyFields(BaseModel):
    """Key fields extracted from the entire document."""
    entities: EntityData = Field(description="Key entities from the document")
    topics: List[str] = Field(default_factory=list, description="Main topics and themes")
    key_facts: List[str] = Field(default_factory=list, description="Most important facts")
    document_purpose: str = Field(description="What this document is for")
    actionable_items: List[str] = Field(default_factory=list, description="Actions, requirements, or next steps")


class DocumentSummary(BaseModel):
    """Final consolidated document analysis."""
    title: str = Field(description="Descriptive title for the document")
    docType: str = Field(description="Type of document (e.g., contract, invoice, report, letter)")
    summary: str = Field(description="Comprehensive 2-3 paragraph summary of the entire document")
    keyFields: DocumentKeyFields = Field(description="Structured key information from the document")


def load_di_analysis_from_adls(case_id: str, file_id: str) -> Dict[str, Any]:
    """Load Document Intelligence analysis results from ADLS."""
    try:
        # Use ADLS service instead of direct client
        adls_service = ADLSService()
        if not adls_service.is_configured():
            raise ValueError("ADLS service not configured")
        
        # Path: cases/{caseId}/derived/di/v1/{fileId}/analyze.json
        di_path = f"{case_id}/derived/di/v1/{file_id}/analyze.json"
        
        # Use service method to download file
        file_content = adls_service.download_file(di_path)
        if file_content is None:
            raise FileNotFoundError(f"DI analysis file not found: {di_path}")
        
        di_data = json.loads(file_content.decode('utf-8'))
        logging.info(f"Successfully loaded DI analysis from {di_path}")
        return di_data
        
    except Exception as e:
        logging.error(f"Failed to load DI analysis for case {case_id}, file {file_id}: {e}")
        raise


def extract_text_content(di_data: Dict[str, Any]) -> str:
    """Extract main text content from Document Intelligence analysis."""
    try:
        # Primary source: main content field
        content = di_data.get("content", "")
        
        # Fallback: extract from key-value pairs and tables if content is empty
        if not content.strip():
            text_parts = []
            
            # Extract from key-value pairs
            kv_pairs = di_data.get("key_value_pairs", [])
            for kv in kv_pairs:
                key = kv.get("key", "").strip()
                value = kv.get("value", "").strip()
                if key and value:
                    text_parts.append(f"{key}: {value}")
            
            # Extract from tables
            tables = di_data.get("tables", [])
            for table in tables:
                cells = table.get("cells", [])
                table_text = []
                for cell in cells:
                    cell_content = cell.get("content", "").strip()
                    if cell_content:
                        table_text.append(cell_content)
                if table_text:
                    text_parts.append(" | ".join(table_text))
            
            content = "\n".join(text_parts)
        
        logging.info(f"Extracted {len(content)} characters of text content")
        return content
        
    except Exception as e:
        logging.error(f"Failed to extract text content: {e}")
        return ""


def chunk_text(text: str, chunk_size: int = 3500, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks for LLM processing."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # If not the last chunk, try to break at word boundary
        if end < len(text):
            # Look for last space within reasonable distance
            space_pos = text.rfind(' ', start, end)
            if space_pos > start + chunk_size - 200:  # Within 200 chars of target
                end = space_pos
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start position with overlap
        start = end - overlap
        if start >= len(text):
            break
    
    logging.info(f"Split text into {len(chunks)} chunks (avg size: {len(text)//len(chunks) if chunks else 0})")
    return chunks


async def analyze_chunk_with_llm(chunk: str, chunk_index: int, total_chunks: int) -> Dict[str, Any]:
    """Analyze a text chunk using LLM for summarization and metadata extraction."""
    try:
        # Configure OpenAI client
        openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_key = os.getenv("AZURE_OPENAI_KEY")
        openai_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        model_name = os.getenv("AZURE_OPENAI_MODEL_NAME", "gpt-4")
        
        if not openai_endpoint or not openai_key:
            raise ValueError("Azure OpenAI configuration missing")
        
        client = openai.AzureOpenAI(
            azure_endpoint=openai_endpoint,
            api_key=openai_key,
            api_version=openai_version
        )
        
        # System prompt for chunk analysis
        system_prompt = """You are a document analysis assistant. Analyze the given text chunk and extract:
            1. Key entities (people, organizations, dates, amounts, etc.)
            2. Main topics and themes
            3. Important facts and details
            4. Document type indicators
            5. Brief summary of this chunk's content

            Focus on accuracy and completeness. Extract all relevant information from the text."""

        user_prompt = f"""Chunk {chunk_index + 1} of {total_chunks}:

            {chunk}

            Analyze this text chunk and extract the structured information."""

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=1000,
            response_format={
                "type": "json_schema", 
                "json_schema": {
                    "name": "chunk_analysis", 
                    "schema": ChunkAnalysis.model_json_schema()
                }
            }
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Parse the structured response
        try:
            chunk_data = json.loads(response_text)
            validated_result = ChunkAnalysis.model_validate(chunk_data)
            
            # Convert to dict and add metadata
            result = validated_result.model_dump()
            result["chunk_index"] = chunk_index
            result["chunk_text_length"] = len(chunk)
            
            return result
            
        except (json.JSONDecodeError, ValueError) as e:
            logging.warning(f"Failed to parse structured response for chunk {chunk_index}: {e}")
            # Fallback to basic structure
            return {
                "summary": f"Error parsing chunk {chunk_index} response",
                "entities": {"people": [], "organizations": [], "dates": [], "amounts": [], "locations": []},
                "topics": [],
                "key_facts": [],
                "doc_type_indicators": [],
                "chunk_index": chunk_index,
                "chunk_text_length": len(chunk),
                "parse_error": True
            }
        
    except Exception as e:
        logging.error(f"Failed to analyze chunk {chunk_index} with LLM: {e}")
        return {
            "summary": f"Error analyzing chunk {chunk_index}",
            "entities": {"people": [], "organizations": [], "dates": [], "amounts": [], "locations": []},
            "topics": [],
            "key_facts": [],
            "doc_type_indicators": [],
            "chunk_index": chunk_index,
            "chunk_text_length": len(chunk),
            "error": str(e)
        }


async def reduce_chunk_analyses(chunk_results: List[Dict[str, Any]], original_filename: str) -> Dict[str, Any]:
    """Merge chunk analyses into a single normalized summary using LLM."""
    try:
        # Configure OpenAI client
        openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_key = os.getenv("AZURE_OPENAI_KEY")
        openai_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        model_name = os.getenv("AZURE_OPENAI_MODEL_NAME", "gpt-4")
        
        client = openai.AzureOpenAI(
            azure_endpoint=openai_endpoint,
            api_key=openai_key,
            api_version=openai_version
        )
        
        # Prepare chunk summaries for reduction
        chunk_summaries = []
        all_entities = {"people": [], "organizations": [], "dates": [], "amounts": [], "locations": []}
        all_topics = []
        all_facts = []
        all_doc_indicators = []
        
        for result in chunk_results:
            if not result.get("error"):
                chunk_summaries.append(f"Chunk {result.get('chunk_index', 0)}: {result.get('summary', '')}")
                
                # Aggregate entities
                entities = result.get("entities", {})
                for entity_type, entity_list in all_entities.items():
                    entity_list.extend(entities.get(entity_type, []))
                
                all_topics.extend(result.get("topics", []))
                all_facts.extend(result.get("key_facts", []))
                all_doc_indicators.extend(result.get("doc_type_indicators", []))
        
        # Deduplicate lists
        for entity_type in all_entities:
            all_entities[entity_type] = list(set(all_entities[entity_type]))
        all_topics = list(set(all_topics))
        all_facts = list(set(all_facts))
        all_doc_indicators = list(set(all_doc_indicators))
        
        # System prompt for reduction
        system_prompt = """You are a document analysis assistant. You will receive chunk-by-chunk analyses 
            of a document and must create a final consolidated summary.

            Create a comprehensive document summary that consolidates all the information from the individual 
            chunks. Focus on the most important and relevant information. Prioritize quality over quantity.

            The summary should provide a clear understanding of what the document is about, its purpose, and 
            the key information it contains."""

        # Prepare input for reduction
        chunk_data = {
            "filename": original_filename,
            "total_chunks": len(chunk_results),
            "chunk_summaries": chunk_summaries,
            "aggregated_entities": all_entities,
            "aggregated_topics": all_topics,
            "aggregated_facts": all_facts,
            "doc_type_indicators": all_doc_indicators
        }
        
        user_prompt = f"""Document filename: {original_filename}

            Chunk-by-chunk analysis results:
            {json.dumps(chunk_data, indent=2)}

            Create a final consolidated document summary from this analysis data."""

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={
                "type": "json_schema", 
                "json_schema": {
                    "name": "document_summary", 
                    "schema": DocumentSummary.model_json_schema()
                }
            }
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Parse the structured response
        try:
            summary_data = json.loads(response_text)
            validated_summary = DocumentSummary.model_validate(summary_data)
            
            # Convert to dict and add metadata
            final_result = validated_summary.model_dump()
            final_result["metadata"] = {
                "processed_chunks": len(chunk_results),
                "successful_chunks": len([r for r in chunk_results if not r.get("error")]),
                "total_text_length": sum(r.get("chunk_text_length", 0) for r in chunk_results),
                "processing_timestamp": datetime.utcnow().isoformat() + 'Z',
                "original_filename": original_filename
            }
            
            return final_result
            
        except (json.JSONDecodeError, ValueError) as e:
            logging.warning(f"Failed to parse structured summary response: {e}")
            # Fallback structure
            return {
                "title": f"Analysis of {original_filename}",
                "docType": "Unknown",
                "summary": response_text if response_text else "Unable to generate summary",
                "keyFields": {
                    "entities": all_entities,
                    "topics": all_topics,
                    "key_facts": all_facts,
                    "document_purpose": "Unable to determine",
                    "actionable_items": []
                },
                "metadata": {
                    "processed_chunks": len(chunk_results),
                    "successful_chunks": len([r for r in chunk_results if not r.get("error")]),
                    "processing_timestamp": datetime.utcnow().isoformat() + 'Z',
                    "original_filename": original_filename,
                    "parse_error": True
                }
            }
        
    except Exception as e:
        logging.error(f"Failed to reduce chunk analyses: {e}")
        return {
            "title": f"Analysis of {original_filename}",
            "docType": "Unknown",
            "summary": f"Error during analysis reduction: {str(e)}",
            "keyFields": {
                "entities": {"people": [], "organizations": [], "dates": [], "amounts": [], "locations": []},
                "topics": [],
                "key_facts": [],
                "document_purpose": "Unable to determine",
                "actionable_items": []
            },
            "metadata": {
                "processed_chunks": len(chunk_results),
                "processing_timestamp": datetime.utcnow().isoformat() + 'Z',
                "original_filename": original_filename,
                "error": str(e)
            }
        }


def save_llm_summary_to_adls(case_id: str, file_id: str, summary_data: Dict[str, Any]) -> str:
    """Save LLM analysis summary to ADLS."""
    try:
        # Use ADLS service instead of direct client
        adls_service = ADLSService()
        if not adls_service.is_configured():
            raise ValueError("ADLS service not configured")
        
        # Path: cases/{caseId}/derived/llm/v1/{fileId}/summary.json
        llm_path = f"{case_id}/derived/llm/v1/{file_id}"
        file_path = f"{llm_path}/summary.json"
        
        # Convert to JSON string
        json_data = json.dumps(summary_data, indent=2)
        
        # Use service method to upload file
        success = adls_service.upload_file(file_path, json_data.encode("utf-8"))
        if not success:
            raise Exception("Failed to upload LLM summary to ADLS")
        
        logging.info(f"LLM summary saved to: {file_path}")
        return file_path
        
    except Exception as e:
        logging.error(f"Failed to save LLM summary to ADLS: {e}")
        raise


def _map_status(status_in: str) -> str:
    """Map internal status to external controlled vocabulary."""
    status_map = {
        "success": "completed",
        "processing": "in_progress",
        "partial_success": "partial",
        "failed": "failed",
        "completed": "completed"
    }
    return status_map.get(status_in, status_in)


def _build_full_adls_url_from_path(container_relative_path: str) -> Optional[str]:
    """Construct full ADLS URL using ADLSService configuration and a container-relative path."""
    try:
        adls_service = ADLSService()
        if not adls_service.is_configured():
            return None
        account_url = getattr(adls_service, '_account_url', None)
        container = getattr(adls_service, '_container_name', None)
        if not account_url or not container:
            return None
        # account_url may already include https://<account>.dfs.core.windows.net
        # Construct canonical URL: {account_url}/{container}/{container_relative_path}
        # Ensure no leading slash on container_relative_path
        relative = container_relative_path.lstrip('/')
        return f"{account_url}/{container}/{relative}"
    except Exception:
        return None


def _extract_attachments_from_case(case_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Robustly extract attachments list from a case document supporting common key variants."""
    if not isinstance(case_doc, dict):
        return []
    # Preferred canonical key
    if 'attachments' in case_doc and case_doc.get('attachments'):
        return case_doc.get('attachments')
    # Common alternatives (including historic typo)
    for key in ('attachements', 'files', 'documents', 'attachments_metadata'):
        if key in case_doc and case_doc.get(key):
            return case_doc.get(key)
    return []


def update_case_attachment_with_llm_analysis(case_id: str, file_id: str, status: str, version: int, summary_json_path: str, full_json_path: str = None):
    """Update the case attachment with LLM analysis artifact references."""
    try:
        cosmos_service = CosmosService()
        
        # Read the existing case
        case_doc = cosmos_service.get_case_or_record(case_id=case_id)
        if not case_doc:
            raise ValueError(f"Case {case_id} not found")
        # Find and update the attachment with the matching fileId
        attachments = case_doc.get("attachments", [])
        updated = False

        for attachment in attachments:
            if attachment.get("fileId") == file_id:
                # Construct full ADLS URL for summary path where possible
                full_summary_url = _build_full_adls_url_from_path(summary_json_path) or summary_json_path
                artifact_paths = {"summary": summary_json_path}
                if full_json_path:
                    artifact_paths["full"] = full_json_path

                # Ensure analysis slot exists and write unified analysis.llm section
                if "analysis" not in attachment:
                    attachment["analysis"] = {}

                attachment["analysis"]["llm"] = {
                    "latestId": f"analysis:{case_id}:{file_id}:v{version}:llm",
                    "status": _map_status(status),
                    "version": version,
                    "generatedAt": datetime.utcnow().isoformat() + 'Z',
                    "path": full_summary_url,
                    "artifactPaths": artifact_paths
                }
                updated = True
                break

        if not updated:
            logging.warning(f"No attachment found with fileId {file_id} in case {case_id}")
            return False

        # Update the case document (write back full attachments array)
        case_doc["attachments"] = attachments
        result = cosmos_service.upsert_item(case_doc)
        if not result:
            raise Exception("Failed to update case document")

        logging.info(f"Successfully updated case {case_id} with LLM analysis references for fileId {file_id}")

        # Also create/update a separate analysis item in Cosmos for LLM artifacts
        try:
            analysis_item = {
                "id": f"analysis:{case_id}:{file_id}:v{version}:llm",
                "caseId": case_id,
                "fileId": file_id,
                "kind": "llm",
                "version": version,
                "status": _map_status(status),
                "paths": {"summary": summary_json_path},
                "createdAt": datetime.utcnow().isoformat() + 'Z'
            }
            if full_json_path:
                analysis_item["paths"]["full"] = full_json_path
            cosmos_service.upsert_item(analysis_item)
        except Exception as e:
            logging.warning(f"Failed to upsert LLM analysis item for {case_id}/{file_id}: {e}")

        return True
        
    except Exception as e:
        logging.error(f"Failed to update case {case_id} for LLM analysis fileId {file_id}: {e}")
        raise


async def process_single_file_llm_analysis(case_id: str, attachment: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single file through LLM analysis pipeline."""
    file_id = attachment.get("fileId")
    filename = attachment.get("name", "unknown")
    
    if not file_id:
        return {
            "fileId": None,
            "filename": filename,
            "status": "error",
            "error": "Missing fileId in attachment"
        }
    
    try:
        # Check if LLM analysis already exists
        analysis = attachment.get("analysis", {})
        if "llm" in analysis:
            logging.info(f"LLM analysis already exists for fileId {file_id}, skipping")
            return {
                "fileId": file_id,
                "filename": filename,
                "status": "skipped",
                "reason": "LLM analysis already exists",
                "existingAnalysisId": analysis["llm"].get("latestId")
            }
        
        # Check if DI analysis exists
        if "di" not in analysis:
            logging.info(f"No DI analysis found for fileId {file_id}, skipping LLM analysis")
            return {
                "fileId": file_id,
                "filename": filename,
                "status": "skipped",
                "reason": "No DI analysis found"
            }
        
        # Generate LLM analysis ID
        llm_analysis_id = f"analysis:{case_id}:{file_id}:v1:llm"
        
        # Step 1: Load DI analysis from ADLS
        di_data = load_di_analysis_from_adls(case_id, file_id)
        
        # Step 2: Extract text content
        text_content = extract_text_content(di_data)
        if not text_content.strip():
            raise ValueError("No text content found in DI analysis")
        
        # Step 3: Chunk text
        chunks = chunk_text(text_content)
        
        # Step 4: Analyze each chunk with LLM
        chunk_results = []
        for i, chunk in enumerate(chunks):
            chunk_result = await analyze_chunk_with_llm(chunk, i, len(chunks))
            chunk_results.append(chunk_result)
        
        # Step 5: Reduce chunk analyses into final summary
        final_summary = await reduce_chunk_analyses(chunk_results, filename)
        
        # Step 6: Save summary to ADLS
        summary_path = save_llm_summary_to_adls(case_id, file_id, final_summary)
        
        # Step 7: Update case attachment with analysis references
        update_case_attachment_with_llm_analysis(case_id, file_id, "completed", 1, summary_path)

        # DEMO: set top-level file_analysis flag on the parent case record
        try:
            cosmos_service = CosmosService()
            case_doc = cosmos_service.get_case_or_record(case_id=case_id)
            if case_doc and isinstance(case_doc, dict):
                case_doc["file_analysis"] = "completed"
                try:
                    cosmos_service.upsert_item(case_doc)
                    logging.info(f"Set demo top-level file_analysis='completed' on case {case_id}")
                except Exception as upsert_err:
                    logging.warning(f"Failed to upsert demo file_analysis for case {case_id}: {upsert_err}")
        except Exception as demo_err:
            logging.warning(f"Failed to set demo file_analysis for case {case_id}: {demo_err}")
        
        return {
            "fileId": file_id,
            "filename": filename,
            "llmAnalysisId": llm_analysis_id,
            "status": "success",
            "summaryPath": summary_path,
            "processedChunks": len(chunks),
            "textLength": len(text_content)
        }
        
    except Exception as e:
        logging.error(f"Failed to process LLM analysis for fileId {file_id}: {e}")
        
        # Try to update case attachment with failed status
        try:
            update_case_attachment_with_llm_analysis(case_id, file_id, "failed", 1, "")
        except Exception as cosmos_error:
            logging.error(f"Failed to update case with LLM failure status: {cosmos_error}")
        
        return {
            "fileId": file_id,
            "filename": filename,
            "llmAnalysisId": f"analysis:{case_id}:{file_id}:v1:llm",
            "status": "failed",
            "error": str(e)
        }


@bp_doc_llm.route("doc_llm", methods=["POST"])
async def doc_llm_processing(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP-triggered function for LLM analysis of document attachments."""
    logging.info("Processing LLM analysis request.")
    
    try:
        body = req.get_json()
        logging.info(f"Request body keys: {list(body.keys()) if body else 'None'}")
        
        if not body:
            return func.HttpResponse("Missing request body", status_code=400)
        
        case_id = body.get("caseId")
        if not case_id:
            return func.HttpResponse("Missing caseId in request", status_code=400)
        
        attachments = body.get("attachments")
        if not attachments:
            # If attachments not supplied, fetch case record from Cosmos and extract attachments
            try:
                cosmos_service = CosmosService()
                case_doc = cosmos_service.get_case_or_record(case_id=case_id)
                if not case_doc:
                    return func.HttpResponse(json.dumps({"error": "case not found", "caseId": case_id}), status_code=404, mimetype="application/json")
                attachments = _extract_attachments_from_case(case_doc)
                logging.info(f"Fetched {len(attachments)} attachments from case {case_id} (Cosmos)")
            except Exception as e:
                logging.error(f"Failed to read case {case_id} from Cosmos: {e}")
                return func.HttpResponse(json.dumps({"error": "failed to read case", "detail": str(e)}), status_code=500, mimetype="application/json")

        if not attachments:
            return func.HttpResponse(
                body=json.dumps({"message": "No attachments found to process", "caseId": case_id}),
                status_code=200,
                mimetype="application/json"
            )
        
        logging.info(f"Processing LLM analysis for case {case_id} with {len(attachments)} attachments")
        
        # Process each attachment
        results = []
        for attachment in attachments:
            result = await process_single_file_llm_analysis(case_id, attachment)
            results.append(result)
        
        # Prepare summary response
        successful_count = len([r for r in results if r.get("status") == "success"])
        skipped_count = len([r for r in results if r.get("status") == "skipped"])
        failed_count = len([r for r in results if r.get("status") == "failed"])
        
        response_data = {
            "caseId": case_id,
            "totalAttachments": len(attachments),
            "processedFiles": successful_count,
            "skippedFiles": skipped_count,
            "failedFiles": failed_count,
            "results": results,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
        logging.info(f"LLM analysis completed: {successful_count} successful, {skipped_count} skipped, {failed_count} failed")
        
        return func.HttpResponse(
            body=json.dumps(response_data, indent=2),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.exception(f"Unexpected error in LLM processing: {e}")
        return func.HttpResponse(f"Internal server error: {str(e)}", status_code=500)


def _upsert_combined_analysis_reference(case_id: str, file_id: str, di_path: str | None, llm_path: str | None, version: int = 1) -> bool:
    """
    Create/update a simple combined 'analysis' reference on the attachment and create a Cosmos analysis item.
    Writes attachment['analysis']['combined'] = {"di": di_path, "llm": llm_path, "version": version, "updatedAt": ...}
    and also creates an analysis item with kind 'combined'.
    """
    try:
        cosmos_service = CosmosService()
        case_doc = cosmos_service.get_case_or_record(case_id=case_id)
        if not case_doc:
            logging.warning(f"Case {case_id} not found when writing combined analysis reference")
            return False

        attachments = case_doc.get("attachments", [])
        updated = False
        for attachment in attachments:
            if attachment.get("fileId") == file_id:
                if "analysis" not in attachment:
                    attachment["analysis"] = {}

                attachment["analysis"].setdefault("combined", {})
                attachment["analysis"]["combined"].update({
                    "di": di_path or "",
                    "llm": llm_path or "",
                    "version": version,
                    "updatedAt": datetime.utcnow().isoformat() + 'Z'
                })
                updated = True
                break

        if not updated:
            logging.warning(f"No attachment found with fileId {file_id} in case {case_id} while upserting combined analysis")
            return False

        case_doc["attachments"] = attachments
        result = cosmos_service.upsert_item(case_doc)
        if not result:
            raise Exception("Failed to upsert case document with combined analysis")

        # Also create/update a separate Cosmos analysis item for combined references
        try:
            analysis_item = {
                "id": f"analysis:{case_id}:{file_id}:v{version}:combined",
                "caseId": case_id,
                "fileId": file_id,
                "kind": "combined",
                "version": version,
                "status": "completed",
                "paths": {"di": di_path or "", "llm": llm_path or ""},
                "createdAt": datetime.utcnow().isoformat() + 'Z'
            }
            cosmos_service.upsert_item(analysis_item)
        except Exception as ex:
            logging.warning(f"Failed to upsert combined analysis item for {case_id}/{file_id}: {ex}")

        logging.info(f"Upserted combined analysis reference for case {case_id} file {file_id}")
        return True

    except Exception as e:
        logging.error(f"Failed to upsert combined analysis reference: {e}")
        return False


@bp_doc_llm.route("doc_full", methods=["POST"])
async def doc_full_processing(req: func.HttpRequest) -> func.HttpResponse:
    """
    New combined endpoint: run Document Intelligence (DI) then LLM analysis in-band and write a simple combined
    analysis reference into the case attachment.

    Request shapes supported:
      - { "caseId": "<id>", "attachments": [ { "fileId": "...", "name": "...", "path": "..." }, ... ] }
      - { "caseId": "<id>" }  (will fetch attachments from Cosmos and process them)
    """
    logging.info("Processing combined DI + LLM request (doc_full).")

    try:
        body = req.get_json()
        if not body:
            return func.HttpResponse("Missing request body", status_code=400)

        case_id = body.get("caseId")
        if not case_id:
            return func.HttpResponse("Missing caseId in request", status_code=400)

        attachments = body.get("attachments")
        if not attachments:
            # Fetch case from Cosmos and extract attachments
            try:
                cosmos_service = CosmosService()
                case_doc = cosmos_service.get_case_or_record(case_id=case_id)
                if not case_doc:
                    return func.HttpResponse(json.dumps({"error": "case not found", "caseId": case_id}), status_code=404, mimetype="application/json")
                attachments = _extract_attachments_from_case(case_doc)
                logging.info(f"Fetched {len(attachments)} attachments from case {case_id} (Cosmos)")
            except Exception as e:
                logging.error(f"Failed to read case {case_id} from Cosmos: {e}")
                return func.HttpResponse(json.dumps({"error": "failed to read case", "detail": str(e)}), status_code=500, mimetype="application/json")

        if not attachments:
            return func.HttpResponse(body=json.dumps({"message": "No attachments found to process", "caseId": case_id}), status_code=200, mimetype="application/json")

        results = []
        for att in attachments:
            attachment_name = att.get("name") or att.get("filename") or "unknown"
            document_path = att.get("path") or ""
            file_id = att.get("fileId") or (str(uuid.uuid4())[:6])

            if not document_path:
                err = {"fileId": file_id, "filename": attachment_name, "status": "failed", "error": "Missing attachment path"}
                logging.error(f"Skipping attachment {attachment_name}: missing path")
                results.append(err)
                continue

            logging.info(f"Starting DI for {attachment_name} (fileId: {file_id})")
            try:
                # Call existing DI pipeline which downloads, analyzes, writes ADLS, updates cosmos (di)
                di_result = await process_single_pdf(document_path, attachment_name, case_id=case_id, file_id=file_id)
                di_path = di_result.get("storage_path") or di_result.get("storage_path", "")
            except Exception as di_ex:
                logging.error(f"DI processing failed for {attachment_name}: {di_ex}")
                results.append({
                    "fileId": file_id,
                    "filename": attachment_name,
                    "status": "failed",
                    "stage": "di",
                    "error": str(di_ex)
                })
                continue

            # Prepare a minimal attachment entry expected by the LLM pipeline
            attachment_for_llm = {
                "fileId": file_id,
                "name": attachment_name,
                # ensure there is an 'analysis' key containing a 'di' marker so LLM flow proceeds
                "analysis": {
                    "di": {
                        "path": di_path
                    }
                }
            }

            logging.info(f"Starting LLM analysis for {attachment_name} (fileId: {file_id})")
            try:
                llm_result = await process_single_file_llm_analysis(case_id, attachment_for_llm)
                llm_path = llm_result.get("summaryPath", "")
                status = llm_result.get("status", "failed")
            except Exception as llm_ex:
                logging.error(f"LLM processing failed for {attachment_name}: {llm_ex}")
                llm_result = {"status": "failed", "error": str(llm_ex)}
                llm_path = ""
                status = "failed"

            # Upsert the combined reference into the case attachment and create a combined analysis item
            try:
                _upsert_combined_analysis_reference(case_id, file_id, di_path, llm_path, version=1)
            except Exception as combined_ex:
                logging.warning(f"Failed to upsert combined analysis reference for {file_id}: {combined_ex}")

            results.append({
                "fileId": file_id,
                "filename": attachment_name,
                "diPath": di_path,
                "llmPath": llm_path,
                "status": status,
                "llmResult": llm_result
            })

        summary = {
            "caseId": case_id,
            "processed": len([r for r in results if r.get("status") == "success"]),
            "failed": len([r for r in results if r.get("status") != "success"]),
            "results": results,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }

        return func.HttpResponse(body=json.dumps(summary, indent=2), status_code=200, mimetype="application/json")

    except Exception as e:
        logging.exception(f"Unexpected error in combined processing: {e}")
        return func.HttpResponse(f"Internal server error: {str(e)}", status_code=500)