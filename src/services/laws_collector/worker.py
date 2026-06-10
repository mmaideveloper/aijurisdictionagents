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
from .slovlex_zip_import import SlovLexZipImportRunner
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
    import_mode = getattr(config, "import_mode", "zip")
    logger.info(
        "[laws-collector] startup "
        f"telemetry_mode={telemetry_mode} "
        f"country={config.country_code} db_backend={config.db_backend} "
        f"import_mode={import_mode} "
        f"embedding_option={embedding_runtime.option} "
        f"embedding_model={embedding_runtime.model} "
        f"embedding_device={embedding_runtime.device or ''}"
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
                if import_mode == "zip":
                    summary = SlovLexZipImportRunner(
                        config=config,
                        store=store,
                        service=service,
                    ).run(max_running_seconds=max_running_seconds)
                    logger.info(
                        f"[laws-collector] collector={collector_definition.collector_name} "
                        f"country={config.country_code} cycle={cycle} fixture=live import_mode=zip "
                        f"phase={summary.phase} import_key={summary.import_key or ''} "
                        f"entries_processed={summary.entries_processed} "
                        f"processed={summary.sync_summary.processed} "
                        f"new_documents={summary.sync_summary.new_documents} "
                        f"new_versions={summary.sync_summary.new_versions} "
                        f"metadata_updates={summary.sync_summary.metadata_updates} "
                        f"skipped={summary.sync_summary.skipped} "
                        f"archive_completed={str(summary.archive_completed).lower()} "
                        f"monthly_completed={str(summary.monthly_completed).lower()} "
                        f"last_processed_law={summary.last_processed_law or ''}"
                    )
                    if summary.stopped_due_to_max_running_time:
                        logger.info(
                            "[laws-collector] worker stopped during zip import after max running time "
                            "max_running_minutes=%s elapsed_seconds=%.1f",
                            options.max_running_minutes,
                            time.monotonic() - started_at,
                        )
                        return
                    if summary.archive_completed and summary.monthly_completed:
                        tail_summary = SlovLexSequentialImportRunner(
                            config=config,
                            store=store,
                            service=service,
                        ).run(max_probes=options.max_probes, max_running_seconds=max_running_seconds)
                        logger.info(
                            f"[laws-collector] collector={collector_definition.collector_name} "
                            f"country={config.country_code} cycle={cycle} fixture=live import_mode=zip_tail_probe "
                            f"probes={tail_summary.probes} max_probes={options.max_probes} "
                            f"laws_found={tail_summary.laws_found} failed_laws={tail_summary.failed_laws} "
                            f"years_advanced={tail_summary.years_advanced} "
                            f"stopped_on_current_year_gap={str(tail_summary.stopped_on_current_year_gap).lower()} "
                            f"last_processed_law={tail_summary.last_processed_law or ''} "
                            f"next_law_to_check={tail_summary.next_law_to_check}"
                        )
                        if tail_summary.stopped_due_to_max_running_time:
                            logger.info(
                                "[laws-collector] worker stopped during zip tail probe after max running time "
                                "max_running_minutes=%s elapsed_seconds=%.1f",
                                options.max_running_minutes,
                                time.monotonic() - started_at,
                            )
                            return
                        if _is_up_to_date_tail_summary(tail_summary):
                            _log_no_new_laws(config.country_code, tail_summary)
                            logger.info(
                                "[laws-collector] worker stopped because laws collector is up to date "
                                "last_processed_law=%s next_law_to_check=%s",
                                tail_summary.last_processed_law or "",
                                tail_summary.next_law_to_check,
                            )
                            return
                else:
                    summary = SlovLexSequentialImportRunner(
                        config=config,
                        store=store,
                        service=service,
                    ).run(max_probes=options.max_probes, max_running_seconds=max_running_seconds)
                    logger.info(
                        f"[laws-collector] collector={collector_definition.collector_name} "
                        f"country={config.country_code} cycle={cycle} fixture=live import_mode=one_law_url "
                        f"probes={summary.probes} max_probes={options.max_probes} "
                        f"laws_found={summary.laws_found} failed_laws={summary.failed_laws} "
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
                    if _is_up_to_date_tail_summary(summary):
                        _log_no_new_laws(config.country_code, summary)
                        logger.info(
                            "[laws-collector] worker stopped because laws collector is up to date "
                            "last_processed_law=%s next_law_to_check=%s",
                            summary.last_processed_law or "",
                            summary.next_law_to_check,
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


def _is_up_to_date_tail_summary(summary: object) -> bool:
    return (
        bool(getattr(summary, "stopped_on_current_year_gap", False))
        and int(getattr(summary, "failed_laws", 0)) == 0
    )


def _log_no_new_laws(country_code: str, summary: object) -> None:
    last_processed_at = getattr(summary, "last_processed_at", None) or getattr(summary, "last_collector_run_at", None)
    logger.info(
        "[laws-collector] No new laws for %s, last processed law %s at %s",
        country_code,
        getattr(summary, "last_processed_law", None) or "none",
        last_processed_at or "n/a",
    )
