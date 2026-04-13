from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

from aijurisdictionagents.llm.embeddings import MockEmbeddingClient
from services.laws_collector import LawsCollectorConfig, SlovakLawsCollectorService, SqliteLawStore
from services.laws_collector.slovak_source_fixtures import baseline_snapshots


def main() -> None:
    demo_root = Path("runs/storage/laws-collector/demo-artifacts")
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="sqlite",
        db_local=str(demo_root / "sqlite" / "laws.sqlite3"),
        db_cloud="",
        storage_local=str(demo_root / "files"),
        storage_cloud="",
        delta_poll_hours=3,
        initial_import_from=date(1993, 1, 1),
        historical_import_from=date(1993, 1, 1),
    )
    store = SqliteLawStore.from_config(config)
    store.initialize()
    service = SlovakLawsCollectorService(
        config=config,
        store=store,
        embedding_client=MockEmbeddingClient(),
    )
    snapshot = baseline_snapshots()[0]
    service.sync((snapshot,))

    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT artifact_kind, storage_backend, storage_path, content_bytes
            FROM source_artifacts
            ORDER BY artifact_kind
            """
        ).fetchall()

    print("Database:", config.db_path)
    for row in rows:
        storage_path = Path(str(row["storage_path"]))
        print(
            f"{row['artifact_kind']}: backend={row['storage_backend']} "
            f"bytes={row['content_bytes']} path={storage_path}"
        )
        print("  exists:", storage_path.exists())


if __name__ == "__main__":
    main()
