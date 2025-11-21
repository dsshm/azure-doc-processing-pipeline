import logging
import os
import json
import tiktoken
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
import openai
from pydantic import BaseModel, Field

import azure.functions as func

from services import BlobService, DocumentSummarizer

bp_llm = func.Blueprint()



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
  "event"
]

### - Field Models - ###
# Evidence for categories
class CategoryEvidence(BaseModel):
  category: Categories = Field(..., description="The category that applies to the evidence.")
  confidence: float = Field(..., description="The confidence score of the evidence.")
  supporting_evidence: list[str] = Field(..., description="A list of supporting evidence for the category.")

# Evidence for entities
class EntityEvidence(BaseModel):
  quote: str = Field(..., description="The quoted text from the input that supports the entity.")
  start_char: int = Field(..., description="The starting character index of the quoted text.")
  end_char: int = Field(..., description="The ending character index of the quoted text.")

# Entity Item
class EntityItem(BaseModel):
  entity: str = Field(..., description="The named entity recognized in the text.")
  type: EntityTypes = Field(..., description="The type of the named entity.")
  confidence: float = Field(..., description="The confidence score of the entity recognition.")
  supporting_evidence: list[EntityEvidence] = Field(..., description="A list of supporting evidence for the entity.")

# Translation
class Translation(BaseModel):
  text: str = Field(..., description="The translated text.")
  original_text: str = Field(..., description="The original text before translation.")
  source_language: str = Field(..., description="The language of the original text.")
  target_language: str = Field(..., description="The language of the translated text.")

# Page Summary
class PageSummary(BaseModel):
  page_number: int = Field(..., description="The page number in the document.")
  summary: str = Field(..., description="A brief summary of the page content.")
  key_points: list[str] = Field(..., description="A list of key points extracted from the page.")

# General Description
class GeneralDescription(BaseModel):
  description: str = Field(..., description="A general description of the document content.")
  author: Optional[str] = Field(None, description="The author of the document, if identified.")
  date_created: Optional[str] = Field(None, description="The creation date of the document, if identified (ISO format string).")
  confidence: float = Field(..., description="The confidence score of the description.")
  categories: list[CategoryEvidence] = Field(..., description="A list of category evidences.")
  entities: list[EntityItem] = Field(..., description="A list of recognized entities in the text.")
  keywords: Optional[list[str]] = Field(None, description="A list of keywords extracted from the document.")
  translation: Optional[Translation] = Field(None, description="Translation of the document text, if applicable.")
  page_summaries: Optional[list[PageSummary]] = Field(None, description="A list of summaries for each page in the document.")

class LLMOperations:
  def __init__(self):
    self.openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    self.openai_api_key = os.getenv("AZURE_OPENAI_KEY")
    self.openai_version = os.getenv("AZURE_OPENAI_API_VERSION")
    self.model_name = os.getenv("AZURE_OPENAI_MODEL_NAME")
    self.embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL")

    self.client = openai.AzureOpenAI(
      azure_endpoint=self.openai_endpoint,
      api_key=self.openai_api_key,
      api_version=self.openai_version,
    )

    # Init Document Summarizer
    self.summarizer = DocumentSummarizer(self.client, self.model_name)

  def analyze_page(self, page_content: str, page_number: int, total_pages: int) -> Dict[str, Any]:
      """
      Analyze a single page using LLM with existing GeneralDescription format.
      
      Args:
          page_content: Text content of the page
          page_number: Page number being analyzed
          total_pages: Total number of pages in document
      
      Returns:
          Dict with GeneralDescription format plus page metadata
      """
      prompt = f"""
        This is page {page_number} of {total_pages} from a document.

        Text:
        \"\"\"{page_content}\"\"\"

        Instructions:
        1. Provide a brief general description of this page's content.
        2. Identify relevant categories from the following list: {Categories}. For each category, provide supporting evidence from the text.
        3. Extract named entities such as {EntityTypes}. For each entity, provide supporting evidence from the text.
        4. If the source language is not English, provide a translation to English.
        """

      response = self.client.chat.completions.create(
        model=self.model_name,
        messages=[
          {"role": "system", "content": "You are an expert document analyst. Given the following text from this page, provide a concise general description of its content, identify relevant categories, and extract named entities."},
          {"role": "user", "content": prompt}
        ],
        response_format={
          "type": "json_schema",
          "json_schema": {
            "name": "GeneralDescription",
            "schema": GeneralDescription.model_json_schema()
          }
        },
        temperature=0.2,
        max_tokens=4000,
        n=1,
        stop=None,
      )

      try:
        content = response.choices[0].message.content
        data = json.loads(content)
        # Add page metadata
        data["page_number"] = page_number
        data["page_text_length"] = len(page_content)
        logging.info(f"Successfully analyzed page {page_number}/{total_pages}")
        return data
      except (json.JSONDecodeError, KeyError) as e:
        logging.error(f"Error parsing LLM response for page {page_number}: {e}")
        # Return minimal structure on error
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
          "error": str(e),
          "is_error": True  # Add explicit flag
        }

  def consolidate_page_analyses(self, page_results: List[Dict[str, Any]]) -> Dict[str, Any]:
      """
      Consolidate multiple page analyses into a single GeneralDescription.
      Aggregates entities, categories, and creates unified description.
      
      Args:
          page_results: List of page analysis results
      
      Returns:
          Consolidated GeneralDescription format
      """
      # Aggregate all data from pages
      all_descriptions = []
      all_categories = []
      all_entities = []
      all_keywords = []
      authors = set()
      dates = set()
      confidence_scores = []
      
      for result in page_results:
        if result.get("error"):
          continue
        
        page_num = result.get("page_number", "?")
        desc = result.get("description", "")
        if desc:
          all_descriptions.append(f"Page {page_num}: {desc}")
        
        all_categories.extend(result.get("categories", []))
        all_entities.extend(result.get("entities", []))
        
        keywords = result.get("keywords")
        if keywords:
          all_keywords.extend(keywords)
        
        author = result.get("author")
        if author:
          authors.add(author)
        
        date_created = result.get("date_created")
        if date_created:
          dates.add(str(date_created))
        
        confidence = result.get("confidence")
        if confidence:
          confidence_scores.append(confidence)
      
      # Deduplicate entities by entity name (case-insensitive)
      unique_entities = {}
      for entity in all_entities:
        entity_key = entity.get("entity", "").lower()
        if entity_key and entity_key not in unique_entities:
          unique_entities[entity_key] = entity
      
      # Deduplicate categories by category name
      unique_categories = {}
      for category in all_categories:
        cat_key = category.get("category", "")
        if cat_key:
          if cat_key not in unique_categories:
            unique_categories[cat_key] = category
          else:
            # Merge supporting evidence
            existing = unique_categories[cat_key]
            existing_evidence = set(existing.get("supporting_evidence", []))
            new_evidence = set(category.get("supporting_evidence", []))
            existing["supporting_evidence"] = list(existing_evidence | new_evidence)
      
      # Deduplicate keywords
      unique_keywords = list(dict.fromkeys(all_keywords)) if all_keywords else None
      
      # Calculate average confidence
      avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
      
      # Create consolidated description
      #consolidated_description = " ".join(all_descriptions) if all_descriptions else "Document analysis completed."

      # Use DocumentSummarizer to create intelligent document summary
      logging.info(f"Reducing {len(page_results)} page summaries to document-level summary")
      consolidated_description = self.summarizer.reduce_to_document_summary(page_results, len(page_results))
      
      # Build final result
      consolidated = {
        "description": consolidated_description,
        "author": list(authors)[0] if authors else None,
        "date_created": list(dates)[0] if dates else None,
        "confidence": round(avg_confidence, 2),
        "categories": list(unique_categories.values()),
        "entities": list(unique_entities.values()),
        "keywords": unique_keywords,
        "translation": None,
        "metadata": {
          "total_pages": len(page_results),
          "successful_pages": len([r for r in page_results if not r.get("error")]),
          "chunking_method": "page_based"
        }
      }
      
      # Prepare page summaries list
      page_summaries_list = []
      for result in page_results:
        if not result.get("error"):
            page_summaries_list.append(
                PageSummary(
                    page_number=result.get("page_number"),
                    summary=result.get("description", ""),
                    key_points=result.get("keywords", []) or []
                ).model_dump()
            )
      
      logging.info(f"Consolidated {len(page_results)} page analyses into final description")
      consolidated["page_summaries"] = page_summaries_list
      return consolidated

  def generate_embedding(self, text):

    text_str = str(text).strip()
    logging.info(f"Generating embedding for text of length {len(text_str)}")

    try:
      response = self.client.embeddings.create(
        model=self.embedding_model,
        input=text_str
      )

      return response.data[0].embedding
    except Exception as e:
      logging.error(f"Error generating embedding: {e}")
      raise ValueError("Failed to generate embedding") from e
    
@bp_llm.route(route="describe", methods=["POST"])
async def describe_document(req: func.HttpRequest) -> func.HttpResponse:
  try:
    body = req.get_json()
    llmops = LLMOperations()
    pages = body.get("pages", [])

  # Support both direct pages and nested analysis.pages (from Document Intelligence)
    if "analysis" in body:
        analysis_data = body["analysis"]
        pages = analysis_data.get("pages", [])
        fallback_content = analysis_data.get("content", "")
        logging.info("Processing Document Intelligence output format")
    else:
        pages = body.get("pages", [])
        fallback_content = body.get("content", "")
        logging.info("Processing direct pages format")

    # Validate pages is a list
    if not isinstance(pages, list):
        return func.HttpResponse(
            body=json.dumps({"error": "pages must be a list"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Fallback to using entire content if no pages provided
    if not pages and fallback_content:
        logging.info("No pages found, creating single page from content")
        pages = [{
            "page_number": 1,
            "content": fallback_content
        }]    

    # IF no pages are found fallback to useing entire content.
    if not pages:
      pages = [{
        "page_number": 1,
        "content": body.get("content", "")
    }]

    logging.info(f"Total chunks to process: {len(pages)}")

    # Analyze each chunk to generate page summaries
    page_summaries = []

    for page in pages:
      page_content = page.get("content", "")
      page_number = page.get("page_number", 0)

      # Skip empty pages
      if not page_content:
        logging.warning(f"Skipping empty page {page_number}")
        page["analysis"] = {
          "description": "Empty page",
          "error": "No content to analyze"
        }
        continue

      summary = llmops.analyze_page(
        page_content=page_content,
        page_number=page_number,
        total_pages=len(pages)
      )

      # Attach analysis to the page
      page["analysis"] = summary  

      # Append summary to page_summaries for consolidation
      page_summaries.append(summary)


    # Consolidate page analysis
    consolidated_results = llmops.consolidate_page_analyses(page_summaries)

    # Generate overall summary for the documemt


    # Generate Description
    #results = llmops.generate_general_description(text=body)

    # Generate text embedding based on description
    #description = results.get('description', '')
    #logging.info(f"Generating embedding for description: {description}")
    #embedding = llmops.generate_embedding(text=description)

    response_data = {
      "llm_analysis": consolidated_results,
      "pages": pages  
      #"embedding": embedding
    }

    return func.HttpResponse(
      body=json.dumps(response_data, default=str),
      status_code=200,
      mimetype="application/json"
    )
  
  except Exception as e:
    logging.error(f"Error in describe_document: {e}")
    return func.HttpResponse(
      body=json.dumps({"error": str(e)}),
      status_code=500,
      mimetype="application/json"
    )