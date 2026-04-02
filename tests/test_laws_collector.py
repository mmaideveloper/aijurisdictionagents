from __future__ import annotations

from datetime import date
from pathlib import Path

from services.laws_collector import (
    LawsCollectorConfig,
    SlovLexImportPlanner,
    SlovLexSequentialImportRunner,
    SlovakLawsCollectorService,
    SqliteLawStore,
    get_country_laws_collector_definition,
)
from services.laws_collector.import_planner import ImportTarget
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
        initial_import_from=date(1993, 1, 1),
        historical_import_from=date(1993, 1, 1),
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
    assert overview[0].parent_law_year is None
    assert overview[0].parent_law_number is None


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
    assert overview[2].law_number == 421
    assert overview[2].parent_law_year == 2025
    assert overview[2].parent_law_number == 25


def test_laws_collector_config_resolves_relative_db_from_repo_root(monkeypatch) -> None:
    monkeypatch.delenv("LAWS_DB_LOCAL", raising=False)

    config = LawsCollectorConfig.from_env()

    assert config.db_path.name == "sk_laws.sqlite3"
    assert config.db_path.parent.name == "sqlite"
    assert config.db_path.parent.parent.name == "laws-collector"
    assert config.db_path.parent.parent.parent.name == "storage"
    assert config.db_path.parent.parent.parent.parent.name == "runs"
    assert config.db_path.parent.parent.parent.parent.parent == Path(__file__).resolve().parents[1]
    assert config.country_db_name == "laws_sk"
    assert config.initial_import_from == date(1993, 1, 1)
    assert config.historical_import_from == date(1993, 1, 1)


def test_laws_collector_update_plan_detects_changes(tmp_path: Path) -> None:
    _, service = _build_service(tmp_path)

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


def test_slovlex_import_planner_starts_from_1_1993_without_progress(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    planner = SlovLexImportPlanner(config=service.config)
    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=planner.initial_year,
    )

    plan = planner.build_plan(progress=progress, today=date(2026, 3, 30))

    assert plan.initial_year == 1993
    assert plan.next_target == ImportTarget(year=1993, number=1)
    assert plan.last_processed_law is None
    assert plan.stop_when_missing_current_year is False


def test_slovlex_import_planner_persists_next_law_after_processed_probe(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    planner = SlovLexImportPlanner(config=service.config)
    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=planner.initial_year,
    )

    updated = planner.mark_processed(
        progress,
        target=ImportTarget(year=1993, number=1),
        processed_at="2026-03-30T12:00:00Z",
    )
    store.save_collector_progress(updated)
    reloaded = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=planner.initial_year,
    )

    assert reloaded.last_processed_law == "1/1993"
    assert reloaded.next_probe_law == "2/1993"
    assert reloaded.last_collector_run_at == "2026-03-30T12:00:00Z"


def test_slovlex_import_planner_jumps_to_next_year_on_missing_past_year(tmp_path: Path) -> None:
    _, service = _build_service(tmp_path)
    planner = SlovLexImportPlanner(config=service.config)
    progress = planner.initial_progress().evolve(
        last_processed_at="2026-03-30T12:00:00Z",
        last_processed_law_year=1993,
        last_processed_law_number=234,
        next_probe_law_year=1993,
        next_probe_law_number=235,
    )

    updated, stopped = planner.mark_missing(
        progress,
        target=ImportTarget(year=1993, number=235),
        observed_at="2026-03-30T13:00:00Z",
        today=date(2026, 3, 30),
    )

    assert stopped is False
    assert updated.next_probe_law == "1/1994"
    assert updated.last_processed_law == "234/1993"
    assert updated.last_collector_run_at == "2026-03-30T13:00:00Z"


def test_slovlex_import_planner_stops_on_missing_current_year_and_retries_same_law(tmp_path: Path) -> None:
    _, service = _build_service(tmp_path)
    planner = SlovLexImportPlanner(config=service.config)
    progress = planner.initial_progress().evolve(
        last_processed_at="2026-03-30T12:00:00Z",
        last_processed_law_year=2026,
        last_processed_law_number=234,
        next_probe_law_year=2026,
        next_probe_law_number=235,
    )

    updated, stopped = planner.mark_missing(
        progress,
        target=ImportTarget(year=2026, number=235),
        observed_at="2026-03-30T13:00:00Z",
        today=date(2026, 3, 30),
    )

    assert stopped is True
    assert updated.next_probe_law == "235/2026"
    assert updated.last_processed_law == "234/2026"
    assert updated.last_collector_run_at == "2026-03-30T13:00:00Z"


def test_slovlex_sequential_import_runner_updates_progress_until_current_year_gap(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    runner = SlovLexSequentialImportRunner(config=service.config, store=store)

    def fake_probe(*, target: ImportTarget, timeout_seconds: float) -> object:
        outcomes = {
            (1993, 1): True,
            (1993, 2): False,
            (1994, 1): True,
            (1994, 2): False,
        }
        exists = outcomes[(target.year, target.number)]
        return type(
            "Probe",
            (),
            {
                "target": target,
                "exists": exists,
                "status_code": 200 if exists else 404,
                "url": target.url,
            },
        )()

    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=1993,
    )
    progress = progress.evolve(
        next_probe_law_year=1993,
        next_probe_law_number=1,
    )
    store.save_collector_progress(progress)
    runner._probe_target = fake_probe  # type: ignore[method-assign]

    summary = runner.run(max_probes=4, today=date(1994, 3, 30))
    reloaded = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=1993,
    )

    assert summary.probes == 4
    assert summary.laws_found == 2
    assert summary.years_advanced == 1
    assert summary.stopped_on_current_year_gap is True
    assert summary.next_law_to_check == "2/1994"
    assert reloaded.next_probe_law == "2/1994"


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
        initial_import_from=date(1993, 1, 1),
        historical_import_from=date(1993, 1, 1),
    )

    assert config.country_db_name == "laws_cz"
    assert config.db_path.name == "cz_laws.sqlite3"
