from __future__ import annotations

from datetime import date
import os

import psycopg

from services.laws_collector import (
    LawsCollectorConfig,
    PostgresLawStore,
    SlovLexSequentialImportRunner,
    SlovakLawsCollectorService,
)


def main() -> None:
    db_cloud = os.getenv(
        "LAWS_DB_CLOUD",
        "postgresql://postgres:postgres@127.0.0.1:5433/laws_sk",
    ).strip()
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="postgres",
        db_local="",
        db_cloud=db_cloud,
        storage_local="./runs/storage/laws-collector/files/sk",
        storage_cloud="",
        delta_poll_hours=3,
        initial_import_from=date(1993, 1, 1),
        historical_import_from=date(1993, 1, 1),
    )
    store = PostgresLawStore.from_config(config)
    service = SlovakLawsCollectorService(config=config, store=store)
    runner = SlovLexSequentialImportRunner(config=config, store=store, service=service)
    summary = runner.run(max_probes=1)

    with psycopg.connect(db_cloud) as conn:
        law_row = conn.execute(
            """
            SELECT d.law_year, d.law_number, d.official_name, d.last_download_status,
                   v.version_token, v.embedding_model, v.embedding_dimensions, v.embedding_vector,
                   LENGTH(a.content_text) AS html_text_length
            FROM law_documents AS d
            JOIN law_versions AS v ON v.document_id = d.document_id
            JOIN source_artifacts AS a
              ON a.version_id = v.version_id AND a.artifact_kind = 'html'
            WHERE d.country_code = 'SK' AND d.collection_code = 'ZZ'
              AND d.law_year = 1993 AND d.law_number = 1
            ORDER BY v.created_at
            LIMIT 1
            """
        ).fetchone()
        progress_row = conn.execute(
            """
            SELECT last_processed_law_year, last_processed_law_number,
                   last_processed_at, next_probe_law_year, next_probe_law_number
            FROM collector_progress
            WHERE country_code = 'SK'
            """
        ).fetchone()

    print("Connection:", db_cloud)
    print("Probes:", summary.probes)
    print("Laws found:", summary.laws_found)
    print("First found URL:", summary.first_found_url or "")
    if law_row is None:
        print("Stored law: missing")
    else:
        print("Stored law:", f"{law_row[1]}/{law_row[0]}")
        print("Official name:", law_row[2])
        print("DB status:", law_row[3])
        print("Version token:", law_row[4])
        print("Embedding model:", law_row[5])
        print("Embedding dimensions:", law_row[6])
        print("Vector stored:", bool(law_row[7]))
        print("Stored text length:", law_row[8])
    if progress_row is None:
        print("Collector progress: missing")
    else:
        print("Last processed law:", f"{progress_row[1]}/{progress_row[0]}")
        print("Last processed at:", progress_row[2])
        print("Next law to check:", f"{progress_row[4]}/{progress_row[3]}")


if __name__ == "__main__":
    main()
