from __future__ import annotations

from dataclasses import dataclass
import os
import time

from aijurisdictionagents.llm import load_embedding_runtime_summary_from_env

from .country_registry import get_country_laws_collector_definition
from .config import LawsCollectorConfig
from .postgres_store import PostgresLawStore
from .slovlex_process import SlovLexSequentialImportRunner
from .sqlite_store import SqliteLawStore


@dataclass(frozen=True)
class WorkerOptions:
    fixture: str
    poll_seconds: int
    max_cycles: int
    max_probes: int

    @classmethod
    def from_env(cls) -> "WorkerOptions":
        fixture = os.getenv("LAWS_WORKER_FIXTURE", "baseline").strip().lower()
        if fixture not in {"baseline", "delta", "live"}:
            raise ValueError("LAWS_WORKER_FIXTURE must be baseline, delta, or live")

        poll_seconds = int(os.getenv("LAWS_WORKER_POLL_SECONDS", "3600"))
        if poll_seconds < 1:
            raise ValueError("LAWS_WORKER_POLL_SECONDS must be >= 1")

        max_cycles = int(os.getenv("LAWS_WORKER_MAX_CYCLES", "0"))
        if max_cycles < 0:
            raise ValueError("LAWS_WORKER_MAX_CYCLES must be >= 0")

        max_probes = int(os.getenv("LAWS_WORKER_MAX_PROBES", "1"))
        if max_probes < 1:
            raise ValueError("LAWS_WORKER_MAX_PROBES must be >= 1")

        return cls(
            fixture=fixture,
            poll_seconds=poll_seconds,
            max_cycles=max_cycles,
            max_probes=max_probes,
        )


def run_worker() -> None:
    config = LawsCollectorConfig.from_env()
    embedding_runtime = load_embedding_runtime_summary_from_env()
    collector_definition = get_country_laws_collector_definition(config.country_code)
    store = SqliteLawStore.from_config(config) if config.db_backend == "sqlite" else PostgresLawStore.from_config(config)
    store.initialize()
    service = collector_definition.create_service(config=config, store=store)

    options = WorkerOptions.from_env()
    cycle = 0
    print(
        "[laws-collector] startup "
        f"country={config.country_code} db_backend={config.db_backend} "
        f"embedding_option={embedding_runtime.option} "
        f"embedding_model={embedding_runtime.model}"
    )

    while True:
        cycle += 1
        if options.fixture == "live":
            summary = SlovLexSequentialImportRunner(
                config=config,
                store=store,
                service=service,
            ).run(max_probes=options.max_probes)
            print(
                f"[laws-collector] collector={collector_definition.collector_name} "
                f"country={config.country_code} cycle={cycle} fixture=live "
                f"probes={summary.probes} max_probes={options.max_probes} laws_found={summary.laws_found} "
                f"years_advanced={summary.years_advanced} "
                f"stopped_on_current_year_gap={str(summary.stopped_on_current_year_gap).lower()} "
                f"last_processed_law={summary.last_processed_law or ''} "
                f"last_processed_at={summary.last_processed_at or ''} "
                f"next_law_to_check={summary.next_law_to_check}"
            )
        else:
            snapshots = (
                collector_definition.baseline_snapshots()
                if options.fixture == "baseline"
                else collector_definition.delta_snapshots()
            )
            summary = service.sync(snapshots)
            print(
                f"[laws-collector] collector={collector_definition.collector_name} "
                f"country={config.country_code} cycle={cycle} fixture={options.fixture} "
                f"processed={summary.processed} new_documents={summary.new_documents} "
                f"new_versions={summary.new_versions} metadata_updates={summary.metadata_updates} "
                f"skipped={summary.skipped}"
            )

        if options.max_cycles > 0 and cycle >= options.max_cycles:
            print("[laws-collector] worker stopped after max cycles")
            return

        time.sleep(options.poll_seconds)
