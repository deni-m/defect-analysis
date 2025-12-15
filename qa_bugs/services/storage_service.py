"""Azure Blob Storage service for file persistence."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Dict
from io import BytesIO
import pandas as pd

try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
except ImportError:
    BlobServiceClient = None
    ContentSettings = None


class AzureBlobStorageService:
    """
    Service for uploading and downloading CSV files to/from Azure Blob Storage.

    Configuration via environment variables:
    - AZURE_STORAGE_CONNECTION_STRING: Azure Storage connection string
    - AZURE_STORAGE_CONTAINER: Container name (default: bug-analytics-uploads)
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        container_name: Optional[str] = None
    ):
        """
        Initialize Azure Blob Storage service.

        Args:
            connection_string: Azure Storage connection string (or from env)
            container_name: Container name (or from env, default: bug-analytics-uploads)
        """
        if BlobServiceClient is None:
            raise ImportError(
                "azure-storage-blob is not installed. "
                "Install it with: pip install azure-storage-blob"
            )

        # Get connection string from parameter or environment
        self.connection_string = connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not self.connection_string:
            raise ValueError(
                "Azure Storage connection string not found. "
                "Provide it via constructor or AZURE_STORAGE_CONNECTION_STRING env variable."
            )

        # Get container name from parameter or environment
        self.container_name = container_name or os.getenv(
            "AZURE_STORAGE_CONTAINER",
            "bug-analytics-uploads"
        )

        # Initialize blob service client
        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.connection_string
        )

        # Ensure container exists
        self._ensure_container_exists()

    def _ensure_container_exists(self):
        """Create container if it doesn't exist."""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            if not container_client.exists():
                container_client.create_container()
        except Exception as e:
            # Log but don't fail - container might exist and we just can't check
            print(f"Warning: Could not verify container existence: {e}")

    def upload_csv(
        self,
        file_content: bytes,
        original_filename: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> tuple[str, str]:
        """
        Upload CSV file to blob storage.

        Args:
            file_content: CSV file content as bytes
            original_filename: Original filename
            metadata: Optional metadata to attach to blob

        Returns:
            Tuple of (blob_name, blob_url)
        """
        # Generate unique blob name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"{timestamp}_{original_filename}"

        # Get blob client
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )

        # Prepare metadata
        blob_metadata = metadata or {}
        blob_metadata["original_filename"] = original_filename
        blob_metadata["upload_timestamp"] = timestamp

        # Upload blob
        blob_client.upload_blob(
            file_content,
            overwrite=True,
            content_settings=ContentSettings(content_type="text/csv"),
            metadata=blob_metadata
        )

        # Get blob URL
        blob_url = blob_client.url

        return blob_name, blob_url

    def download_csv_to_dataframe(self, blob_name: str) -> pd.DataFrame:
        """
        Download CSV blob and parse as DataFrame.

        Args:
            blob_name: Name of the blob to download

        Returns:
            DataFrame with CSV contents
        """
        # Get blob client
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )

        # Download blob to memory
        blob_data = blob_client.download_blob()
        csv_bytes = blob_data.readall()

        # Parse CSV
        df = pd.read_csv(BytesIO(csv_bytes))
        return df

    def get_blob_url(self, blob_name: str) -> str:
        """
        Get URL for a blob.

        Args:
            blob_name: Name of the blob

        Returns:
            Blob URL
        """
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        return blob_client.url

    def list_blobs(self, prefix: Optional[str] = None, limit: int = 100) -> list[Dict]:
        """
        List blobs in container.

        Args:
            prefix: Optional prefix to filter blobs
            limit: Maximum number of blobs to return

        Returns:
            List of blob info dicts
        """
        container_client = self.blob_service_client.get_container_client(
            self.container_name
        )

        blobs = []
        for blob in container_client.list_blobs(name_starts_with=prefix):
            if len(blobs) >= limit:
                break
            blobs.append({
                "name": blob.name,
                "size": blob.size,
                "created": blob.creation_time,
                "modified": blob.last_modified,
                "metadata": blob.metadata
            })

        return blobs

    def delete_blob(self, blob_name: str):
        """
        Delete a blob.

        Args:
            blob_name: Name of the blob to delete
        """
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=blob_name
        )
        blob_client.delete_blob()


# Convenience function for getting storage service with default settings
def get_storage_service() -> AzureBlobStorageService:
    """
    Get Azure Blob Storage service with default configuration from environment.

    Returns:
        Configured AzureBlobStorageService instance
    """
    return AzureBlobStorageService()
