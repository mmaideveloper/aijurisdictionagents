from __future__ import annotations

from pathlib import Path
import tempfile

from services.laws_collector import LawsCollectorConfig, SlovakLawsCollectorService, SqliteLawStore
from services.laws_collector.source_fixtures import baseline_snapshots, delta_snapshots


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
        store = SqliteLawStore.from_config(config)
        store.initialize()
        service = SlovakLawsCollectorService(config=config, store=store)

        baseline = service.sync(baseline_snapshots())
        delta = service.sync(delta_snapshots())
        plan = service.plan_updates(known_snapshots=baseline_snapshots(), latest_snapshots=delta_snapshots())
        counts = store.get_counts()
        overview = store.list_document_overview()

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
