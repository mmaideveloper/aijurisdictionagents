from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class LawsCollectorConfig:
    country_code: str
    db_backend: str
    db_local: str
    db_cloud: str
    storage_local: str
    storage_cloud: str
    delta_poll_hours: int

    @classmethod
    def from_env(cls) -> "LawsCollectorConfig":
        return cls(
            country_code=os.getenv("LAWS_COUNTRY", "SK").strip().upper(),
            db_backend=os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower(),
            db_local=os.getenv("LAWS_DB_LOCAL", "./data/laws/sk_laws.sqlite3").strip(),
            db_cloud=os.getenv("LAWS_DB_CLOUD", "").strip(),
            storage_local=os.getenv("LAWS_STORAGE_LOCAL", "./storage/laws/sk").strip(),
            storage_cloud=os.getenv("LAWS_STORAGE_CLOUD", "").strip(),
            delta_poll_hours=int(os.getenv("LAWS_DELTA_POLL_HOURS", "3")),
        )

    def validate(self) -> None:
        if self.country_code != "SK":
            raise ValueError("laws_collector currently supports only country_code=SK")
        if self.db_backend not in {"sqlite", "postgres"}:
            raise ValueError("LAWS_DB_BACKEND must be one of: sqlite, postgres")
        if self.delta_poll_hours < 1:
            raise ValueError("LAWS_DELTA_POLL_HOURS must be >= 1")

    @property
    def db_path(self) -> Path:
        return Path(self.db_local)

    @property
    def storage_root(self) -> Path:
        return Path(self.storage_local)
