from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import time

from aijurisdictionagents import __version__
from aijurisdictionagents.llm import load_embedding_runtime_summary_from_env
from aijurisdictionagents.telemetry import configure_worker_telemetry

from .country_registry import get_country_laws_collector_definition
from .config import LawsCollectorConfig
from .postgres_store import PostgresLawStore
from .slovlex_process import SlovLexSequentialImportRunner
from .sqlite_store import SqliteLawStore

logger = logging.getLogger("laws-collector")


@dataclass(frozen=True)
class WorkerOptions:
    fixture: str
    poll_seconds: int
    max_cycles: int
    max_probes: int
    max_running_minutes: int

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

        max_running_minutes = int(os.getenv("LAWS_COLLECTOR_MAX_RUNNING_TIME", "60"))
        if max_running_minutes < 0:
            raise ValueError("LAWS_COLLECTOR_MAX_RUNNING_TIME must be >= 0")

        return cls(
            fixture=fixture,
            poll_seconds=poll_seconds,
            max_cycles=max_cycles,
            max_probes=max_probes,
            max_running_minutes=max_running_minutes,
        )


def run_worker() -> None:
    telemetry_mode = configure_worker_telemetry(
        service_name="laws-collector",
        service_version=__version__,
        logger_name="laws-collector",
    )
    config = LawsCollectorConfig.from_env()
    embedding_runtime = load_embedding_runtime_summary_from_env()
    collector_definition = get_country_laws_collector_definition(config.country_code)
    store = SqliteLawStore.from_config(config) if config.db_backend == "sqlite" else PostgresLawStore.from_config(config)
    store.initialize()
    service = collector_definition.create_service(config=config, store=store)

    options = WorkerOptions.from_env()
    started_at = time.monotonic()
    cycle = 0
    logger.info(
        "[laws-collector] startup "
        f"telemetry_mode={telemetry_mode} "
        f"country={config.country_code} db_backend={config.db_backend} "
        f"embedding_option={embedding_runtime.option} "
        f"embedding_model={embedding_runtime.model}"
    )

    try:
        while True:
            cycle += 1
            if options.fixture == "live":
                max_running_seconds = 0.0
                if _is_azure_runtime() and options.max_running_minutes > 0:
                    max_running_seconds = max(0.0, (options.max_running_minutes * 60) - (time.monotonic() - started_at))
                    if max_running_seconds <= 0:
                        logger.info(
                            "[laws-collector] worker stopped after max running time "
                            "max_running_minutes=%s elapsed_seconds=%.1f",
                            options.max_running_minutes,
                            time.monotonic() - started_at,
                        )
                        return
                summary = SlovLexSequentialImportRunner(
                    config=config,
                    store=store,
                    service=service,
                ).run(max_probes=options.max_probes, max_running_seconds=max_running_seconds)
                logger.info(
                    f"[laws-collector] collector={collector_definition.collector_name} "
                    f"country={config.country_code} cycle={cycle} fixture=live "
                    f"probes={summary.probes} max_probes={options.max_probes} laws_found={summary.laws_found} "
                    f"years_advanced={summary.years_advanced} "
                    f"stopped_on_current_year_gap={str(summary.stopped_on_current_year_gap).lower()} "
                    f"last_processed_law={summary.last_processed_law or ''} "
                    f"last_processed_at={summary.last_processed_at or ''} "
                    f"next_law_to_check={summary.next_law_to_check}"
                )
                if summary.stopped_due_to_max_running_time:
                    logger.info(
                        "[laws-collector] worker stopped during live probing after max running time "
                        "max_running_minutes=%s elapsed_seconds=%.1f",
                        options.max_running_minutes,
                        time.monotonic() - started_at,
                    )
                    return
            else:
                snapshots = (
                    collector_definition.baseline_snapshots()
                    if options.fixture == "baseline"
                    else collector_definition.delta_snapshots()
                )
                summary = service.sync(snapshots)
                logger.info(
                    f"[laws-collector] collector={collector_definition.collector_name} "
                    f"country={config.country_code} cycle={cycle} fixture={options.fixture} "
                    f"processed={summary.processed} new_documents={summary.new_documents} "
                    f"new_versions={summary.new_versions} metadata_updates={summary.metadata_updates} "
                    f"skipped={summary.skipped}"
                )

            if _is_azure_runtime() and options.max_running_minutes > 0:
                elapsed_seconds = time.monotonic() - started_at
                max_running_seconds = options.max_running_minutes * 60
                if elapsed_seconds >= max_running_seconds:
                    logger.info(
                        "[laws-collector] worker stopped after max running time "
                        "max_running_minutes=%s elapsed_seconds=%.1f",
                        options.max_running_minutes,
                        elapsed_seconds,
                    )
                    return

            if options.max_cycles > 0 and cycle >= options.max_cycles:
                logger.info("[laws-collector] worker stopped after max cycles")
                return

            time.sleep(options.poll_seconds)
    except Exception:
        logger.exception("[laws-collector] worker failed")
        raise


def _is_azure_runtime() -> bool:
    return os.getenv("LAWS_DB_BACKEND", "").strip().lower() == "postgres"
