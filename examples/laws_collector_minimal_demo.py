from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile

from services.laws_collector import (
    LawsCollectorConfig,
    SlovLexImportPlanner,
    SqliteLawStore,
    get_country_laws_collector_definition,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = LawsCollectorConfig(
            country_code="SK",
            db_backend="sqlite",
            db_local=str(root / "laws.sqlite3"),
            db_cloud="",
            storage_local="",
            storage_cloud="",
            delta_poll_hours=3,
            initial_import_from=date(1945, 1, 1),
            historical_import_from=date(1945, 1, 1),
        )
        collector_definition = get_country_laws_collector_definition(config.country_code)
        store = SqliteLawStore.from_config(config)
        store.initialize()
        service = collector_definition.create_service(config=config, store=store)
        planner = SlovLexImportPlanner(config=config)

        baseline = collector_definition.baseline_snapshots()
        delta = collector_definition.delta_snapshots()
        baseline_summary = service.sync(baseline)
        delta_summary = service.sync(delta)
        update_plan = service.plan_updates(known_snapshots=baseline, latest_snapshots=delta)
        progress = store.get_or_create_collector_progress(
            country_code=config.country_code,
            source_system="slov-lex",
            initial_year=planner.initial_year,
        )
        import_plan = planner.build_plan(progress=progress, today=date(2026, 3, 30))
        counts = store.get_counts()
        overview = store.list_document_overview()

        print("Collector:", collector_definition.collector_name)
        print("Country:", config.country_code)
        print("Cloud DB name:", collector_definition.cloud_database_name)
        print("Baseline sync:", baseline_summary)
        print("Delta sync:", delta_summary)
        print("Planned updates:", update_plan.items_with_updates)
        print("Import initial year:", import_plan.initial_year)
        print("Next law to check:", import_plan.next_target.law_id)
        print("Next law URL:", import_plan.next_target.url)
        print("Last processed law:", import_plan.last_processed_law or "")
        print("Last collector run:", import_plan.last_collector_run_at or "")
        print("Documents in DB:", counts.documents)
        print("Versions in DB:", counts.versions)
        print("Provisions in DB:", counts.provisions)
        print("Update events in DB:", counts.update_events)
        print("First document:", overview[0])
        print("SQLite path:", store.db_path)


if __name__ == "__main__":
    main()
