from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class CourtDecisionCollectorConfig:
    db_backend: str
    db_cloud: str
    storage_local: str
    source_base_url: str
    source_timeout_seconds: float
    source_retry_attempts: int
    source_retry_backoff_seconds: float
    poll_hours: int
    embedding_dimensions: int
    default_limit: int
    max_pdf_bytes: int

    @classmethod
    def from_env(cls) -> "CourtDecisionCollectorConfig":
        return cls(
            db_backend=os.getenv("COURT_DECISIONS_DB_BACKEND", "postgres").strip().lower(),
            db_cloud=os.getenv("COURT_DECISIONS_DB_CLOUD", "").strip(),
            storage_local=os.getenv(
                "COURT_DECISIONS_STORAGE_LOCAL",
                "./runs/storage/court-decision-collector/files/sk",
            ).strip(),
            source_base_url=os.getenv(
                "COURT_DECISIONS_SOURCE_BASE_URL",
                "https://obcan.justice.sk/pilot/api/ress-isu-service/v1",
            ).strip().rstrip("/"),
            source_timeout_seconds=float(os.getenv("COURT_DECISIONS_SOURCE_TIMEOUT_SECONDS", "90")),
            source_retry_attempts=int(os.getenv("COURT_DECISIONS_SOURCE_RETRY_ATTEMPTS", "3")),
            source_retry_backoff_seconds=float(
                os.getenv("COURT_DECISIONS_SOURCE_RETRY_BACKOFF_SECONDS", "5")
            ),
            poll_hours=int(os.getenv("COURT_DECISIONS_WORKER_POLL_HOURS", "1")),
            embedding_dimensions=int(os.getenv("COURT_DECISIONS_EMBEDDING_DIMENSIONS", "32")),
            default_limit=int(os.getenv("COURT_DECISIONS_IMPORT_LIMIT", "25")),
            max_pdf_bytes=_env_int("COURT_DECISIONS_MAX_PDF_BYTES", 26214400),
        )

    def validate(self) -> None:
        if self.db_backend != "postgres":
            raise ValueError("COURT_DECISIONS_DB_BACKEND currently supports only postgres")
        if not self.db_cloud:
            raise ValueError("COURT_DECISIONS_DB_CLOUD must point to the dedicated PostgreSQL database")
        if self.source_timeout_seconds <= 0:
            raise ValueError("COURT_DECISIONS_SOURCE_TIMEOUT_SECONDS must be > 0")
        if self.source_retry_attempts < 1:
            raise ValueError("COURT_DECISIONS_SOURCE_RETRY_ATTEMPTS must be >= 1")
        if self.source_retry_backoff_seconds < 0:
            raise ValueError("COURT_DECISIONS_SOURCE_RETRY_BACKOFF_SECONDS must be >= 0")
        if self.poll_hours < 1:
            raise ValueError("COURT_DECISIONS_WORKER_POLL_HOURS must be >= 1")
        if self.embedding_dimensions < 8:
            raise ValueError("COURT_DECISIONS_EMBEDDING_DIMENSIONS must be >= 8")
        if self.default_limit < 1:
            raise ValueError("COURT_DECISIONS_IMPORT_LIMIT must be >= 1")
        if self.max_pdf_bytes < 1024:
            raise ValueError("COURT_DECISIONS_MAX_PDF_BYTES must be >= 1024")

    @property
    def storage_root(self) -> Path:
        candidate = Path(self.storage_local)
        if candidate.is_absolute():
            return candidate
        return _REPO_ROOT / candidate


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value or value == "unknown-variable":
        return default
    return int(value)
