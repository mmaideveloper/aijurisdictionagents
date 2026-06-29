from __future__ import annotations

import argparse
import logging

from .config import CourtDecisionCollectorConfig
from .fixtures import sample_court_decision_records
from .infosud_source import InfoSudSourceClient
from .postgres_store import PostgresCourtDecisionStore
from .service import CourtDecisionCollectorService


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Slovak court decisions into PostgreSQL vectors.")
    parser.add_argument("--fixture", action="store_true", help="Import one bundled fixture decision.")
    parser.add_argument("--live", action="store_true", help="Fetch one page from the InfoSud API.")
    parser.add_argument("--page", type=int, default=0, help="InfoSud list page for live import.")
    parser.add_argument("--limit", type=int, default=None, help="Number of decisions to import.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = CourtDecisionCollectorConfig.from_env()
    config.validate()
    store = PostgresCourtDecisionStore.from_config(config)
    print("court_decision_collector initializing_postgres")
    store.initialize()

    def console_log(message: str) -> None:
        print(f"court_decision_collector {message}", flush=True)

    source = InfoSudSourceClient(base_url=config.source_base_url)
    service = CourtDecisionCollectorService(store=store, source=source, progress_logger=console_log)
    limit = args.limit or config.default_limit
    if args.live:
        summary = service.sync_live_page(page=args.page, size=limit)
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
