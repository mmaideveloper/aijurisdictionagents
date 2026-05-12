from __future__ import annotations

from datetime import date
from pathlib import Path
import shutil
import sqlite3
import zipfile

from aijurisdictionagents.llm.embeddings import MockEmbeddingClient
from services.laws_collector import LawsCollectorConfig, SlovakLawsCollectorService, SqliteLawStore
from services.laws_collector.slovlex_zip_import import (
    SlovLexExportIndex,
    SlovLexMonthlyExport,
    SlovLexZipImportRunner,
)


def main() -> int:
    temp_root = Path("runs/storage/laws-collector/archive-inventory-demo")
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)

    db_path = temp_root / "laws.sqlite3"
    zip_path = temp_root / "exportZmeny.zip"
    _create_monthly_zip(zip_path)

    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="sqlite",
        db_local=str(db_path),
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

    class FakeIndexLoader:
        def load(self, *, timeout_seconds: float = 30.0) -> SlovLexExportIndex:
            return SlovLexExportIndex(
                archive_export=None,
                monthly_export=SlovLexMonthlyExport(
                    range_start="2026-03-01",
                    range_end="2026-04-01",
                    zip_url=zip_path.resolve().as_uri(),
                ),
            )

    summary = SlovLexZipImportRunner(
        config=config,
        store=store,
        service=service,
        export_index_loader=FakeIndexLoader(),
    ).run()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT import_key, asset_name, storage_backend, storage_path, checksum, processing_status
            FROM archive_import_assets
            ORDER BY asset_name
            """
        ).fetchall()

    print(
        f"summary processed={summary.sync_summary.processed} "
        f"entries_processed={summary.entries_processed} monthly_completed={summary.monthly_completed}"
    )
    for row in rows:
        print(
            "asset "
            f"import_key={row['import_key']} asset_name={row['asset_name']} "
            f"storage_backend={row['storage_backend']} status={row['processing_status']} "
            f"path={row['storage_path']} checksum={row['checksum']}"
        )

    return 0


def _create_monthly_zip(zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    html = """
    <html>
      <body>
        <h1>1/1993 Z. z.</h1>
        <table id="InfoTable">
          <tr><td class="title">Číslo predpisu:</td><td class="value_bold">1/1993 Z. z.</td></tr>
          <tr><td class="title">Názov:</td><td class="value">Prvy zakon</td></tr>
          <tr><td class="title">Typ:</td><td class="value_bold">Zákon</td></tr>
          <tr><td class="title">Dátum vyhlásenia:</td><td class="value_bold">01.01.1993</td></tr>
          <tr><td class="title">Dátum účinnosti od:</td><td class="value">01.01.1993</td></tr>
        </table>
        <tr class="effectivenessHistoryItem" data-iri="/SK/ZZ/1993/1/19930101" data-vyhlasene="0" data-ucinnostod="1993-01-01" data-ucinnostdo=""></tr>
        <div class="text" id="paragraf-1.odsek-1.text">Ukazkove ustanovenie.</div>
        <div id="iri" data-iri="/SK/ZZ/1993/1/19930101"></div>
      </body>
    </html>
    """
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("changed/SK/ZZ/1993/1/19930101.html", html)


if __name__ == "__main__":
    raise SystemExit(main())
