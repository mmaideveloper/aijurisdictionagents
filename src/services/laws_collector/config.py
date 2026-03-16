from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


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
            db_local=os.getenv("LAWS_DB_LOCAL", "./databases/laws-collector/sk_laws.sqlite3").strip(),
            db_cloud=os.getenv("LAWS_DB_CLOUD", "").strip(),
            storage_local=os.getenv("LAWS_STORAGE_LOCAL", "./storage/laws/sk").strip(),
            storage_cloud=os.getenv("LAWS_STORAGE_CLOUD", "").strip(),
            delta_poll_hours=int(os.getenv("LAWS_DELTA_POLL_HOURS", "3")),
        )

    def validate(self) -> None:
        if len(self.country_code) != 2 or not self.country_code.isalpha():
            raise ValueError("LAWS_COUNTRY must be a 2-letter ISO code")
        if self.db_backend not in {"sqlite", "postgres"}:
            raise ValueError("LAWS_DB_BACKEND must be one of: sqlite, postgres")
        if self.db_backend == "postgres" and not self.db_cloud:
            raise ValueError("LAWS_DB_CLOUD must be set for postgres backend")
        if self.delta_poll_hours < 1:
            raise ValueError("LAWS_DELTA_POLL_HOURS must be >= 1")

    @property
    def db_path(self) -> Path:
        return _resolve_repo_path(self.db_local)

    @property
    def storage_root(self) -> Path:
        return Path(self.storage_local)

    @property
    def country_db_name(self) -> str:
        return f"laws_{self.country_code.lower()}"


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
