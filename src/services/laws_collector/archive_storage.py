from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContainerClient

from .config import LawsCollectorConfig


@dataclass(frozen=True)
class StoredArchiveObject:
    storage_backend: str
    storage_path: str


class ArchiveObjectStore:
    def persist_file(self, *, source_path: Path, relative_path: str) -> StoredArchiveObject:
        raise NotImplementedError


class LocalArchiveObjectStore(ArchiveObjectStore):
    def persist_file(self, *, source_path: Path, relative_path: str) -> StoredArchiveObject:
        return StoredArchiveObject(
            storage_backend="local_file",
            storage_path=str(source_path.resolve()),
        )


class AzureBlobArchiveObjectStore(ArchiveObjectStore):
    def __init__(self, *, container_url: str) -> None:
        self._container_url = container_url.rstrip("/")
        self._container_client = _build_container_client(self._container_url)
        try:
            self._container_client.create_container()
        except ResourceExistsError:
            pass

    def persist_file(self, *, source_path: Path, relative_path: str) -> StoredArchiveObject:
        normalized_relative_path = relative_path.strip().replace("\\", "/").lstrip("/")
        blob_client = self._container_client.get_blob_client(normalized_relative_path)
        if not blob_client.exists():
            with source_path.open("rb") as handle:
                blob_client.upload_blob(handle, overwrite=False)
        return StoredArchiveObject(
            storage_backend="azure_blob",
            storage_path=f"{self._container_url}/{normalized_relative_path}",
        )


def build_archive_object_store(config: LawsCollectorConfig) -> ArchiveObjectStore:
    if config.storage_cloud:
        return AzureBlobArchiveObjectStore(container_url=config.storage_cloud)
    return LocalArchiveObjectStore()


def _build_container_client(container_url: str) -> ContainerClient:
    parsed = urlparse(container_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("LAWS_STORAGE_CLOUD must be a valid Azure Blob container URL.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 1:
        raise ValueError(
            "LAWS_STORAGE_CLOUD must point to a blob container, for example "
            "'https://<account>.blob.core.windows.net/laws-collection-sk'."
        )
    container_name = path_parts[0]
    account_url = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.query:
        return ContainerClient.from_container_url(container_url)

    managed_identity_client_id = os.getenv("AZURE_CLIENT_ID", "").strip() or None
    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
        managed_identity_client_id=managed_identity_client_id,
    )
    return BlobServiceClient(account_url=account_url, credential=credential).get_container_client(
        container_name
    )
