from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SLOVAK_INITIAL_IMPORT_DATE = date(1993, 1, 1)


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
    import_mode: str = "zip"

    @classmethod
    def from_env(cls) -> "LawsCollectorConfig":
        country_code = os.getenv("LAWS_COUNTRY", "SK").strip().upper()
        import_mode = os.getenv("LAWS_COLLECTOR_IMPORT", "zip").strip().lower()
        db_local = os.getenv("LAWS_DB_LOCAL", "").strip()
        storage_local = os.getenv("LAWS_STORAGE_LOCAL", "").strip()

        if not db_local:
            db_local = cls.default_local_db_path_for(country_code)
        if not storage_local:
            storage_local = cls.default_local_storage_path_for(country_code)

        return cls(
            country_code=country_code,
            import_mode=import_mode,
            db_backend=os.getenv("LAWS_DB_BACKEND", "sqlite").strip().lower(),
            db_local=db_local,
            db_cloud=os.getenv("LAWS_DB_CLOUD", "").strip(),
            storage_local=storage_local,
            storage_cloud=os.getenv("LAWS_STORAGE_CLOUD", "").strip(),
            delta_poll_hours=int(os.getenv("LAWS_DELTA_POLL_HOURS", "3")),
            initial_import_from=_SLOVAK_INITIAL_IMPORT_DATE,
            historical_import_from=_SLOVAK_INITIAL_IMPORT_DATE,
        )

    @staticmethod
    def default_local_db_path_for(country_code: str) -> str:
        normalized_country_code = country_code.strip().lower()
        if normalized_country_code == "sk":
            return "./runs/storage/laws-collector/sqlite/sk_laws.sqlite3"
        return f"./runs/storage/laws-collector/sqlite/{normalized_country_code}_laws.sqlite3"

    @staticmethod
    def default_local_storage_path_for(country_code: str) -> str:
        normalized_country_code = country_code.strip().lower()
        return f"./runs/storage/laws-collector/files/{normalized_country_code}"

    def validate(self) -> None:
        if len(self.country_code) != 2 or not self.country_code.isalpha():
            raise ValueError("LAWS_COUNTRY must be a 2-letter ISO code")
        if self.import_mode not in {"one_law_url", "zip"}:
            raise ValueError("LAWS_COLLECTOR_IMPORT must be one of: one_law_url, zip")
        if self.db_backend not in {"sqlite", "postgres"}:
            raise ValueError("LAWS_DB_BACKEND must be one of: sqlite, postgres")
        if self.db_backend == "postgres" and not self.db_cloud:
            raise ValueError("LAWS_DB_CLOUD must be set for postgres backend")
        if self.delta_poll_hours < 1:
            raise ValueError("LAWS_DELTA_POLL_HOURS must be >= 1")
        if self.country_code == "SK":
            if self.initial_import_from != _SLOVAK_INITIAL_IMPORT_DATE:
                raise ValueError("Slovak laws collector initial import date is fixed at 1993-01-01")
            if self.historical_import_from != _SLOVAK_INITIAL_IMPORT_DATE:
                raise ValueError("Slovak laws collector historical import date is fixed at 1993-01-01")

    @property
    def db_path(self) -> Path:
        return _resolve_repo_path(self.db_local)

    @property
    def storage_root(self) -> Path:
        return _resolve_repo_path(self.storage_local)

    @property
    def archive_root(self) -> Path:
        if self.country_code == "SK":
            return _resolve_repo_path("./archivelaws/laws-collection-sk")
        return _resolve_repo_path(f"./archivelaws/{self.country_code.lower()}")

    @property
    def country_db_name(self) -> str:
        return f"laws_{self.country_code.lower()}"


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate
