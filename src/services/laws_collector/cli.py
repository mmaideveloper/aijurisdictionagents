from __future__ import annotations

import argparse

from .country_registry import get_country_laws_collector_definition
from .config import LawsCollectorConfig
from .import_planner import SlovLexImportPlanner
from .postgres_store import PostgresLawStore
from .slovlex_process import SlovLexSequentialImportRunner
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
    parser.add_argument(
        "--plan-import",
        action="store_true",
        help="Print the persisted SlovLex sequential import plan for the configured country.",
    )
    parser.add_argument(
        "--run-sequential-import",
        action="store_true",
        help="Probe SlovLex sequentially by law number/year and persist collector progress.",
    )
    parser.add_argument(
        "--max-probes",
        type=int,
        default=25,
        help="Maximum SlovLex sequential probes to execute in one run.",
    )
    parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=12.0,
        help="Timeout for each SlovLex HTTP probe.",
    )
    args = parser.parse_args()

    config = LawsCollectorConfig.from_env()
    collector_definition = get_country_laws_collector_definition(config.country_code)
    store = SqliteLawStore.from_config(config) if config.db_backend == "sqlite" else PostgresLawStore.from_config(config)
    store.initialize()
    service = collector_definition.create_service(config=config, store=store)

    baseline = collector_definition.baseline_snapshots()
    snapshots = baseline if args.fixture == "baseline" else collector_definition.delta_snapshots()

    if args.plan_import:
        planner = SlovLexImportPlanner(config=config)
        progress = store.get_or_create_collector_progress(
            country_code=config.country_code,
            source_system="slov-lex",
            initial_year=planner.initial_year,
        )
        plan = planner.build_plan(progress=progress)
        print("country:", config.country_code)
        print("database_name:", config.country_db_name)
        print("initial_year:", plan.initial_year)
        print("current_year:", plan.current_year)
        print("last_collector_run_at:", plan.last_collector_run_at or "")
        print("last_processed_at:", plan.last_processed_at or "")
        print("last_processed_law:", plan.last_processed_law or "")
        print("next_law_to_check:", plan.next_target.law_id)
        print("next_law_url:", plan.next_target.url)
        print("stop_when_missing_current_year:", str(plan.stop_when_missing_current_year).lower())
        return

    if args.run_sequential_import:
        runner = SlovLexSequentialImportRunner(config=config, store=store, service=service)
        summary = runner.run(
            max_probes=args.max_probes,
            timeout_seconds=args.probe_timeout_seconds,
        )
        print("country:", config.country_code)
        print("database_name:", config.country_db_name)
        print("probes:", summary.probes)
        print("laws_found:", summary.laws_found)
        print("years_advanced:", summary.years_advanced)
        print("stopped_on_current_year_gap:", str(summary.stopped_on_current_year_gap).lower())
        print("last_checked_law:", summary.last_checked_law or "")
        print("last_processed_law:", summary.last_processed_law or "")
        print("next_law_to_check:", summary.next_law_to_check)
        print("last_collector_run_at:", summary.last_collector_run_at or "")
        print("last_processed_at:", summary.last_processed_at or "")
        print("first_found_url:", summary.first_found_url or "")
        return

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
    print("metadata_in_db:", counts.metadata)
    print("relations_in_db:", counts.relations)
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
