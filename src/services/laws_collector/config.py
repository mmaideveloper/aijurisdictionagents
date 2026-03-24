from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
    initial_import_from: date
    historical_import_from: date

    @classmethod
    def from_env(cls) -> "LawsCollectorConfig":
        country_code = os.getenv("LAWS_COUNTRY", "SK").strip().upper()
        default_sqlite_path = f"./databases/laws-collector/{country_code.lower()}_laws.sqlite3"
        return cls(
            country_code=country_code,
            db_backend=os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower(),
            db_local=os.getenv("LAWS_DB_LOCAL", default_sqlite_path).strip(),
            db_cloud=os.getenv("LAWS_DB_CLOUD", "").strip(),
            storage_local=os.getenv("LAWS_STORAGE_LOCAL", f"./storage/laws/{country_code.lower()}").strip(),
            storage_cloud=os.getenv("LAWS_STORAGE_CLOUD", "").strip(),
            delta_poll_hours=int(os.getenv("LAWS_DELTA_POLL_HOURS", "3")),
            initial_import_from=_parse_iso_date(os.getenv("LAWS_INITIAL_IMPORT_FROM", "2025-01-01")),
            historical_import_from=_parse_iso_date(os.getenv("LAWS_HISTORICAL_IMPORT_FROM", "1946-01-01")),
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
        if self.historical_import_from > self.initial_import_from:
            raise ValueError("LAWS_HISTORICAL_IMPORT_FROM must be on or before LAWS_INITIAL_IMPORT_FROM")

    @property
    def db_path(self) -> Path:
        return _resolve_repo_path(self.db_local)

    @property
    def storage_root(self) -> Path:
        return _resolve_repo_path(self.storage_local)

    @property
    def country_db_name(self) -> str:
        return f"laws_{self.country_code.lower()}"



def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate



def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {value}") from exc
