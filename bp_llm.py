import logging
import os
import json

from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
import openai
from pydantic import BaseModel, Field

import azure.functions as func

from services import BlobService

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

# General Description
class GeneralDescription(BaseModel):
  description: str = Field(..., description="A general description of the document content.")
  author: Optional[str] = Field(None, description="The author of the document, if identified.")
  date_created: Optional[datetime] = Field(None, description="The creation date of the document, if identified.")
  confidence: float = Field(..., description="The confidence score of the description.")
  categories: list[CategoryEvidence] = Field(..., description="A list of category evidences.")
  entities: list[EntityItem] = Field(..., description="A list of recognized entities in the text.")
  keywords: Optional[list[str]] = Field(None, description="A list of keywords extracted from the document.")
  translation: Optional[Translation] = Field(None, description="Translation of the document text, if applicable.")


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

  def generate_general_description(self, text: str):
    prompt = f"""
    You are an expert document analyst. Given the following text, provide a concise general description of its content, identify relevant categories, and extract named entities.

    Text:
    \"\"\"{text}\"\"\"

    Instructions:
    1. Provide a brief general description of the document content.
    2. Identify relevant categories from the following list: {Categories}. For each category, provide supporting evidence from the text.
    3. Extract named entities such as {EntityTypes}. For each entity, provide supporting evidence from the text.
    4. If the source language is not English, provide a translation to English.

    """

    response = self.client.chat.completions.create(
      model=self.model_name,
      messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt}
      ],
      response_format={
        "type": "json_schema",
        "json_schema":{
          "name": "GeneralDescription",
          "schema": GeneralDescription.model_json_schema()
        }
      },
      temperature=0.2,
      max_tokens=1000,
      n=1,
      stop=None,
    )

    try:
      content = response.choices[0].message.content
      data = json.loads(content)
      print( data )
      return data
    except (json.JSONDecodeError, KeyError) as e:
      logging.error(f"Error parsing LLM response: {e}")
      raise ValueError("Failed to parse LLM response") from e
    
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

    # Generate Description
    results = llmops.generate_general_description(text=body)

    # Generate text embedding based on description
    #description = results.get('description', '')
    #logging.info(f"Generating embedding for description: {description}")
    #embedding = llmops.generate_embedding(text=description)

    response_data = {
      "llm_analysis": results,
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