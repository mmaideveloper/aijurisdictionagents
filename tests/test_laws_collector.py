from __future__ import annotations

from pathlib import Path

from services.laws_collector import LawsCollectorConfig, SlovakLawsCollectorService, SqliteLawStore
from services.laws_collector.source_fixtures import baseline_snapshots, delta_snapshots


def _build_service(tmp_path: Path) -> tuple[SqliteLawStore, SlovakLawsCollectorService]:
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="sqlite",
        db_local=str(tmp_path / "laws.sqlite3"),
        db_cloud="",
        storage_local="",
        storage_cloud="",
        delta_poll_hours=3,
    )
    store = SqliteLawStore.from_config(config)
    store.initialize()
    service = SlovakLawsCollectorService(config=config, store=store)
    return store, service


def test_laws_collector_baseline_sync_creates_documents_and_versions(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)

    summary = service.sync(baseline_snapshots())
    counts = store.get_counts()

    assert summary.processed == 2
    assert summary.new_documents == 2
    assert summary.new_versions == 0
    assert summary.skipped == 0
    assert counts.documents == 2
    assert counts.versions == 2
    assert counts.provisions == 3
    assert counts.update_events == 2
    overview = store.list_document_overview()
    assert overview[0].official_name == "Stavebny zakon"
    assert overview[0].lawyer_title == "Stavebny zakon"
    assert overview[0].download_attempt_count == 1


def test_laws_collector_delta_sync_adds_new_act_and_new_version(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)

    service.sync(baseline_snapshots())
    summary = service.sync(delta_snapshots())
    counts = store.get_counts()

    assert summary.processed == 2
    assert summary.new_documents == 1
    assert summary.new_versions == 1
    assert summary.metadata_updates == 0
    assert summary.skipped == 0
    assert counts.documents == 3
    assert counts.versions == 4
    assert counts.provisions == 6
    assert counts.update_events == 4
    overview = store.list_document_overview()
    assert overview[0].download_attempt_count == 2
    assert overview[0].last_download_status == "stored"
