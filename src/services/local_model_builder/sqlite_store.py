from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from pathlib import Path


@dataclass(frozen=True)
class LawCorpusSummary:
    country_code: str
    total_documents: int
    latest_law_year: int
    latest_law_number: int
    latest_updated_at: datetime

    @property
    def last_processed_law(self) -> str:
        return f"{self.latest_law_number}/{self.latest_law_year}"


class LocalModelSqliteStore:
    def __init__(self, *, metadata_db_path: Path, migration_path: Path) -> None:
        self.metadata_db_path = metadata_db_path
        self.migration_path = migration_path

    def ensure_schema(self) -> None:
        self.metadata_db_path.parent.mkdir(parents=True, exist_ok=True)
        sql = self.migration_path.read_text(encoding="utf-8")
        with sqlite3.connect(self.metadata_db_path) as connection:
            connection.executescript(sql)
            connection.commit()

    def read_law_corpus_summary(self, *, laws_db_path: Path, country_code: str) -> LawCorpusSummary:
        with sqlite3.connect(laws_db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_documents,
                    MAX(law_year) AS latest_law_year,
                    MAX(CASE WHEN law_year = (SELECT MAX(law_year) FROM law_documents WHERE country_code = ?) THEN law_number ELSE NULL END) AS latest_law_number,
                    MAX(updated_at) AS latest_updated_at
                FROM law_documents
                WHERE country_code = ?
                """,
                (country_code, country_code),
            ).fetchone()

        if row is None or row["total_documents"] == 0:
            raise ValueError(f"No law_documents rows found for country {country_code}")

        updated_at_raw = str(row["latest_updated_at"])
        latest_updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
        if latest_updated_at.tzinfo is None:
            latest_updated_at = latest_updated_at.replace(tzinfo=timezone.utc)

        return LawCorpusSummary(
            country_code=country_code,
            total_documents=int(row["total_documents"]),
            latest_law_year=int(row["latest_law_year"]),
            latest_law_number=int(row["latest_law_number"]),
            latest_updated_at=latest_updated_at,
        )

    def persist_model_build(
        self,
        *,
        country_code: str,
        model_name: str,
        model_version: str,
        model_cutoff_time: datetime,
        last_processed_law: str,
        base_model: str,
        adapter_name: str,
        quantization: str,
        training_documents: int,
        output_format: str,
        output_uri: str,
    ) -> None:
        with sqlite3.connect(self.metadata_db_path) as connection:
            connection.execute(
                """
                INSERT INTO local_model_versions (
                    country_code,
                    model_name,
                    model_version,
                    model_cutoff_time,
                    last_processed_law,
                    base_model,
                    adapter_name,
                    quantization,
                    training_documents,
                    output_format,
                    output_uri
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    country_code,
                    model_name,
                    model_version,
                    model_cutoff_time.isoformat(),
                    last_processed_law,
                    base_model,
                    adapter_name,
                    quantization,
                    training_documents,
                    output_format,
                    output_uri,
                ),
            )
            connection.commit()
