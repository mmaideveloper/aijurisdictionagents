"""Minimal runnable demo for the LocalModelBuilder service.

Run:
    python examples/local_model_builder_minimal_demo.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from services.local_model_builder import (
    LocalModelBuildRequest,
    LocalModelBuilderConfig,
    LocalModelBuilderService,
)


def _seed_demo_laws_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS law_documents (
                document_id TEXT PRIMARY KEY,
                country_code TEXT NOT NULL,
                law_year INTEGER NOT NULL,
                law_number INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        now = datetime.now(tz=timezone.utc).isoformat()
        connection.execute(
            """
            INSERT OR REPLACE INTO law_documents(document_id, country_code, law_year, law_number, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("demo-sk-1234-2026", "SK", 2026, 1234, now),
        )
        connection.commit()


if __name__ == "__main__":
    laws_db = REPO_ROOT / "runs" / "storage" / "local-model-builder" / "sqlite" / "demo_laws.sqlite3"
    _seed_demo_laws_db(laws_db)

    service = LocalModelBuilderService.from_config(config=LocalModelBuilderConfig(laws_db_path=str(laws_db)))
    result = service.build_country_model(LocalModelBuildRequest(country_code="SK"))

    print(f"Built local model: {result.model_name}:{result.model_version}")
    print(f"Cutoff time: {result.model_cutoff_time.isoformat()}")
    print(f"Last processed law: {result.last_processed_law}")
    print(f"Manifest: {result.metadata_path}")
