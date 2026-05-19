from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import sqlite3
import threading
import time
import zipfile

from aijurisdictionagents.llm.embeddings import MockEmbeddingClient
from services.laws_collector.archive_storage import StoredArchiveObject
from services.laws_collector import LawsCollectorConfig, SqliteLawStore, SlovakLawsCollectorService
from services.laws_collector.domain import CollectorImportState, SyncSummary
import services.laws_collector.slovlex_zip_import as zip_import
from services.laws_collector.slovlex_zip_import import (
    SlovLexArchiveExport,
    SlovLexExportIndex,
    SlovLexMonthlyExport,
    SlovLexZipImportRunner,
    parse_export_index_html,
)


def _build_service(tmp_path: Path) -> tuple[SqliteLawStore, SlovakLawsCollectorService, LawsCollectorConfig]:
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="sqlite",
        db_local=str(tmp_path / "laws.sqlite3"),
        db_cloud="",
        storage_local=str(tmp_path / "files"),
        storage_cloud="",
        delta_poll_hours=3,
        initial_import_from=date(1945, 1, 1),
        historical_import_from=date(1945, 1, 1),
        import_mode="zip",
    )
    store = SqliteLawStore.from_config(config)
    store.initialize()
    service = SlovakLawsCollectorService(
        config=config,
        store=store,
        embedding_client=MockEmbeddingClient(),
    )
    return store, service, config


def test_slovak_archive_root_defaults_to_laws_collection_sk(tmp_path: Path) -> None:
    _, _, config = _build_service(tmp_path)
    assert config.archive_root.as_posix().endswith("/archivelaws/laws-collection-sk")


def _build_html(*, number: int, year: int, title: str, effective_from: str) -> str:
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
        <div class="text" id="paragraf-1.odsek-1.text">Ustanovenie pre {title}.</div>
        <div id="iri" data-iri="/SK/ZZ/{year}/{number}/{effective_from.replace('-', '')}"></div>
      </body>
    </html>
    """


def _create_monthly_zip(zip_path: Path, *, laws: list[tuple[int, int, str, str]]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        for year, number, title, effective_from in laws:
            archive.writestr(
                f"changed/SK/ZZ/{year}/{number}/{effective_from.replace('-', '')}.html",
                _build_html(number=number, year=year, title=title, effective_from=effective_from),
            )


def test_parse_export_index_html_returns_archive_and_monthly_descriptors() -> None:
    html = """
    <div class="idsk-heading-m">Zmeny v zbierke od 01.03.2026 do 01.04.2026</div>
    <ul class="archive-list">
      <li><a href="https://static.slov-lex.sk/static/exporty/ZZ/exportZmeny.zip">exportZmeny.zip</a></li>
    </ul>
    <div class="idsk-heading-m"> Kompletný archív zbierky zo dňa 01.04.2026</div>
    <ul class="archive-list">
      <li><a href="https://static.slov-lex.sk/static/exporty/ZZ/export.z01">export.z01</a></li>
      <li><a href="https://static.slov-lex.sk/static/exporty/ZZ/export.zip">export.zip</a></li>
    </ul>
    """

    index = parse_export_index_html(html)

    assert index.archive_export == SlovLexArchiveExport(
        snapshot_date="2026-04-01",
        part_urls=(
            "https://static.slov-lex.sk/static/exporty/ZZ/export.z01",
            "https://static.slov-lex.sk/static/exporty/ZZ/export.zip",
        ),
    )
    assert index.monthly_export == SlovLexMonthlyExport(
        range_start="2026-03-01",
        range_end="2026-04-01",
        zip_url="https://static.slov-lex.sk/static/exporty/ZZ/exportZmeny.zip",
    )


def test_zip_import_runner_imports_monthly_zip_and_marks_state_complete(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    monthly_zip = tmp_path / "fixtures" / "exportZmeny.zip"
    _create_monthly_zip(
        monthly_zip,
        laws=[
            (1993, 1, "Prvy zakon", "1993-01-01"),
            (1993, 2, "Druhy zakon", "1993-02-01"),
        ],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=None,
                monthly_export=SlovLexMonthlyExport(
                    range_start="2098-01-01",
                    range_end="2098-02-01",
                    zip_url=monthly_zip.resolve().as_uri(),
                ),
            )

    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    state = store.get_import_state(
        country_code="SK",
        import_key="slov-lex:zip:monthly:2098-01-01_2098-02-01",
    )

    assert summary.phase == "monthly"
    assert summary.entries_processed == 2
    assert summary.sync_summary.processed == 2
    assert summary.monthly_completed is True
    assert state is not None
    assert state.status == "completed"
    assert state.last_processed_law == "2/1993"
    assert store.get_counts().documents == 2


def test_zip_import_runner_persists_html_source_artifact_references(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    monthly_zip = tmp_path / "fixtures" / "exportZmeny.zip"
    _create_monthly_zip(
        monthly_zip,
        laws=[(1993, 1, "Prvy zakon", "1993-01-01")],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=None,
                monthly_export=SlovLexMonthlyExport(
                    range_start="2098-03-01",
                    range_end="2098-04-01",
                    zip_url=monthly_zip.resolve().as_uri(),
                ),
            )

    SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT artifact_kind, storage_backend, storage_path, content_text, content_blob
            FROM source_artifacts
            WHERE artifact_kind = 'html'
            ORDER BY fetched_at
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    assert row["artifact_kind"] == "html"
    assert row["storage_backend"] == "local_file"
    assert Path(str(row["storage_path"])).exists()
    assert row["content_blob"] is None
    assert "Ustanovenie pre Prvy zakon." in str(row["content_text"])


def test_zip_import_runner_resumes_after_timeout(tmp_path: Path, monkeypatch) -> None:
    store, service, config = _build_service(tmp_path)
    monthly_zip = tmp_path / "fixtures" / "exportZmeny.zip"
    _create_monthly_zip(
        monthly_zip,
        laws=[
            (1993, 1, "Prvy zakon", "1993-01-01"),
            (1993, 2, "Druhy zakon", "1993-02-01"),
        ],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=None,
                monthly_export=SlovLexMonthlyExport(
                    range_start="2026-03-01",
                    range_end="2026-04-01",
                    zip_url=monthly_zip.resolve().as_uri(),
                ),
            )

    original_loader = zip_import.load_snapshot_from_entry_file
    loaded_entries: list[str] = []

    def counting_loader(entry: Path):
        loaded_entries.append(entry.name)
        return original_loader(entry)

    monkeypatch.setattr(zip_import, "load_snapshot_from_entry_file", counting_loader)

    first_runner = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
        monotonic_time_provider=iter([0.0, 0.0, 50.0]).__next__,
    )
    first_summary = first_runner.run(max_running_seconds=30)

    assert first_summary.stopped_due_to_max_running_time is True
    assert first_summary.entries_processed == 1
    assert loaded_entries == ["19930101.html"]

    monkeypatch.setattr(zip_import, "load_snapshot_from_entry_file", original_loader)

    second_summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    state = store.get_import_state(
        country_code="SK",
        import_key="slov-lex:zip:monthly:2026-03-01_2026-04-01",
    )

    assert second_summary.entries_processed == 1
    assert second_summary.sync_summary.processed == 1
    assert state is not None
    assert state.status == "completed"
    assert store.get_counts().documents == 2


def test_zip_import_runner_skips_monthly_export_covered_by_completed_archive(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    store.upsert_import_state(
        CollectorImportState(
            country_code="SK",
            source_system="slov-lex",
            import_key="slov-lex:zip:archive-seed",
            import_label="archive seed 2026-04-01",
            source_url="https://static.slov-lex.sk/static/exporty/ZZ/export.zip",
            status="completed",
            started_at="2026-04-01T00:00:00Z",
            last_processed_at="2026-04-01T00:00:00Z",
            last_processed_entry="SK/ZZ/1993/1/19930101.html",
            last_processed_law_year=1993,
            last_processed_law_number=1,
            completed_at="2026-04-01T00:00:00Z",
            metadata={"archive_snapshot_date": "2026-04-01", "phase": "archive"},
        )
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=None,
                monthly_export=SlovLexMonthlyExport(
                    range_start="2026-03-01",
                    range_end="2026-04-01",
                    zip_url="https://static.slov-lex.sk/static/exporty/ZZ/exportZmeny.zip",
                ),
            )

    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    assert summary.phase == "monthly"
    assert summary.skipped_as_already_completed is True
    assert summary.entries_processed == 0
    assert summary.monthly_completed is True


def test_zip_import_runner_skips_already_completed_monthly_export(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    store.upsert_import_state(
        CollectorImportState(
            country_code="SK",
            source_system="slov-lex",
            import_key="slov-lex:zip:archive-seed",
            import_label="archive seed 2026-04-01",
            source_url="https://static.slov-lex.sk/static/exporty/ZZ/export.zip",
            status="completed",
            started_at="2026-04-01T00:00:00Z",
            last_processed_at="2026-04-01T00:00:00Z",
            last_processed_entry="changed/SK/ZZ/1993/1/19930101.html",
            last_processed_law_year=1993,
            last_processed_law_number=1,
            completed_at="2026-04-01T00:00:00Z",
            metadata={"archive_snapshot_date": "2026-04-01", "phase": "archive"},
        )
    )
    store.upsert_import_state(
        CollectorImportState(
            country_code="SK",
            source_system="slov-lex",
            import_key="slov-lex:zip:monthly:2026-04-02_2026-04-15",
            import_label="monthly 2026-04-02..2026-04-15",
            source_url="https://static.slov-lex.sk/static/exporty/ZZ/exportZmeny.zip",
            status="completed",
            started_at="2026-04-15T00:00:00Z",
            last_processed_at="2026-04-15T00:00:00Z",
            last_processed_entry="changed/SK/ZZ/1993/2/19930201.html",
            last_processed_law_year=1993,
            last_processed_law_number=2,
            completed_at="2026-04-15T00:00:00Z",
            metadata={
                "monthly_range_start": "2026-04-02",
                "monthly_range_end": "2026-04-15",
                "phase": "monthly",
            },
        )
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-01",
                    part_urls=("https://static.slov-lex.sk/static/exporty/ZZ/export.zip",),
                ),
                monthly_export=SlovLexMonthlyExport(
                    range_start="2026-04-02",
                    range_end="2026-04-15",
                    zip_url="https://static.slov-lex.sk/static/exporty/ZZ/exportZmeny.zip",
                ),
            )

    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    assert summary.phase == "monthly"
    assert summary.skipped_as_already_completed is True
    assert summary.entries_processed == 0
    assert summary.monthly_completed is True


def test_zip_import_runner_processes_archive_seed(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    archive_zip = tmp_path / "fixtures" / "export.zip"
    _create_monthly_zip(
        archive_zip,
        laws=[
            (1993, 1, "Prvy zakon", "1993-01-01"),
            (1993, 2, "Druhy zakon", "1993-02-01"),
        ],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-01",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=None,
            )

    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    state = store.get_import_state(country_code="SK", import_key="slov-lex:zip:archive-seed")

    assert summary.archive_completed is True
    assert state is not None
    assert state.status == "completed"
    assert state.metadata["archive_snapshot_date"] == "2026-04-01"
    assert store.get_counts().documents == 2


def test_zip_import_runner_skips_laws_before_historical_baseline(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    archive_zip = tmp_path / "fixtures" / "export.zip"
    _create_monthly_zip(
        archive_zip,
        laws=[
            (1944, 1, "Pred baseline", "1944-01-01"),
            (1945, 1, "Baseline", "1945-01-01"),
        ],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-03",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=None,
            )

    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    assert summary.archive_completed is True
    assert store.get_counts().documents == 1


def test_zip_import_runner_updates_collector_progress(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    archive_zip = tmp_path / "fixtures" / "export.zip"
    _create_monthly_zip(
        archive_zip,
        laws=[
            (1993, 1, "Prvy zakon", "1993-01-01"),
            (1993, 2, "Druhy zakon", "1993-02-01"),
        ],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-01",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=None,
            )

    SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=1993,
    )
    assert progress.last_processed_law == "2/1993"
    assert progress.last_processed_at is not None
    assert progress.last_collector_run_at is not None
    assert progress.next_probe_law == "3/1993"


def test_zip_import_runner_sets_progress_to_highest_law_not_last_sorted_entry(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    archive_zip = tmp_path / "fixtures" / "export.zip"
    _create_monthly_zip(
        archive_zip,
        laws=[
            (2026, 100, "Stovka", "2026-01-01"),
            (2026, 9, "Deviatka", "2026-01-01"),
        ],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-02",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=None,
            )

    SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=1945,
    )
    assert progress.last_processed_law == "100/2026"
    assert progress.next_probe_law == "101/2026"


def test_zip_import_runner_imports_law_groups_in_parallel(tmp_path: Path) -> None:
    store, _, base_config = _build_service(tmp_path)
    config = replace(base_config, import_zip_max_threads=3)
    monthly_zip = tmp_path / "fixtures" / "exportZmeny.zip"
    _create_monthly_zip(
        monthly_zip,
        laws=[
            (1993, 1, "Prvy zakon", "1993-01-01"),
            (1993, 2, "Druhy zakon", "1993-02-01"),
            (1993, 3, "Treti zakon", "1993-03-01"),
        ],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=None,
                monthly_export=SlovLexMonthlyExport(
                    range_start="2099-01-01",
                    range_end="2099-01-03",
                    zip_url=monthly_zip.resolve().as_uri(),
                ),
            )

    active_syncs = 0
    max_active_syncs = 0
    lock = threading.Lock()
    all_workers_started = threading.Event()

    class BlockingService:
        def sync(self, snapshots):
            nonlocal active_syncs, max_active_syncs
            with lock:
                active_syncs += 1
                max_active_syncs = max(max_active_syncs, active_syncs)
                if active_syncs == 3:
                    all_workers_started.set()
            all_workers_started.wait(timeout=2)
            time.sleep(0.01)
            with lock:
                active_syncs -= 1
            return SyncSummary(processed=len(tuple(snapshots)))

    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=BlockingService(),
        export_index_loader=FakeIndexLoader(),
    ).run()

    assert summary.entries_processed == 3
    assert max_active_syncs == 3
    state = store.get_import_state(country_code="SK", import_key="slov-lex:zip:monthly:2099-01-01_2099-01-03")
    assert state is not None
    assert state.status == "completed"
    assert state.last_processed_law == "3/1993"


def test_zip_import_runner_reextracts_when_marker_signature_does_not_match(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    archive_root = config.archive_root / "archive" / "2026-04-01"
    extract_root = archive_root / "extract"
    extract_root.mkdir(parents=True, exist_ok=True)
    (extract_root / ".extract.complete").write_text("2026-04-01T00:00:00Z", encoding="utf-8")
    stale_entry = extract_root / "changed" / "SK" / "ZZ" / "1993" / "999" / "19990101.html"
    stale_entry.parent.mkdir(parents=True, exist_ok=True)
    stale_entry.write_text("stale", encoding="utf-8")

    archive_zip = tmp_path / "fixtures" / "export.zip"
    _create_monthly_zip(
        archive_zip,
        laws=[(1993, 1, "Prvy zakon", "1993-01-01")],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-01",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=None,
            )

    SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    assert not stale_entry.exists()
    assert (extract_root / "changed" / "SK" / "ZZ" / "1993" / "1" / "19930101.html").exists()


def test_zip_import_runner_records_archive_assets_and_marks_them_processed(tmp_path: Path) -> None:
    store, service, config = _build_service(tmp_path)
    archive_zip = tmp_path / "fixtures" / "export.zip"
    _create_monthly_zip(
        archive_zip,
        laws=[(1993, 1, "Prvy zakon", "1993-01-01")],
    )

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-01",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=None,
            )

    class FakeArchiveObjectStore:
        def persist_file(self, *, source_path: Path, relative_path: str) -> StoredArchiveObject:
            return StoredArchiveObject(
                storage_backend="azure_blob",
                storage_path=f"https://example.blob.core.windows.net/laws-collection-sk/{relative_path}",
            )

    SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
        archive_object_store=FakeArchiveObjectStore(),
    ).run()

    with sqlite3.connect(config.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT import_key, phase, asset_name, storage_backend, storage_path,
                   processing_status, metadata_json
            FROM archive_import_assets
            WHERE import_key = ?
            """,
            ("slov-lex:zip:archive-seed",),
        ).fetchone()

    assert row is not None
    assert row["phase"] == "archive"
    assert row["asset_name"] == "export.zip"
    assert row["storage_backend"] == "azure_blob"
    assert row["processing_status"] == "processed"
    assert "laws-collection-sk/sk/archive/2026-04-01/download/export.zip" in str(row["storage_path"])
    assert "archive_snapshot_date" in str(row["metadata_json"])
