from __future__ import annotations

from pathlib import Path

from datetime import date

from services.laws_collector import LawsCollectorConfig, SlovLexImportPlanner, SlovakLawsCollectorService, SqliteLawStore
from services.laws_collector.source_fixtures import baseline_snapshots, delta_snapshots
from services.laws_collector import (
    get_country_laws_collector_definition,
)
from services.laws_collector.slovak_laws_collector import SlovakLawsCollectorService
from services.laws_collector.slovak_source_fixtures import baseline_snapshots, delta_snapshots


def _build_service(tmp_path: Path) -> tuple[SqliteLawStore, SlovakLawsCollectorService]:
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="sqlite",
        db_local=str(tmp_path / "laws.sqlite3"),
        db_cloud="",
        storage_local="",
        storage_cloud="",
        delta_poll_hours=3,
        initial_import_from=date(2025, 1, 1),
        historical_import_from=date(1946, 1, 1),
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
    assert overview[0].applicable_to == "all construction permits"
    assert overview[0].superseded_by_url == ""


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
    assert overview[0].superseded_by_url == "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2026/11/"


def test_laws_collector_config_resolves_relative_db_from_repo_root(monkeypatch) -> None:
    monkeypatch.delenv("LAWS_DB_LOCAL", raising=False)

    config = LawsCollectorConfig.from_env()

    assert config.db_path.name == "sk_laws.sqlite3"
    assert config.db_path.parent.name == "laws-collector"
    assert config.db_path.parent.parent.name == "databases"
    assert config.db_path.parent.parent.parent == Path(__file__).resolve().parents[1]
    assert config.country_db_name == "laws_sk"



def test_laws_collector_update_plan_detects_changes(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)

    plan = service.plan_updates(known_snapshots=baseline_snapshots(), latest_snapshots=delta_snapshots())

    assert plan.checked_items == 2
    assert plan.items_with_updates == 2
    assert any(item.reason == "new_document_or_version" for item in plan.items)


def test_laws_collector_config_defaults_to_country_specific_sqlite_db(monkeypatch) -> None:
    monkeypatch.delenv("LAWS_DB_LOCAL", raising=False)
    monkeypatch.setenv("LAWS_COUNTRY", "SK")

    config = LawsCollectorConfig.from_env()

    assert config.db_path.name == "sk_laws.sqlite3"
    assert config.country_db_name == "laws_sk"


def test_slovlex_import_planner_starts_with_2025_then_unblocks_1946_history(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    planner = SlovLexImportPlanner(config=service.config)

    blocked_plan = planner.build_plan(today=date(2026, 3, 23), initial_window_complete=False)
    unblocked_plan = planner.build_plan(today=date(2026, 3, 23), initial_window_complete=True)

    assert blocked_plan.windows[0].stage == "initial_2025_to_today"
    assert blocked_plan.windows[0].start_date.isoformat() == "2025-01-01"
    assert blocked_plan.windows[0].end_date.isoformat() == "2026-03-23"
    assert blocked_plan.windows[1].stage == "historical_1946_to_2024"
    assert blocked_plan.windows[1].start_date.isoformat() == "1946-01-01"
    assert blocked_plan.windows[1].end_date.isoformat() == "2024-12-31"
    assert blocked_plan.windows[1].blocked_by == "initial_2025_to_today"
    assert unblocked_plan.windows[1].blocked_by is None
def test_country_definition_resolves_slovak_collector_and_db_name() -> None:
    definition = get_country_laws_collector_definition("sk")

    assert definition.collector_name == "slovak_laws_collector"
    assert definition.country_code == "SK"
    assert definition.cloud_database_name == "laws_sk"


def test_country_db_name_uses_laws_prefix_for_future_countries() -> None:
    config = LawsCollectorConfig(
        country_code="CZ",
        db_backend="sqlite",
        db_local=LawsCollectorConfig.default_local_db_path_for("CZ"),
        db_cloud="",
        storage_local="",
        storage_cloud="",
        delta_poll_hours=3,
    )

    assert config.country_db_name == "laws_cz"
    assert config.db_path.name == "cz_laws.sqlite3"
