from __future__ import annotations

import argparse

from .country_registry import get_country_laws_collector_definition
from .config import LawsCollectorConfig
from .postgres_store import PostgresLawStore
from .sqlite_store import SqliteLawStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or update the selected country laws collector store.")
    parser.add_argument(
        "--fixture",
        choices=("baseline", "delta"),
        default="baseline",
        help="Which built-in fixture set to ingest.",
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Only run update-plan detection between baseline and selected fixture.",
    )
    args = parser.parse_args()

    config = LawsCollectorConfig.from_env()
    collector_definition = get_country_laws_collector_definition(config.country_code)
    store = SqliteLawStore.from_config(config) if config.db_backend == "sqlite" else PostgresLawStore.from_config(config)
    store.initialize()
    service = collector_definition.create_service(config=config, store=store)

    baseline = collector_definition.baseline_snapshots()
    snapshots = baseline if args.fixture == "baseline" else collector_definition.delta_snapshots()

    if args.check_updates:
        plan = service.plan_updates(known_snapshots=baseline, latest_snapshots=snapshots)
        print("checked_items:", plan.checked_items)
        print("items_with_updates:", plan.items_with_updates)
        if plan.items:
            print("first_update_item:", plan.items[0])
        return

    summary = service.sync(snapshots)
    counts = store.get_counts()

    print("country:", config.country_code)
    print("collector:", collector_definition.collector_name)
    print("cloud_database_name:", collector_definition.cloud_database_name)
    print("fixture:", args.fixture)
    print("processed:", summary.processed)
    print("new_documents:", summary.new_documents)
    print("new_versions:", summary.new_versions)
    print("metadata_updates:", summary.metadata_updates)
    print("skipped:", summary.skipped)
    print("documents_in_db:", counts.documents)
    print("versions_in_db:", counts.versions)
    print("provisions_in_db:", counts.provisions)
    print("update_events_in_db:", counts.update_events)
    if hasattr(store, "list_document_overview"):
        overview = store.list_document_overview()
        if overview:
            print("first_document:", overview[0])
    if hasattr(store, "db_path"):
        print("db_path:", store.db_path)


if __name__ == "__main__":
    main()
