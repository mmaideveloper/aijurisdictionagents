from __future__ import annotations

from pathlib import Path
import sqlite3

from services.local_model_builder import (
    LocalModelBuildRequest,
    LocalModelBuilderConfig,
    LocalModelBuilderService,
)


def _create_laws_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE law_documents (
                document_id TEXT PRIMARY KEY,
                country_code TEXT NOT NULL,
                law_year INTEGER NOT NULL,
                law_number INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO law_documents(document_id, country_code, law_year, law_number, updated_at) VALUES(?, ?, ?, ?, ?)",
            (
                ("sk-1000-2025", "SK", 2025, 1000, "2026-03-01T10:00:00+00:00"),
                ("sk-1234-2026", "SK", 2026, 1234, "2026-04-01T10:00:00+00:00"),
            ),
        )
        connection.commit()


def test_local_model_builder_writes_bundle_and_metadata(tmp_path: Path) -> None:
    laws_db = tmp_path / "laws.sqlite3"
    _create_laws_db(laws_db)

    metadata_db = tmp_path / "local_models.sqlite3"
    output_root = tmp_path / "models"

    service = LocalModelBuilderService.from_config(
        config=LocalModelBuilderConfig(
            laws_db_path=str(laws_db),
            metadata_db_path=str(metadata_db),
            output_root=str(output_root),
            sql_assets_root="./databases/local-model-builder/migrations",
        )
    )

    result = service.build_country_model(LocalModelBuildRequest(country_code="SK"))

    assert result.last_processed_law == "1234/2026"
    assert result.training_documents == 2
    assert result.modelfile_path.exists()
    assert result.metadata_path.exists()

    with sqlite3.connect(metadata_db) as connection:
        row = connection.execute(
            "SELECT model_name, model_version, last_processed_law FROM local_model_versions"
        ).fetchone()

    assert row is not None
    assert row[0] == "aj-sk-laws-local"
    assert row[1] == result.model_version
    assert row[2] == "1234/2026"
