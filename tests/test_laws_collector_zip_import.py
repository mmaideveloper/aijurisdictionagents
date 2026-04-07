from __future__ import annotations

from datetime import date
from pathlib import Path
import zipfile

from aijurisdictionagents.llm.embeddings import MockEmbeddingClient
from services.laws_collector import LawsCollectorConfig, SqliteLawStore, SlovakLawsCollectorService
from services.laws_collector.domain import CollectorImportState
from services.laws_collector.slovlex_zip_import import (
    SlovLexArchiveExport,
    SlovLexExportIndex,
    SlovLexMonthlyExport,
    SlovLexZipImportRunner,
    _extract_zip_archive,
    parse_export_index_html,
)


def _build_service(tmp_path: Path) -> tuple[SqliteLawStore, SlovakLawsCollectorService, LawsCollectorConfig]:
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="sqlite",
        db_local=str(tmp_path / "laws.sqlite3"),
        db_cloud="",
        storage_local="",
        storage_cloud="",
        delta_poll_hours=3,
        initial_import_from=date(1993, 1, 1),
        historical_import_from=date(1993, 1, 1),
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
                    range_start="2026-03-01",
                    range_end="2026-04-01",
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
        import_key="slov-lex:zip:monthly:2026-03-01_2026-04-01",
    )

    assert summary.phase == "monthly"
    assert summary.entries_processed == 2
    assert summary.sync_summary.processed == 2
    assert summary.monthly_completed is True
    assert state is not None
    assert state.status == "completed"
    assert state.last_processed_law == "2/1993"
    assert store.get_counts().documents == 2


def test_zip_import_runner_resumes_after_timeout(tmp_path: Path) -> None:
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

    first_runner = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
        monotonic_time_provider=iter([0.0, 0.0, 50.0, 50.0]).__next__,
    )
    first_summary = first_runner.run(max_running_seconds=30)

    assert first_summary.stopped_due_to_max_running_time is True
    assert first_summary.entries_processed == 1

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


def test_zip_import_runner_processes_archive_seed(tmp_path: Path, monkeypatch) -> None:
    store, service, config = _build_service(tmp_path)
    archive_zip = tmp_path / "fixtures" / "export.zip"
    _create_monthly_zip(
        archive_zip,
        laws=[
            (1993, 1, "Prvy zakon", "1993-01-01"),
            (1993, 2, "Druhy zakon", "1993-02-01"),
        ],
    )

    def fake_extract_archive_bundle(*, download_root: Path, extract_root: Path) -> None:
        _extract_zip_archive(zip_path=download_root / "export.zip", extract_root=extract_root)

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=SlovLexArchiveExport(
                    snapshot_date="2026-04-01",
                    part_urls=(archive_zip.resolve().as_uri(),),
                ),
                monthly_export=None,
            )

    monkeypatch.setattr(
        "services.laws_collector.slovlex_zip_import._extract_archive_bundle",
        fake_extract_archive_bundle,
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
