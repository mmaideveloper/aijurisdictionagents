from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys

from .config import CourtDecisionCollectorConfig
from .fixtures import FixtureCourtDecisionSource, sample_court_decision_records
from .infosud_source import InfoSudSourceClient
from .enrichment import OnDemandCourtDecisionEnricher
from .enrichment_queue import BackgroundCourtDecisionEnricher
from .postgres_store import PostgresCourtDecisionStore
from .service import CourtDecisionCollectorService


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Slovak court decisions into PostgreSQL vectors.")
    parser.add_argument("--fixture", action="store_true", help="Import one bundled fixture decision.")
    parser.add_argument(
        "--fixture-source",
        action="store_true",
        help="Use bundled fixture pages as the source for service-loop testing.",
    )
    parser.add_argument("--live", action="store_true", help="Fetch one page from the InfoSud API.")
    parser.add_argument("--enrich-source-url", default="", help="On-demand enrich one allowlisted InfoSud decision URL.")
    parser.add_argument(
        "--run-enrichment-once",
        action="store_true",
        help="Run one bounded durable background-enrichment cycle (must be enabled by env).",
    )
    parser.add_argument("--enrichment-pause", action="store_true", help="Durably pause enrichment claims.")
    parser.add_argument("--enrichment-resume", action="store_true", help="Resume enrichment claims.")
    parser.add_argument(
        "--enrichment-retention-cleanup",
        action="store_true",
        help="Apply configured raw-text/PDF retention without claiming enrichment work.",
    )
    parser.add_argument(
        "--run-service",
        action="store_true",
        help="Run the long-lived collector service and wait between polls when current.",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run one cursor-safe collector pass until the source has no more decisions.",
    )
    parser.add_argument("--page", type=int, default=0, help="InfoSud list page for live import.")
    parser.add_argument("--limit", type=int, default=None, help="Number of decisions to import.")
    parser.add_argument("--max-pages", type=int, default=0, help="Optional max pages for bounded loop runs.")
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Override the service poll interval. Defaults to COURT_DECISIONS_WORKER_POLL_HOURS.",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        default=0,
        help="Optional test-only cap for service idle cycles. Default 0 runs forever.",
    )
    parser.add_argument(
        "--log-file",
        default="./logs/court-decision-collector.log",
        help="Progress log file. Console logging remains enabled.",
    )
    parser.add_argument(
        "--source-insecure-local-tls",
        action="store_true",
        help="Local Windows runtime workaround only: disable TLS verification for InfoSud HTTPS requests.",
    )
    parser.add_argument(
        "--stop-after-decisions",
        type=int,
        default=0,
        help="Stop after N processed decisions to test restart-safe resume.",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = CourtDecisionCollectorConfig.from_env()
    config.validate()
    store = PostgresCourtDecisionStore.from_config(config)
    progress_logger = TeeProgressLogger(Path(args.log_file))
    progress_logger("initializing_postgres")
    store.initialize()

    if args.source_insecure_local_tls and not args.fixture_source:
        progress_logger("source_tls_verify_disabled scope=local status=warning")
    source = (
        FixtureCourtDecisionSource()
        if args.fixture_source
        else InfoSudSourceClient(
            base_url=config.source_base_url,
            timeout_seconds=config.source_timeout_seconds,
            retry_attempts=config.source_retry_attempts,
            retry_backoff_seconds=config.source_retry_backoff_seconds,
            tls_verify=not args.source_insecure_local_tls,
            progress_logger=progress_logger,
        )
    )
    if args.enrichment_pause and args.enrichment_resume:
        raise ValueError("Choose only one of --enrichment-pause or --enrichment-resume")
    if args.enrichment_pause or args.enrichment_resume:
        store.set_enrichment_paused(
            source_system="infosud",
            paused=args.enrichment_pause,
            reason="operator_requested" if args.enrichment_pause else "",
        )
        print("enrichment_status:", "paused" if args.enrichment_pause else "resumed")
        return

    on_demand_enricher: OnDemandCourtDecisionEnricher | None = None
    background_enricher: BackgroundCourtDecisionEnricher | None = None
    if isinstance(source, InfoSudSourceClient):
        on_demand_enricher = OnDemandCourtDecisionEnricher(
            store=store,
            source=source,
            storage_root=config.storage_root,
            max_pdf_bytes=config.max_pdf_bytes,
        )
        background_enricher = BackgroundCourtDecisionEnricher(
            store=store,
            enricher=on_demand_enricher,
            config=config,
            progress_logger=progress_logger,
        )
    service = CourtDecisionCollectorService(
        store=store,
        source=source,
        progress_logger=progress_logger,
        enrichment_auto_queue=config.enrichment_enabled,
        enrichment_max_attempts=config.enrichment_max_attempts,
        enrichment_cycle_hook=background_enricher.run_cycle if background_enricher else None,
    )
    if args.enrich_source_url:
        if not isinstance(source, InfoSudSourceClient):
            raise ValueError("--enrich-source-url requires the live InfoSud source")
        if on_demand_enricher is None:
            raise RuntimeError("On-demand enricher was not initialized")
        enrichment_result = on_demand_enricher.enrich_source_url(args.enrich_source_url)
        import json
        print(json.dumps(enrichment_result.to_dict(), ensure_ascii=False, indent=2))
        return
    if args.run_enrichment_once:
        if background_enricher is None:
            raise ValueError("--run-enrichment-once requires the live InfoSud source")
        cycle_result = background_enricher.run_cycle()
        print("enrichment_status:", cycle_result.status)
        print("enrichment_processed:", cycle_result.processed)
        print("enrichment_ready:", cycle_result.ready)
        return
    if args.enrichment_retention_cleanup:
        if background_enricher is None:
            raise ValueError("--enrichment-retention-cleanup requires the live InfoSud source")
        retention_result = background_enricher.apply_retention()
        print("enrichment_raw_cleared:", retention_result["raw_cleared"])
        print("enrichment_pdf_cleared:", retention_result["pdf_cleared"])
        return
    limit = args.limit or config.default_limit
    if args.run_service:
        poll_seconds = args.poll_seconds if args.poll_seconds is not None else config.poll_hours * 3600
        summary = service.run_worker_loop(
            page_size=limit,
            poll_seconds=poll_seconds,
            daily_new_limit=config.daily_new_limit,
            discovery_overlap_pages=config.discovery_overlap_pages,
            backfill_pages_per_cycle=config.backfill_pages_per_cycle,
            max_idle_cycles=args.max_idle_cycles,
        )
        scheduler_status = store.get_scheduler_state(source_system=source.source_system).status
    elif args.run_once:
        summary = service.run_priority_cycle(
            page_size=limit,
            daily_new_limit=config.daily_new_limit,
            discovery_overlap_pages=config.discovery_overlap_pages,
            backfill_pages_per_cycle=args.max_pages or config.backfill_pages_per_cycle,
            max_decisions=args.stop_after_decisions,
        )
        scheduler_status = store.get_scheduler_state(source_system=source.source_system).status
        if background_enricher is not None:
            background_enricher.run_cycle()
    elif args.live:
        summary = service.sync_live_page(page=args.page, size=limit)
        scheduler_status = store.status().status
    else:
        summary = service.sync_records(sample_court_decision_records())
        scheduler_status = store.status().status
    print("processed:", summary.processed)
    print("created:", summary.created)
    print("updated:", summary.updated)
    print("unchanged:", summary.unchanged)
    print("last_processed_decision:", summary.last_label)
    print("collector_status:", scheduler_status)


class TeeProgressLogger:
    def __init__(self, log_file: Path) -> None:
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        line = f"{timestamp} court_decision_collector {message}"
        print(line, flush=True)
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")


if __name__ == "__main__":
    main()
