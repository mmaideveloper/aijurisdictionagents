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
    daily_new_limit: int
    discovery_overlap_pages: int
    backfill_pages_per_cycle: int
    max_pdf_bytes: int
    enrichment_enabled: bool
    enrichment_cycle_limit: int
    enrichment_candidate_limit: int
    enrichment_rate_delay_seconds: float
    enrichment_lease_seconds: int
    enrichment_max_attempts: int
    enrichment_retry_backoff_seconds: int
    enrichment_min_free_disk_bytes: int
    enrichment_raw_retention_days: int
    enrichment_pdf_retention_days: int

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
            daily_new_limit=_env_int("COURT_DECISIONS_DAILY_NEW_LIMIT", 10000),
            discovery_overlap_pages=_env_int("COURT_DECISIONS_DISCOVERY_OVERLAP_PAGES", 2),
            backfill_pages_per_cycle=_env_int("COURT_DECISIONS_BACKFILL_PAGES_PER_CYCLE", 10),
            max_pdf_bytes=_env_int("COURT_DECISIONS_MAX_PDF_BYTES", 26214400),
            enrichment_enabled=_env_bool("COURT_DECISIONS_ENRICHMENT_ENABLED", False),
            enrichment_cycle_limit=_env_int("COURT_DECISIONS_ENRICHMENT_CYCLE_LIMIT", 5),
            enrichment_candidate_limit=_env_int("COURT_DECISIONS_ENRICHMENT_CANDIDATE_LIMIT", 25),
            enrichment_rate_delay_seconds=_env_float(
                "COURT_DECISIONS_ENRICHMENT_RATE_DELAY_SECONDS", 2.0
            ),
            enrichment_lease_seconds=_env_int("COURT_DECISIONS_ENRICHMENT_LEASE_SECONDS", 900),
            enrichment_max_attempts=_env_int("COURT_DECISIONS_ENRICHMENT_MAX_ATTEMPTS", 3),
            enrichment_retry_backoff_seconds=_env_int(
                "COURT_DECISIONS_ENRICHMENT_RETRY_BACKOFF_SECONDS", 300
            ),
            enrichment_min_free_disk_bytes=_env_int(
                "COURT_DECISIONS_ENRICHMENT_MIN_FREE_DISK_BYTES", 1073741824
            ),
            enrichment_raw_retention_days=_env_int(
                "COURT_DECISIONS_ENRICHMENT_RAW_RETENTION_DAYS", 30
            ),
            enrichment_pdf_retention_days=_env_int(
                "COURT_DECISIONS_ENRICHMENT_PDF_RETENTION_DAYS", 30
            ),
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
        if self.daily_new_limit < 1:
            raise ValueError("COURT_DECISIONS_DAILY_NEW_LIMIT must be >= 1")
        if self.discovery_overlap_pages < 1:
            raise ValueError("COURT_DECISIONS_DISCOVERY_OVERLAP_PAGES must be >= 1")
        if self.backfill_pages_per_cycle < 1:
            raise ValueError("COURT_DECISIONS_BACKFILL_PAGES_PER_CYCLE must be >= 1")
        if self.max_pdf_bytes < 1024:
            raise ValueError("COURT_DECISIONS_MAX_PDF_BYTES must be >= 1024")
        if self.enrichment_cycle_limit < 1 or self.enrichment_candidate_limit < 1:
            raise ValueError("Court-decision enrichment cycle/candidate limits must be >= 1")
        if self.enrichment_rate_delay_seconds < 0:
            raise ValueError("COURT_DECISIONS_ENRICHMENT_RATE_DELAY_SECONDS must be >= 0")
        if self.enrichment_lease_seconds < 30:
            raise ValueError("COURT_DECISIONS_ENRICHMENT_LEASE_SECONDS must be >= 30")
        if self.enrichment_max_attempts < 1:
            raise ValueError("COURT_DECISIONS_ENRICHMENT_MAX_ATTEMPTS must be >= 1")
        if self.enrichment_retry_backoff_seconds < 0:
            raise ValueError("COURT_DECISIONS_ENRICHMENT_RETRY_BACKOFF_SECONDS must be >= 0")
        if self.enrichment_min_free_disk_bytes < 0:
            raise ValueError("COURT_DECISIONS_ENRICHMENT_MIN_FREE_DISK_BYTES must be >= 0")
        if self.enrichment_raw_retention_days < 1 or self.enrichment_pdf_retention_days < 1:
            raise ValueError("Court-decision enrichment retention days must be >= 1")

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


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value or value == "unknown-variable":
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value or value == "unknown-variable":
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
