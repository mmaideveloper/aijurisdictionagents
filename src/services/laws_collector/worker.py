from __future__ import annotations

from dataclasses import dataclass
import os
import time

from .config import LawsCollectorConfig
from .postgres_store import PostgresLawStore
from .service import SlovakLawsCollectorService
from .source_fixtures import baseline_snapshots, delta_snapshots
from .sqlite_store import SqliteLawStore


@dataclass(frozen=True)
class WorkerOptions:
    fixture: str
    poll_seconds: int
    max_cycles: int

    @classmethod
    def from_env(cls) -> "WorkerOptions":
        fixture = os.getenv("LAWS_WORKER_FIXTURE", "baseline").strip().lower()
        if fixture not in {"baseline", "delta"}:
            raise ValueError("LAWS_WORKER_FIXTURE must be baseline or delta")

        poll_seconds = int(os.getenv("LAWS_WORKER_POLL_SECONDS", "3600"))
        if poll_seconds < 1:
            raise ValueError("LAWS_WORKER_POLL_SECONDS must be >= 1")

        max_cycles = int(os.getenv("LAWS_WORKER_MAX_CYCLES", "0"))
        if max_cycles < 0:
            raise ValueError("LAWS_WORKER_MAX_CYCLES must be >= 0")

        return cls(fixture=fixture, poll_seconds=poll_seconds, max_cycles=max_cycles)


def run_worker() -> None:
    config = LawsCollectorConfig.from_env()
    store = SqliteLawStore.from_config(config) if config.db_backend == "sqlite" else PostgresLawStore.from_config(config)
    store.initialize()
    service = SlovakLawsCollectorService(config=config, store=store)

    options = WorkerOptions.from_env()
    cycle = 0

    while True:
        cycle += 1
        snapshots = baseline_snapshots() if options.fixture == "baseline" else delta_snapshots()
        summary = service.sync(snapshots)

        print(f"[laws-collector] cycle={cycle} fixture={options.fixture} processed={summary.processed} new_documents={summary.new_documents} new_versions={summary.new_versions} metadata_updates={summary.metadata_updates} skipped={summary.skipped}")

        if options.max_cycles > 0 and cycle >= options.max_cycles:
            print("[laws-collector] worker stopped after max cycles")
            return

        time.sleep(options.poll_seconds)
