from __future__ import annotations

from pathlib import Path
import tempfile

from services.laws_collector import (
    LawsCollectorConfig,
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
        )
        collector_definition = get_country_laws_collector_definition(config.country_code)
        store = SqliteLawStore.from_config(config)
        store.initialize()
        service = collector_definition.create_service(config=config, store=store)

        baseline_snapshots = collector_definition.baseline_snapshots()
        delta_snapshots = collector_definition.delta_snapshots()
        baseline = service.sync(baseline_snapshots)
        delta = service.sync(delta_snapshots)
        plan = service.plan_updates(known_snapshots=baseline_snapshots, latest_snapshots=delta_snapshots)
        counts = store.get_counts()
        overview = store.list_document_overview()

        print("Collector:", collector_definition.collector_name)
        print("Country:", config.country_code)
        print("Cloud DB name:", collector_definition.cloud_database_name)
        print("Baseline sync:", baseline)
        print("Delta sync:", delta)
        print("Planned updates:", plan.items_with_updates)
        print("Documents in DB:", counts.documents)
        print("Versions in DB:", counts.versions)
        print("Provisions in DB:", counts.provisions)
        print("Update events in DB:", counts.update_events)
        print("First document:", overview[0])
        print("SQLite path:", store.db_path)


if __name__ == "__main__":
    main()
