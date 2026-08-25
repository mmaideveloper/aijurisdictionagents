from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
import time
from typing import Callable

from .config import CourtDecisionCollectorConfig
from .enrichment import OnDemandCourtDecisionEnricher
from .postgres_store import PostgresCourtDecisionStore
from .pseudonymization import UnsafePseudonymizationError

SleepFunction = Callable[[float], None]
FreeDiskFunction = Callable[[Path], int]


@dataclass(frozen=True)
class EnrichmentCycleSummary:
    status: str
    queued: int = 0
    processed: int = 0
    ready: int = 0
    retryable: int = 0
    dead_letter: int = 0
    quarantined: int = 0


class BackgroundCourtDecisionEnricher:
    """Bounded durable queue worker; background mode is disabled unless explicitly enabled."""

    def __init__(
        self,
        *,
        store: PostgresCourtDecisionStore,
        enricher: OnDemandCourtDecisionEnricher,
        config: CourtDecisionCollectorConfig,
        progress_logger: Callable[[str], None] | None = None,
        sleep_fn: SleepFunction = time.sleep,
        free_disk_fn: FreeDiskFunction | None = None,
    ) -> None:
        self.store = store
        self.enricher = enricher
        self.config = config
        self.progress_logger = progress_logger or logging.info
        self.sleep_fn = sleep_fn
        self.free_disk_fn = free_disk_fn or _free_disk_bytes

    def run_cycle(self) -> EnrichmentCycleSummary:
        if not self.config.enrichment_enabled:
            return EnrichmentCycleSummary(status="disabled")
        if self.store.enrichment_is_paused(source_system="infosud"):
            return EnrichmentCycleSummary(status="paused")
        self.apply_retention()
        self.config.storage_root.mkdir(parents=True, exist_ok=True)
        free_bytes = self.free_disk_fn(self.config.storage_root)
        if free_bytes < self.config.enrichment_min_free_disk_bytes:
            self.progress_logger(
                "court_decision_enrichment_paused reason=disk_guard status=paused"
            )
            return EnrichmentCycleSummary(status="disk_guard")

        queued = self.store.enqueue_recent_enrichment_candidates(
            limit=self.config.enrichment_candidate_limit,
            max_attempts=self.config.enrichment_max_attempts,
            priority_class="background",
        )
        processed = ready = retryable = dead_letter = quarantined = 0
        for index in range(self.config.enrichment_cycle_limit):
            if self.store.enrichment_is_paused(source_system="infosud"):
                return EnrichmentCycleSummary(
                    status="paused",
                    queued=queued,
                    processed=processed,
                    ready=ready,
                    retryable=retryable,
                    dead_letter=dead_letter,
                    quarantined=quarantined,
                )
            item = self.store.claim_next_enrichment(
                lease_seconds=self.config.enrichment_lease_seconds
            )
            if item is None:
                break
            processed += 1
            try:
                self.enricher.enrich_source_url(
                    item.source_url,
                    priority_class=item.priority_class,
                )
                if not self.store.complete_enrichment_work(item):
                    raise RuntimeError("Enrichment lease was lost before completion")
                ready += 1
            except UnsafePseudonymizationError as exc:
                self.store.quarantine_enrichment_work(item, error_type=type(exc).__name__)
                quarantined += 1
                self.progress_logger(
                    "court_decision_enrichment_quarantined "
                    "status=quarantined error_type=UnsafePseudonymizationError"
                )
            except Exception as exc:
                state = self.store.retry_enrichment_work(
                    item,
                    error_type=type(exc).__name__,
                    backoff_seconds=self.config.enrichment_retry_backoff_seconds,
                )
                if state == "dead_letter":
                    dead_letter += 1
                else:
                    retryable += 1
                self.progress_logger(
                    "court_decision_enrichment_failed "
                    f"status={state} error_type={type(exc).__name__}"
                )
            if index + 1 < self.config.enrichment_cycle_limit:
                self.sleep_fn(self.config.enrichment_rate_delay_seconds)

        status = "ready" if processed else "idle"
        self.progress_logger(
            "court_decision_enrichment_cycle_completed "
            f"status={status} queued={queued} processed={processed} ready={ready} "
            f"retryable={retryable} dead_letter={dead_letter} quarantined={quarantined}"
        )
        return EnrichmentCycleSummary(
            status=status,
            queued=queued,
            processed=processed,
            ready=ready,
            retryable=retryable,
            dead_letter=dead_letter,
            quarantined=quarantined,
        )

    def apply_retention(self) -> dict[str, int]:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        raw_before = _iso(now - timedelta(days=self.config.enrichment_raw_retention_days))
        pdf_before = _iso(now - timedelta(days=self.config.enrichment_pdf_retention_days))
        root = self.config.storage_root.resolve()
        cleared_raw = cleared_pdf = rejected_pdf_path = 0
        for artifact in self.store.expired_enrichment_artifacts(
            raw_before=raw_before,
            pdf_before=pdf_before,
        ):
            clear_pdf = artifact.pdf_expired
            if clear_pdf and artifact.pdf_path:
                candidate = Path(artifact.pdf_path).resolve()
                if not candidate.is_relative_to(root):
                    clear_pdf = False
                    rejected_pdf_path += 1
                elif candidate.is_file():
                    candidate.unlink()
            self.store.clear_expired_enrichment_artifact(
                version_id=artifact.version_id,
                clear_raw=artifact.raw_expired,
                clear_pdf=clear_pdf,
            )
            cleared_raw += int(artifact.raw_expired)
            cleared_pdf += int(clear_pdf)
        self.progress_logger(
            "court_decision_enrichment_retention_completed "
            f"raw_cleared={cleared_raw} pdf_cleared={cleared_pdf} "
            f"rejected_pdf_paths={rejected_pdf_path}"
        )
        return {
            "raw_cleared": cleared_raw,
            "pdf_cleared": cleared_pdf,
            "rejected_pdf_paths": rejected_pdf_path,
        }


def _free_disk_bytes(path: Path) -> int:
    return int(shutil.disk_usage(path).free)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
