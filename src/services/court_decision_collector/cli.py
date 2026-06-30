from __future__ import annotations

import argparse
import logging

from .config import CourtDecisionCollectorConfig
from .fixtures import FixtureCourtDecisionSource, sample_court_decision_records
from .infosud_source import InfoSudSourceClient
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
    parser.add_argument(
        "--run-service",
        action="store_true",
        help="Run the collector loop until the source has no more decisions.",
    )
    parser.add_argument("--page", type=int, default=0, help="InfoSud list page for live import.")
    parser.add_argument("--limit", type=int, default=None, help="Number of decisions to import.")
    parser.add_argument("--max-pages", type=int, default=0, help="Optional max pages for bounded loop runs.")
    parser.add_argument(
        "--stop-after-decisions",
        type=int,
        default=0,
        help="Stop after N processed decisions to test restart-safe resume.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = CourtDecisionCollectorConfig.from_env()
    config.validate()
    store = PostgresCourtDecisionStore.from_config(config)
    print("court_decision_collector initializing_postgres")
    store.initialize()

    def console_log(message: str) -> None:
        print(f"court_decision_collector {message}", flush=True)

    source = FixtureCourtDecisionSource() if args.fixture_source else InfoSudSourceClient(base_url=config.source_base_url)
    service = CourtDecisionCollectorService(store=store, source=source, progress_logger=console_log)
    limit = args.limit or config.default_limit
    if args.run_service:
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


if __name__ == "__main__":
    main()
