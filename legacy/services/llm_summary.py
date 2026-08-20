"""
LLM Service for Document Analysis and Summarization

This service handles document analysis using Azure OpenAI, including:
- Page-by-page analysis
- Hierarchical summarization for large documents
- Entity and category extraction
- Consolidation of multi-page analyses
"""

import logging
import os
from typing import Any, Dict, List
import tiktoken
import openai
from pydantic import BaseModel, Field


class DocumentSummarizer:
    """
    Handles intelligent summarization of multi-page documents using LLM.
    Supports hierarchical reduction for large documents to avoid token limits.
    """
    
    def __init__(self, openai_client: openai.AzureOpenAI, model_name: str):
        """
        Initialize the summarizer.
        
        Args:
            openai_client: Configured Azure OpenAI client
            model_name: Model name for chat completions
        """
        self.client = openai_client
        self.model_name = model_name
        self.max_input_tokens_per_request = 15000  # Conservative limit for input
        self.chunk_size = 10  # Pages per chunk in hierarchical reduction
    
    def reduce_to_document_summary(self, page_summaries: List[Dict[str, Any]], total_pages: int) -> str:
        """
        Reduce multiple page summaries into a cohesive document-level summary.
        Automatically chooses between single-pass and hierarchical reduction.
        
        Args:
            page_summaries: List of individual page analysis results
            total_pages: Total number of pages in document
        
        Returns:
            Cohesive document summary string
        """
        # Extract valid summaries
        summaries_text = []
        for page in page_summaries:
            if not page.get("error"):
                desc = page.get("description", "")
                page_num = page.get("page_number", "?")
                if desc:
                    summaries_text.append(f"Page {page_num}: {desc}")
        
        if not summaries_text:
            return "Document analysis completed with no valid content."
        
        # Combine and check token count
        combined_text = "\n\n".join(summaries_text)
        
        try:
            estimated_tokens = self._estimate_tokens(combined_text)
            
            if estimated_tokens > self.max_input_tokens_per_request:
                logging.info(f"Large document detected ({estimated_tokens} est. tokens). Using hierarchical reduction.")
                return self._hierarchical_reduce(summaries_text, total_pages)
            else:
                logging.info(f"Standard reduction ({estimated_tokens} est. tokens)")
                return self._single_pass_reduce(combined_text, total_pages)
                
        except Exception as e:
            logging.error(f"Failed to generate document summary via LLM: {e}")
            # Fallback to truncated concatenation
            fallback = " ".join(summaries_text[:10])
            if len(summaries_text) > 10:
                fallback += f"... (and {len(summaries_text) - 10} more pages)"
            return fallback
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text using tiktoken.
        
        Args:
            text: Text to estimate tokens for
        
        Returns:
            Estimated token count
        """
        try:
            encoding = tiktoken.encoding_for_model(self.model_name)
            return len(encoding.encode(text))
        except Exception:
            # Fallback to character-based estimation (1 token ≈ 4 chars)
            return len(text) // 4
    
    def _single_pass_reduce(self, combined_summaries: str, total_pages: int) -> str:
        """
        Single-pass LLM reduction for documents that fit in context window.
        
        Args:
            combined_summaries: All page summaries combined
            total_pages: Total number of pages
        
        Returns:
            Reduced document summary
        """
        prompt = f"""You are analyzing a {total_pages}-page document. Below are summaries for each page.

        Page Summaries:
        {combined_summaries}

        Instructions:
        1. Synthesize these page summaries into a single, cohesive 2-3 paragraph summary of the entire document.
        2. Focus on the document's main purpose, key information, and overall content.
        3. Remove redundancy and page-specific references.
        4. Write in a natural, flowing narrative style.
        5. Do NOT use phrases like "Page 1 discusses..." - integrate the information seamlessly.

        Provide a comprehensive document summary."""

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are an expert document analyst who creates clear, concise summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_completion_tokens=800,
            n=1,
            stop=None,
        )
        
        summary = response.choices[0].message.content.strip()
        logging.info(f"Generated document summary ({len(summary)} chars)")
        return summary
            
    def _hierarchical_reduce(self, summaries_text: List[str], total_pages: int) -> str:
        """
        Hierarchical reduction for large documents.
        Reduces summaries in batches, then reduces the batch summaries.
        
        Args:
            summaries_text: List of page summary strings
            total_pages: Total number of pages
        
        Returns:
            Final reduced document summary
        """
        # Step 1: Group pages into chunks
        chunks = [summaries_text[i:i + self.chunk_size] 
                  for i in range(0, len(summaries_text), self.chunk_size)]
        
        logging.info(f"Hierarchical reduction: {len(chunks)} chunks of ~{self.chunk_size} pages each")
        
        # Step 2: Reduce each chunk to an intermediate summary
        intermediate_summaries = []
        for i, chunk in enumerate(chunks):
            chunk_text = "\n\n".join(chunk)
            start_page = i * self.chunk_size + 1
            end_page = min((i + 1) * self.chunk_size, total_pages)
            
            prompt = f"""You are analyzing pages {start_page}-{end_page} of a {total_pages}-page document.

Page Summaries:
{chunk_text}

Instructions:
Provide a concise 1-2 paragraph summary that captures the key information from these pages. Focus on main themes, important details, and overall content. Write in a cohesive narrative style."""

            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are an expert document analyst."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_completion_tokens=400,
                    n=1,
                    stop=None,
                )
                
                chunk_summary = response.choices[0].message.content.strip()
                intermediate_summaries.append(f"Pages {start_page}-{end_page}: {chunk_summary}")
                logging.info(f"Reduced chunk {i+1}/{len(chunks)} (pages {start_page}-{end_page})")
                
            except Exception as e:
                logging.error(f"Failed to reduce chunk {i+1}: {e}")
                # Include first few pages from chunk as fallback
                intermediate_summaries.append(f"Pages {start_page}-{end_page}: {' '.join(chunk[:3])}...")
        
        # Step 3: Final reduction of intermediate summaries
        if len(intermediate_summaries) == 1:
            # Only one chunk, return it directly (remove page range prefix)
            return intermediate_summaries[0].split(": ", 1)[1] if ": " in intermediate_summaries[0] else intermediate_summaries[0]
        
        combined_intermediate = "\n\n".join(intermediate_summaries)
        
        final_prompt = f"""You are analyzing a {total_pages}-page document. Below are summaries for different sections.

Section Summaries:
{combined_intermediate}

Instructions:
Synthesize these section summaries into a single, cohesive 2-3 paragraph summary of the entire document. Focus on the document's main purpose, key information, and overall narrative. Write in a natural, flowing style without section references.

Provide a comprehensive document summary."""

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are an expert document analyst who creates clear, concise summaries."},
                {"role": "user", "content": final_prompt}
            ],
            temperature=0.3,
            max_completion_tokens=800,
            n=1,
            stop=None,
        )
        
        final_summary = response.choices[0].message.content.strip()
        logging.info(f"Generated final hierarchical summary ({len(final_summary)} chars)")
        return final_summary
