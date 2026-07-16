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
    service = CourtDecisionCollectorService(store=store, source=source, progress_logger=progress_logger)
    if args.enrich_source_url:
        if not isinstance(source, InfoSudSourceClient):
            raise ValueError("--enrich-source-url requires the live InfoSud source")
        result = OnDemandCourtDecisionEnricher(
            store=store, source=source, storage_root=config.storage_root,
            max_pdf_bytes=config.max_pdf_bytes,
        ).enrich_source_url(args.enrich_source_url)
        import json
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    limit = args.limit or config.default_limit
    if args.run_service:
        poll_seconds = args.poll_seconds if args.poll_seconds is not None else config.poll_hours * 3600
        summary = service.run_worker_loop(
            page_size=limit,
            poll_seconds=poll_seconds,
            max_idle_cycles=args.max_idle_cycles,
        )
        status = store.get_import_state(source_system=source.source_system, cursor_kind="live_loop")
    elif args.run_once:
        summary = service.run_until_current(
            page_size=limit,
            max_pages=args.max_pages,
            stop_after_decisions=args.stop_after_decisions,
        )
        status = store.get_import_state(source_system=source.source_system, cursor_kind="live_loop")
    elif args.live:
        summary = service.sync_live_page(page=args.page, size=limit)
        status = store.status()
    else:
        summary = service.sync_records(sample_court_decision_records())
        status = store.status()
    print("processed:", summary.processed)
    print("created:", summary.created)
    print("updated:", summary.updated)
    print("unchanged:", summary.unchanged)
    print("last_processed_decision:", summary.last_label)
    print("last_source_guid:", summary.last_source_guid)
    print("collector_status:", status.status)
    print("collector_last_processed_at:", status.last_processed_at)


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
