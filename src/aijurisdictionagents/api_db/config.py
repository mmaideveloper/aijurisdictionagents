from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class ApiDataConfig:
    db_option: str
    storage_option: str
    db_local: str
    db_cloud: str
    store_local: str
    store_cloud: str

    @classmethod
    def from_env(cls) -> "ApiDataConfig":
        return cls(
            db_option=os.getenv("DB_OPTION", "local").strip().lower(),
            storage_option=os.getenv("STORAGE_OPTION", "local").strip().lower(),
            db_local=os.getenv("DB_LOCAL", "./data/api.sqlite3").strip(),
            db_cloud=os.getenv("DB_CLOUD", "").strip(),
            store_local=os.getenv("STORE_LOCAL", "./storage").strip(),
            store_cloud=os.getenv("STORE_CLOUD", "").strip(),
        )

    def validate(self) -> None:
        if self.db_option not in {"local", "azure"}:
            raise ValueError("DB_OPTION must be one of: local, azure")
        if self.storage_option not in {"local", "azure"}:
            raise ValueError("STORAGE_OPTION must be one of: local, azure")
        if self.db_option == "azure" and not self.db_cloud:
            raise ValueError("DB_CLOUD must be set when DB_OPTION=azure")
        if self.storage_option == "azure" and not self.store_cloud:
            raise ValueError("STORE_CLOUD must be set when STORAGE_OPTION=azure")

    @property
    def db_path(self) -> Path:
        if self.db_option == "local":
            return Path(self.db_local)
        # Cloud DB configured via connection string (for PostgreSQL adapter in prod).
        # During local development/tests this still needs a local metadata path.
        return Path(self.db_local)

    @property
    def blob_root(self) -> Path:
        if self.storage_option == "local":
            return Path(self.store_local)
        # Cloud storage configured via connection string (for Azure Blob adapter in prod).
        # During local development/tests this still needs a local cache/staging path.
        return Path(self.store_local)
