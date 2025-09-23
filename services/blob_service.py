"""
Azure Blob Storage Service for Case File Management

This service handles storage and retrieval of case attachment files using Azure Blob Storage
with RBAC authentication. Designed for web-optimized file serving.
"""

import os
import logging
import mimetypes
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings, UserDelegationKey, generate_blob_sas, BlobSasPermissions
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError, ClientAuthenticationError

logger = logging.getLogger(__name__)

class BlobService:
    """Service for managing case files in Azure Blob Storage."""
    
    def __init__(self):
        pass
    
    def download_file(self, blob_url: str) -> Optional[bytes]:
        """
        Download file content from blob storage using the blob URL.
        
        Args:
            blob_url: Full blob URL
            
        Returns:
            File content as bytes if successful, None if failed
        """ 
        if not blob_url:
            logger.error("No blob URL provided for download.")
            return None
        

        try:
            # Parse the blob URL to extract container and blob name
            parsed_url = urlparse(blob_url)

            path_parts = parsed_url.path.strip('/').split('/')
            
            if len(path_parts) < 2:
                logger.error(f"Invalid blob URL format: {blob_url}")
                return None
                
            container_name = path_parts[0]
            blob_name = '/'.join(path_parts[1:])

            # BLOB Account URL
            account_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # Create BLOB Service client with DefaultAzureCredential
            if not os.getenv("STORAGE_ACCESS_KEY"):
                credential = DefaultAzureCredential()
            else:
                credential = AzureKeyCredential(os.getenv("STORAGE_ACCESS_KEY"))
            
            blob_service_client = BlobServiceClient(
                account_url=account_url,
                credential=credential
            )
            
            # Get blob client and download
            blob_client = blob_service_client.get_blob_client(
                container=container_name,
                blob=blob_name
            )
            
            download_stream = blob_client.download_blob()
            content = download_stream.readall()
            
            logger.info(f"Successfully downloaded file from blob storage: {blob_name}")
            return content
            
        except ResourceNotFoundError:
            logger.warning(f"File not found in blob storage: {blob_url}")
            return None
        except Exception as e:
            logger.error(f"Failed to download file from blob storage {blob_url}: {e}")
            return None
    
   