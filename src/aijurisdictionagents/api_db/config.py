from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


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
        raw_db_option = os.getenv("DB_OPTION", "local").strip().lower()
        normalized_db_option = (
            "postgres" if raw_db_option == "postgress" else raw_db_option
        )
        return cls(
            db_option=normalized_db_option,
            storage_option=os.getenv("STORAGE_OPTION", "local").strip().lower(),
            db_local=os.getenv("DB_LOCAL", "./runs/storage/api/sqlite/api.sqlite3").strip(),
            db_cloud=os.getenv("DB_CLOUD", "").strip(),
            store_local=os.getenv("STORE_LOCAL", "./runs/storage/api/files").strip(),
            store_cloud=os.getenv("STORE_CLOUD", "").strip(),
        )

    def validate(self) -> None:
        if self.db_option not in {"local", "postgres", "azure"}:
            raise ValueError("DB_OPTION must be one of: local, postgres, azure")
        if self.storage_option not in {"local", "azure"}:
            raise ValueError("STORAGE_OPTION must be one of: local, azure")
        if self.db_option in {"postgres", "azure"} and not self.db_cloud:
            raise ValueError("DB_CLOUD must be set when DB_OPTION=postgres|azure")
        if self.storage_option == "azure" and not self.store_cloud:
            raise ValueError("STORE_CLOUD must be set when STORAGE_OPTION=azure")

    @property
    def db_path(self) -> Path:
        if self.db_option == "local":
            return _resolve_repo_path(self.db_local)
        # PostgreSQL/Azure mode keeps a local fallback path for diagnostics and migration scripts.
        return _resolve_repo_path(self.db_local)

    @property
    def db_connection_uri(self) -> str:
        if self.db_option == "local":
            return ""
        return self.db_cloud

    @property
    def blob_root(self) -> Path:
        if self.storage_option == "local":
            return Path(self.store_local)
        # Cloud storage configured via connection string (for Azure Blob adapter in prod).
        # During local development/tests this still needs a local cache/staging path.
        return Path(self.store_local)


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
