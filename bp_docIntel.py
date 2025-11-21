import logging
import os
import json
import uuid
from datetime import datetime
import azure.functions as func

from typing import Any, Dict, List, Optional

# Import service classes instead of direct Azure SDK usage
from services import BlobService

# Import Azure Service SDKs
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature, AnalyzeResult, AnalyzeOutputOption 

docintel = func.Blueprint()

class AzDocIntel:
  def __init__(self):

    # Check for authentication type (Key / Managed Identity)
    api_key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
    if api_key:
      credential = AzureKeyCredential(api_key)
    else:
      credential = DefaultAzureCredential()

    # Create Document Intelligence client
    self.client = DocumentIntelligenceClient(
      endpoint=os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"),
      credential=credential
    )

  def analyze_document_from_stream(
      self, 
      document_data: bytes, 
      model_id: str = "prebuilt-layout") -> Dict[str, Any]:

    poller = self.client.begin_analyze_document(
      model_id=model_id,
      body=document_data,
      #output_content_format="markdown",
      #output=[AnalyzeOutputOption.PARAGRAPHS],
      features=[
        DocumentAnalysisFeature.BARCODES
      ]
    )

    results = poller.result()

    # Page mapping
    pages = []
    barcodes = []

    for page in results.pages:
      page_number = page.page_number
      page_content = ""

      # METHOD 1: Extract using spans (if available)
      if page.spans and results.content:
        try:
          page_content_parts = []
          for span in page.spans:
            start = span.offset
            end = start + span.length
            page_content_parts.append(results.content[start:end])
          page_content = "".join(page_content_parts)
        except Exception as e:
          page_content = ""

      # METHOD 2: Extract using lines (fallback)
      if not page_content and page.lines:
        try:
          page_content = "\n".join(line.content for line in page.lines)
        except Exception as e:
          page_content = ""

      # METHOD 3: Extract using words (last resort)
      if not page_content and page.words:
        try:
          page_content = " ".join(word.content for word in page.words)
        except Exception as e:
          page_content = ""

      pages.append({
        "page_number": page_number,
        "width": page.width,
        "height": page.height,
        "content": page_content,
      })

      for bc in (getattr(page, "barcodes", None) or []):
        barcodes.append({
          "page_number": page_number,
          "kind": bc.kind,
          "value": bc.value,
          "polygon": bc.polygon,
          "confidence": bc.confidence
        })

    # Table extraction
    tables: List[Dict[str, Any]] = []
    for table in (results.tables or []):
      rows: Dict[int, Dict[int, str]] = {}
      max_row = max((c.row_index for c in table.cells), default=-1)
      max_col = max((c.column_index for c in table.cells), default=-1)

      for row in range(max_row + 1):
        rows[row] = {c: "" for c in range(max_col + 1)}

      for col in table.cells:
        rows[col.row_index][col.column_index] = (col.content or "").strip()

      cvs_rows = [[rows[row][col] for col in range(max_col + 1)] for row in range(max_row + 1)]
      tables.append({
        "page_number": (table.bounding_regions[0].page_number if table.bounding_regions else None),
        "row_count": max_row + 1,
        "column_count": max_col + 1,
        "rows": cvs_rows,
        "polygon": table.bounding_regions[0].polygon if table.bounding_regions else None
      })

    returnResults = {
      "content": results.content or "",
      "pages": pages,
      "tables": tables,
      "barcodes": barcodes,
    }

    return returnResults

@docintel.route(route="analyze", methods=["POST"])
def analyze_document(req: func.HttpRequest) -> func.HttpResponse:
  
  # Get file from BLOB storage
  try:
    body = req.get_json()
    file_url = body.get("file_url")
    if not file_url:
      raise ValueError("Missing 'file_url' in request body.")
  except Exception as e:
    logging.error(f"Error parsing request body: {e}")
    return func.HttpResponse(
      body=json.dumps({"error": "Invalid request body."}),
      status_code=400,
      mimetype="application/json"
    )
  
  try:
    blob_service = BlobService()
    file_data = blob_service.download_file(file_url)

    # Check to make sure the file isn't empty
    if not file_data:
      logging.error(f"File data is empty for URL: {file_url}")
      return func.HttpResponse(
        body=json.dumps({"error": "File data is empty."}),
        status_code=400,
        mimetype="application/json"
      )

  except Exception as e:
    logging.error(f"Error downloading file from BLOB storage: {e}")
    return func.HttpResponse(
      body=json.dumps({"error": "Failed to download file from storage."}),
      status_code=500,
      mimetype="application/json"
    )

  # Process document with Document Intelligence
  try:
    # Initialize Document Intelligence client
    doc_intel = AzDocIntel()
    
    # Get model_id from request body or use default
    model_id = body.get("model_id", "prebuilt-layout")
    
    # Analyze document
    analysis_results = doc_intel.analyze_document_from_stream(
      file_data,
      model_id
    )

    # Add metadata
    response_data = {
      "request_id": str(uuid.uuid4()),
      "timestamp": datetime.utcnow().isoformat() + "Z",
      "file_url": file_url,
      "model_id": model_id,
      "analysis": analysis_results
    }
    
    logging.info(f"Successfully analyzed document: {file_url}")
    
    return func.HttpResponse(
      body=json.dumps(response_data),
      status_code=200,
      mimetype="application/json"
    )
    
  except Exception as e:
    logging.error(f"Error analyzing document with Document Intelligence: {e}")
    return func.HttpResponse(
      body=json.dumps({
        "error": "Failed to analyze document with Document Intelligence.",
        "details": str(e)
      }),
      status_code=500,
      mimetype="application/json"
    ) 