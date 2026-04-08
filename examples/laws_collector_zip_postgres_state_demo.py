"""Replay SlovLex ZIP-import states against local PostgreSQL.

Run:
    python examples/laws_collector_zip_postgres_state_demo.py
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
import logging
import shutil
import sys
import tempfile
import zipfile

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

LOG_PATH = REPO_ROOT / "runs" / "laws-collector-zip-postgres-demo.log"
SERVER_URI = "postgresql://postgres:postgres@127.0.0.1:5433"
SCENARIO_DATABASE = "laws_zip_demo"


class DemoIndexLoader:
    def __init__(
        self,
        *,
        archive_export,
        monthly_export,
    ) -> None:
        self.archive_export = archive_export
        self.monthly_export = monthly_export

    def load(self, *, timeout_seconds: float = 30.0):
        from services.laws_collector.slovlex_zip_import import SlovLexExportIndex

        return SlovLexExportIndex(
            archive_export=self.archive_export,
            monthly_export=self.monthly_export,
        )


def main() -> None:
    _configure_logging()
    print(f"Logs: {LOG_PATH}")
    for scenario in (
        _run_archive_then_monthly_scenario,
        _run_monthly_only_after_archive_scenario,
        _run_skip_when_monthly_already_completed_scenario,
    ):
        scenario()


def _run_archive_then_monthly_scenario() -> None:
    from services.laws_collector.slovlex_zip_import import (
        SlovLexArchiveExport,
        SlovLexMonthlyExport,
        SlovLexZipImportRunner,
    )

    _reset_demo_database()
    config, store, service = _build_postgres_service()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        archive_zip = temp_root / "archive" / "export.zip"
        monthly_zip = temp_root / "monthly" / "exportZmeny.zip"
        _create_zip(
            archive_zip,
            laws=[
                (1993, 1, "Prvy zakon", "1993-01-01"),
                (1993, 2, "Druhy zakon", "1993-02-01"),
            ],
        )
        _create_zip(
            monthly_zip,
            laws=[
                (1993, 3, "Treti zakon", "1993-03-01"),
            ],
        )
        summary = SlovLexZipImportRunner(
            config=config,
            store=store,
            service=service,
            export_index_loader=DemoIndexLoader(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-01",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=SlovLexMonthlyExport(
                    range_start="2026-04-02",
                    range_end="2026-04-15",
                    zip_url=monthly_zip.resolve().as_uri(),
                ),
            ),
        ).run()
    _print_scenario_result(
        title="Scenario 1: fresh database imports archive first and then monthly update",
        store=store,
        summary=summary,
        archive_key="slov-lex:zip:archive-seed",
        monthly_key="slov-lex:zip:monthly:2026-04-02_2026-04-15",
    )


def _run_monthly_only_after_archive_scenario() -> None:
    from services.laws_collector.domain import CollectorImportState
    from services.laws_collector.slovlex_zip_import import (
        SlovLexArchiveExport,
        SlovLexMonthlyExport,
        SlovLexZipImportRunner,
    )

    _reset_demo_database()
    config, store, service = _build_postgres_service()
    store.upsert_import_state(
        CollectorImportState(
            country_code="SK",
            source_system="slov-lex",
            import_key="slov-lex:zip:archive-seed",
            import_label="archive seed 2026-05-01",
            source_url="file://seeded/archive/export.zip",
            status="completed",
            started_at="2026-05-01T00:00:00Z",
            last_processed_at="2026-05-01T00:00:00Z",
            last_processed_entry="changed/SK/ZZ/1993/2/19930201.html",
            last_processed_law_year=1993,
            last_processed_law_number=2,
            completed_at="2026-05-01T00:00:00Z",
            metadata={"archive_snapshot_date": "2026-05-01", "phase": "archive"},
        )
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        monthly_zip = temp_root / "monthly" / "exportZmeny.zip"
        _create_zip(
            monthly_zip,
            laws=[
                (1993, 4, "Stvrty zakon", "1993-04-01"),
            ],
        )
        summary = SlovLexZipImportRunner(
            config=config,
            store=store,
            service=service,
            export_index_loader=DemoIndexLoader(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-05-01",
                    part_urls=("file://seeded/archive/export.zip",),
                ),
                monthly_export=SlovLexMonthlyExport(
                    range_start="2026-05-02",
                    range_end="2026-05-15",
                    zip_url=monthly_zip.resolve().as_uri(),
                ),
            ),
        ).run()
    _print_scenario_result(
        title="Scenario 2: archive is already completed so startup imports monthly update only",
        store=store,
        summary=summary,
        archive_key="slov-lex:zip:archive-seed",
        monthly_key="slov-lex:zip:monthly:2026-05-02_2026-05-15",
    )


def _run_skip_when_monthly_already_completed_scenario() -> None:
    from services.laws_collector.domain import CollectorImportState
    from services.laws_collector.slovlex_zip_import import (
        SlovLexArchiveExport,
        SlovLexMonthlyExport,
        SlovLexZipImportRunner,
    )

    _reset_demo_database()
    config, store, service = _build_postgres_service()
    store.upsert_import_state(
        CollectorImportState(
            country_code="SK",
            source_system="slov-lex",
            import_key="slov-lex:zip:archive-seed",
            import_label="archive seed 2026-06-01",
            source_url="file://seeded/archive/export.zip",
            status="completed",
            started_at="2026-06-01T00:00:00Z",
            last_processed_at="2026-06-01T00:00:00Z",
            last_processed_entry="changed/SK/ZZ/1993/2/19930201.html",
            last_processed_law_year=1993,
            last_processed_law_number=2,
            completed_at="2026-06-01T00:00:00Z",
            metadata={"archive_snapshot_date": "2026-06-01", "phase": "archive"},
        )
    )
    store.upsert_import_state(
        CollectorImportState(
            country_code="SK",
            source_system="slov-lex",
            import_key="slov-lex:zip:monthly:2026-06-02_2026-06-15",
            import_label="monthly 2026-06-02..2026-06-15",
            source_url="file://seeded/monthly/exportZmeny.zip",
            status="completed",
            started_at="2026-06-15T00:00:00Z",
            last_processed_at="2026-06-15T00:00:00Z",
            last_processed_entry="changed/SK/ZZ/1993/4/19930401.html",
            last_processed_law_year=1993,
            last_processed_law_number=4,
            completed_at="2026-06-15T00:00:00Z",
            metadata={
                "monthly_range_start": "2026-06-02",
                "monthly_range_end": "2026-06-15",
                "phase": "monthly",
            },
        )
    )
    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=DemoIndexLoader(
            archive_export=SlovLexArchiveExport(
                snapshot_date="2026-06-01",
                part_urls=("file://seeded/archive/export.zip",),
            ),
            monthly_export=SlovLexMonthlyExport(
                range_start="2026-06-02",
                range_end="2026-06-15",
                zip_url="file://seeded/monthly/exportZmeny.zip",
            ),
        ),
    ).run()
    _print_scenario_result(
        title="Scenario 3: monthly update is already completed and no newer one exists, so import is skipped",
        store=store,
        summary=summary,
        archive_key="slov-lex:zip:archive-seed",
        monthly_key="slov-lex:zip:monthly:2026-06-02_2026-06-15",
    )


def _build_postgres_service():
    from aijurisdictionagents.llm.embeddings import MockEmbeddingClient
    from services.laws_collector import LawsCollectorConfig, PostgresLawStore, SlovakLawsCollectorService

    db_uri = f"{SERVER_URI}/{SCENARIO_DATABASE}"
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="postgres",
        db_local="",
        db_cloud=db_uri,
        storage_local="",
        storage_cloud="",
        delta_poll_hours=3,
        initial_import_from=date(1993, 1, 1),
        historical_import_from=date(1993, 1, 1),
        import_mode="zip",
    )
    store = PostgresLawStore.from_config(config)
    service = SlovakLawsCollectorService(
        config=config,
        store=store,
        embedding_client=MockEmbeddingClient(),
    )
    return config, store, service


def _reset_demo_database() -> None:
    from aijurisdictionagents.db_migrations import apply_sql_migrations

    _clean_demo_archive_folders()
    maintenance_uri = f"{SERVER_URI}/postgres"
    with psycopg.connect(maintenance_uri, autocommit=True) as conn:
        conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (SCENARIO_DATABASE,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{SCENARIO_DATABASE}"')
        conn.execute(f'CREATE DATABASE "{SCENARIO_DATABASE}"')
    apply_sql_migrations(
        project="laws",
        db_option="postgres",
        target=f"{SERVER_URI}/{SCENARIO_DATABASE}",
    )


def _clean_demo_archive_folders() -> None:
    for suffix in (
        REPO_ROOT / "archivelaws" / "slovakia" / "archive" / "2026-04-01",
        REPO_ROOT / "archivelaws" / "slovakia" / "archive" / "2026-05-01",
        REPO_ROOT / "archivelaws" / "slovakia" / "archive" / "2026-06-01",
        REPO_ROOT / "archivelaws" / "slovakia" / "monthly" / "2026-04-15",
        REPO_ROOT / "archivelaws" / "slovakia" / "monthly" / "2026-05-15",
        REPO_ROOT / "archivelaws" / "slovakia" / "monthly" / "2026-06-15",
    ):
        shutil.rmtree(suffix, ignore_errors=True)


def _create_zip(
    zip_path: Path,
    *,
    laws: list[tuple[int, int, str, str]],
) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        for year, number, title, effective_from in laws:
            archive.writestr(
                f"changed/SK/ZZ/{year}/{number}/{effective_from.replace('-', '')}.html",
                _build_html(
                    year=year,
                    number=number,
                    title=title,
                    effective_from=effective_from,
                ),
            )


def _build_html(*, year: int, number: int, title: str, effective_from: str) -> str:
    return f"""
    <html>
      <body>
        <h1>{number}/{year} Z. z.</h1>
        <table id="InfoTable">
          <tr><td class="title">Číslo predpisu:</td><td class="value_bold">{number}/{year} Z. z.</td></tr>
          <tr><td class="title">Názov:</td><td class="value">{title}</td></tr>
          <tr><td class="title">Typ:</td><td class="value_bold">Zákon</td></tr>
          <tr><td class="title">Dátum vyhlásenia:</td><td class="value_bold">01.01.{year}</td></tr>
          <tr><td class="title">Dátum účinnosti od:</td><td class="value">{effective_from[8:10]}.{effective_from[5:7]}.{effective_from[0:4]}</td></tr>
        </table>
        <tr class="effectivenessHistoryItem" data-iri="/SK/ZZ/{year}/{number}/{effective_from.replace('-', '')}" data-vyhlasene="0" data-ucinnostod="{effective_from}" data-ucinnostdo=""></tr>
        <div class="text" id="paragraf-1.odsek-1.text">Ukážkový text pre {title}.</div>
      </body>
    </html>
    """


def _print_scenario_result(
    *,
    title: str,
    store,
    summary,
    archive_key: str,
    monthly_key: str,
) -> None:
    archive_state = store.get_import_state(country_code="SK", import_key=archive_key)
    monthly_state = store.get_import_state(country_code="SK", import_key=monthly_key)
    counts = store.get_counts()
    print("")
    print(title)
    print(f"  phase={summary.phase}")
    print(f"  entries_processed={summary.entries_processed}")
    print(f"  processed={summary.sync_summary.processed}")
    print(f"  new_documents={summary.sync_summary.new_documents}")
    print(f"  archive_completed={str(summary.archive_completed).lower()}")
    print(f"  monthly_completed={str(summary.monthly_completed).lower()}")
    print(f"  skipped_as_already_completed={str(summary.skipped_as_already_completed).lower()}")
    print(f"  last_processed_law={summary.last_processed_law or ''}")
    print(f"  counts={asdict(counts)}")
    print(f"  archive_state={_format_state(archive_state)}")
    print(f"  monthly_state={_format_state(monthly_state)}")

def _format_state(state) -> str:
    if state is None:
        return "missing"
    return (
        f"status={state.status}, "
        f"last_processed_law={state.last_processed_law or ''}, "
        f"last_processed_entry={state.last_processed_entry or ''}, "
        f"completed_at={state.completed_at or ''}"
    )


def _configure_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
        ],
        force=True,
    )


if __name__ == "__main__":
    main()
