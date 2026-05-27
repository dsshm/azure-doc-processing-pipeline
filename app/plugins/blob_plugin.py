"""Semantic Kernel plugin for Azure Blob Storage operations.

Ported from services/blob_service.py.
Auth: DefaultAzureCredential only — no access keys or connection strings.
Supports user delegation SAS for original document access.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from urllib.parse import urlparse

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)


class BlobPlugin:
    """Azure Blob Storage operations exposed as SK functions."""

    def __init__(self, account_url: str | None = None):
        self._account_url = account_url or os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")
        self._credential = DefaultAzureCredential()
        self._client = BlobServiceClient(
            account_url=self._account_url,
            credential=self._credential,
        )

    # ------------------------------------------------------------------
    @kernel_function(name="blob_exists", description="Check whether a blob exists in a container.")
    def blob_exists(
        self,
        container: Annotated[str, "Container name"],
        blob_name: Annotated[str, "Blob path/name"],
    ) -> bool:
        client = self._client.get_blob_client(container=container, blob=blob_name)
        return client.exists()

    # ------------------------------------------------------------------
    @kernel_function(name="download_blob", description="Download a blob and return its bytes.")
    def download_blob(
        self,
        container: Annotated[str, "Container name"],
        blob_name: Annotated[str, "Blob path/name"],
    ) -> bytes:
        blob_client = self._client.get_blob_client(container=container, blob=blob_name)
        return blob_client.download_blob().readall()

    # ------------------------------------------------------------------
    @kernel_function(name="download_blob_by_url", description="Download blob content given its full URL.")
    def download_blob_by_url(
        self,
        blob_url: Annotated[str, "Full blob URL"],
    ) -> bytes:
        container, blob_name = self._parse_blob_url(blob_url)
        return self.download_blob(container=container, blob_name=blob_name)

    # ------------------------------------------------------------------
    @kernel_function(name="upload_blob", description="Upload data to a blob.")
    def upload_blob(
        self,
        container: Annotated[str, "Container name"],
        blob_name: Annotated[str, "Blob path/name"],
        data: Annotated[bytes, "Content bytes"],
        content_type: Annotated[str, "MIME type"] = "application/octet-stream",
    ) -> str:
        blob_client = self._client.get_blob_client(container=container, blob=blob_name)
        blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type=content_type))
        logger.info("Uploaded %s/%s (%d bytes)", container, blob_name, len(data))
        return blob_client.url

    # ------------------------------------------------------------------
    @kernel_function(name="move_blob", description="Copy a blob to a new container then delete the source.")
    def move_blob(
        self,
        source_container: Annotated[str, "Source container"],
        dest_container: Annotated[str, "Destination container"],
        blob_name: Annotated[str, "Blob path/name"],
    ) -> str:
        src_client = self._client.get_blob_client(container=source_container, blob=blob_name)
        dst_client = self._client.get_blob_client(container=dest_container, blob=blob_name)

        # Start copy (server‑side, same account)
        dst_client.start_copy_from_url(src_client.url)
        # Delete source after copy
        src_client.delete_blob()
        logger.info("Moved %s from %s → %s", blob_name, source_container, dest_container)
        return dst_client.url

    # ------------------------------------------------------------------
    @kernel_function(
        name="generate_user_delegation_sas",
        description="Generate a user‑delegation SAS URL for a blob (read‑only, 1 hour).",
    )
    def generate_user_delegation_sas(
        self,
        container: Annotated[str, "Container name"],
        blob_name: Annotated[str, "Blob path/name"],
        expiry_hours: Annotated[int, "Hours until SAS expires"] = 1,
    ) -> str:
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=5)
        expiry = now + timedelta(hours=expiry_hours)

        delegation_key = self._client.get_user_delegation_key(
            key_start_time=start,
            key_expiry_time=expiry,
        )

        account_name = self._parse_account_name()
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            start=start,
        )
        return f"{self._account_url}/{container}/{blob_name}?{sas_token}"

    # ------------------------------------------------------------------
    @kernel_function(name="list_blobs", description="List blobs in a container with optional prefix.")
    def list_blobs(
        self,
        container: Annotated[str, "Container name"],
        prefix: Annotated[str, "Blob name prefix filter"] = "",
    ) -> list[str]:
        container_client = self._client.get_container_client(container)
        return [b.name for b in container_client.list_blobs(name_starts_with=prefix or None)]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _parse_blob_url(self, url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid blob URL: {url}")
        return parts[0], parts[1]

    def _parse_account_name(self) -> str:
        parsed = urlparse(self._account_url)
        return parsed.hostname.split(".")[0] if parsed.hostname else ""
