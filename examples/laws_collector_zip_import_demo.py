from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import zipfile

from aijurisdictionagents.llm.embeddings import MockEmbeddingClient
from services.laws_collector import LawsCollectorConfig, SlovakLawsCollectorService, SqliteLawStore
from services.laws_collector.slovlex_zip_import import (
    SlovLexExportIndex,
    SlovLexMonthlyExport,
    SlovLexZipImportRunner,
)


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
        <div class="text" id="paragraf-1.odsek-1.text">Ukazkovy text pre {title}.</div>
      </body>
    </html>
    """


class DemoIndexLoader:
    def __init__(self, zip_uri: str) -> None:
        self.zip_uri = zip_uri

    def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
        return SlovLexExportIndex(
            archive_export=None,
            monthly_export=SlovLexMonthlyExport(
                range_start="2026-03-01",
                range_end="2026-04-01",
                zip_url=self.zip_uri,
            ),
        )


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        zip_path = temp_root / "exportZmeny.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "changed/SK/ZZ/1993/1/19930101.html",
                _build_html(number=1, year=1993, title="Prvy zakon", effective_from="1993-01-01"),
            )
            archive.writestr(
                "changed/SK/ZZ/1993/2/19930201.html",
                _build_html(number=2, year=1993, title="Druhy zakon", effective_from="1993-02-01"),
            )

        config = LawsCollectorConfig(
            country_code="SK",
            db_backend="sqlite",
            db_local=str(temp_root / "laws.sqlite3"),
            db_cloud="",
            storage_local="",
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

        summary = SlovLexZipImportRunner(
            config=config,
            store=store,
            service=service,
            export_index_loader=DemoIndexLoader(zip_path.resolve().as_uri()),
        ).run()

        print("phase:", summary.phase)
        print("entries_processed:", summary.entries_processed)
        print("processed:", summary.sync_summary.processed)
        print("new_documents:", summary.sync_summary.new_documents)
        print("archive_completed:", str(summary.archive_completed).lower())
        print("monthly_completed:", str(summary.monthly_completed).lower())
        print("last_processed_law:", summary.last_processed_law or "")
        print("db_path:", config.db_path)


if __name__ == "__main__":
    main()
