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
            initial_import_from=date(2025, 1, 1),
            historical_import_from=date(1946, 1, 1),
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
        plan = service.plan_updates(known_snapshots=baseline, latest_snapshots=delta)
        counts = store.get_counts()
        overview = store.list_document_overview()

        print("Country DB name:", config.country_db_name)
        print("Import plan:", planner.build_plan(initial_window_complete=False))
        print("Collector:", collector_definition.collector_name)
        print("Country:", config.country_code)
        print("Cloud DB name:", collector_definition.cloud_database_name)
        print("Baseline sync:", baseline_summary)
        print("Delta sync:", delta_summary)
        print("Planned updates:", plan.items_with_updates)
        print("Documents in DB:", counts.documents)
        print("Versions in DB:", counts.versions)
        print("Provisions in DB:", counts.provisions)
        print("Update events in DB:", counts.update_events)
        print("First document:", overview[0])
        print("Amendment sample parent law:", (overview[2].law_year, overview[2].law_number), "->", (overview[2].parent_law_year, overview[2].parent_law_number))
        print("SQLite path:", store.db_path)


if __name__ == "__main__":
    main()
