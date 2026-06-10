from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
import logging
from pathlib import Path
import sqlite3
import unicodedata

from aijurisdictionagents.llm.embeddings import EmbeddingBatchResult, MockEmbeddingClient
import aijurisdictionagents.llm.embeddings as embedding_module
from services.laws_collector import (
    LawsCollectorConfig,
    LawMetadataRecord,
    LawRelationRecord,
    LawSnapshot,
    SlovLexImportPlanner,
    SlovLexSequentialImportRunner,
    SlovakLawsCollectorService,
    SqliteLawStore,
    get_country_laws_collector_definition,
)
from services.laws_collector.import_planner import ImportTarget
from services.laws_collector.slovlex_live_source import FetchedResource, SlovLexLiveSnapshotLoader
from services.laws_collector.slovak_source_fixtures import baseline_snapshots, delta_snapshots
from services.laws_collector.worker import WorkerOptions
import services.laws_collector.worker as laws_collector_worker
import services.laws_collector.slovlex_live_source as slovlex_live_source


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return " ".join(normalized.encode("ascii", "ignore").decode("ascii").split())


def _build_service(tmp_path: Path) -> tuple[SqliteLawStore, SlovakLawsCollectorService]:
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
    )
    store = SqliteLawStore.from_config(config)
    store.initialize()
    service = SlovakLawsCollectorService(
        config=config,
        store=store,
        embedding_client=MockEmbeddingClient(),
    )
    return store, service


def _get_embedding_metadata(store: SqliteLawStore, *, law_year: int, law_number: int) -> tuple[str, int, list[float]]:
    with store._connect() as conn:  # noqa: SLF001 - test-only verification of persisted values
        row = conn.execute(
            """
            SELECT v.embedding_model, v.embedding_dimensions, v.embedding_vector
            FROM law_versions AS v
            JOIN law_documents AS d ON d.document_id = v.document_id
            WHERE d.law_year = ? AND d.law_number = ?
            ORDER BY v.created_at
            LIMIT 1
            """,
            (law_year, law_number),
        ).fetchone()
    assert row is not None
    return (
        str(row["embedding_model"]),
        int(row["embedding_dimensions"]),
        json.loads(str(row["embedding_vector"])),
    )


def _get_law_metadata(
    store: SqliteLawStore,
    *,
    law_year: int,
    law_number: int,
) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with store._connect() as conn:  # noqa: SLF001 - test-only verification of persisted values
        metadata_row = conn.execute(
            """
            SELECT m.*
            FROM law_metadata AS m
            JOIN law_documents AS d ON d.document_id = m.document_id
            WHERE d.law_year = ? AND d.law_number = ?
            LIMIT 1
            """,
            (law_year, law_number),
        ).fetchone()
        if metadata_row is None:
            return None, []
        relation_rows = conn.execute(
            """
            SELECT relation_type, relation_label, target_law_identifier_text, target_title, ordinal
            FROM law_metadata_relations
            WHERE law_metadata_id = ?
            ORDER BY ordinal
            """,
            (metadata_row["law_metadata_id"],),
        ).fetchall()
    return metadata_row, list(relation_rows)


def _get_source_artifacts(
    store: SqliteLawStore,
    *,
    law_year: int,
    law_number: int,
) -> list[sqlite3.Row]:
    with store._connect() as conn:  # noqa: SLF001 - test-only verification of persisted values
        rows = conn.execute(
            """
            SELECT a.artifact_kind, a.storage_backend, a.storage_path, a.content_text, a.content_blob, a.content_bytes
            FROM source_artifacts AS a
            JOIN law_versions AS v ON v.version_id = a.version_id
            JOIN law_documents AS d ON d.document_id = v.document_id
            WHERE d.law_year = ? AND d.law_number = ?
            ORDER BY a.artifact_kind
            """,
            (law_year, law_number),
        ).fetchall()
    return list(rows)


def test_laws_collector_baseline_sync_creates_documents_and_versions(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)

    summary = service.sync(baseline_snapshots())
    counts = store.get_counts()
    embedding_model, embedding_dimensions, embedding_vector = _get_embedding_metadata(
        store,
        law_year=2025,
        law_number=25,
    )

    assert summary.processed == 2
    assert summary.new_documents == 2
    assert summary.new_versions == 0
    assert summary.skipped == 0
    assert counts.documents == 2
    assert counts.versions == 2
    assert counts.metadata == 0
    assert counts.relations == 0
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
    assert embedding_model == "mock-embedding-32d"
    assert embedding_dimensions == 32
    assert len(embedding_vector) == 32


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
    assert counts.metadata == 0
    assert counts.relations == 0
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
    assert config.initial_import_from == date(1945, 1, 1)
    assert config.historical_import_from == date(1945, 1, 1)


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


def test_laws_collector_worker_options_default_to_single_live_probe(monkeypatch) -> None:
    monkeypatch.delenv("LAWS_WORKER_MAX_PROBES", raising=False)
    monkeypatch.delenv("LAWS_COLLECTOR_MAX_RUNNING_TIME", raising=False)

    options = WorkerOptions.from_env()

    assert options.max_probes == 1
    assert options.max_running_minutes == 60


def test_slovlex_import_planner_starts_from_1_1945_without_progress(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    planner = SlovLexImportPlanner(config=service.config)
    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=planner.initial_year,
    )

    plan = planner.build_plan(progress=progress, today=date(2026, 3, 30))

    assert plan.initial_year == 1945
    assert plan.next_target == ImportTarget(year=1945, number=1)
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


def test_slovlex_sequential_import_runner_stops_mid_cycle_on_max_running_time(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    monotonic_values = iter([0.0, 1.0, 2.0, 3.0, 4.0, 40.0, 41.0, 42.0])
    runner = SlovLexSequentialImportRunner(
        config=service.config,
        store=store,
        monotonic_time_provider=lambda: next(monotonic_values),
    )

    def fake_probe(*, target: ImportTarget, timeout_seconds: float) -> object:
        return type(
            "Probe",
            (),
            {
                "target": target,
                "exists": True,
                "status_code": 200,
                "url": target.url,
            },
        )()

    runner._probe_target = fake_probe  # type: ignore[method-assign]

    summary = runner.run(max_probes=5, today=date(1993, 1, 2), max_running_seconds=30)

    assert summary.probes == 2
    assert summary.stopped_due_to_max_running_time is True


def test_slovlex_sequential_import_runner_logs_up_to_date_when_next_law_static_html_is_404(
    tmp_path: Path,
    capsys,
) -> None:
    store, service = _build_service(tmp_path)

    class FailingSnapshotLoader:
        def load_snapshot(self, *, target: ImportTarget, timeout_seconds: float = 12.0) -> LawSnapshot:
            assert target.law_id == "118/2026"
            raise RuntimeError("SlovLex fetch failed for static html: HTTP 404")

    runner = SlovLexSequentialImportRunner(
        config=service.config,
        store=store,
        service=service,
        snapshot_loader=FailingSnapshotLoader(),
    )

    def fake_probe(*, target: ImportTarget, timeout_seconds: float) -> object:
        return type(
            "Probe",
            (),
            {
                "target": target,
                "exists": True,
                "status_code": 200,
                "url": target.url,
            },
        )()

    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=2026,
    )
    progress = progress.evolve(
        last_processed_law_year=2026,
        last_processed_law_number=117,
        next_probe_law_year=2026,
        next_probe_law_number=118,
    )
    store.save_collector_progress(progress)
    runner._probe_target = fake_probe  # type: ignore[method-assign]

    summary = runner.run(max_probes=3, today=date(2026, 6, 10))
    output = capsys.readouterr().out
    reloaded = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=2026,
    )

    assert summary.probes == 1
    assert summary.laws_found == 0
    assert summary.failed_laws == 0
    assert summary.stopped_on_current_year_gap is True
    assert summary.next_law_to_check == "118/2026"
    assert reloaded.next_probe_law == "118/2026"
    assert reloaded.last_processed_law == "117/2026"
    assert "118/2026 does not exists, system imports all laws and is up to date" in output


def test_slovlex_sequential_import_runner_records_processing_failure_for_retry(
    tmp_path: Path,
    capsys,
) -> None:
    store, service = _build_service(tmp_path)

    class FailingSnapshotLoader:
        def load_snapshot(self, *, target: ImportTarget, timeout_seconds: float = 12.0) -> LawSnapshot:
            assert target.law_id == "118/2026"
            raise RuntimeError("SlovLex fetch failed: temporary connection reset")

    runner = SlovLexSequentialImportRunner(
        config=service.config,
        store=store,
        service=service,
        snapshot_loader=FailingSnapshotLoader(),
    )

    def fake_probe(*, target: ImportTarget, timeout_seconds: float) -> object:
        return type(
            "Probe",
            (),
            {
                "target": target,
                "exists": True,
                "status_code": 200,
                "url": target.url,
            },
        )()

    progress = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=2026,
    )
    progress = progress.evolve(
        last_processed_law_year=2026,
        last_processed_law_number=117,
        next_probe_law_year=2026,
        next_probe_law_number=118,
    )
    store.save_collector_progress(progress)
    runner._probe_target = fake_probe  # type: ignore[method-assign]

    summary = runner.run(max_probes=3, today=date(2026, 6, 10))
    output = capsys.readouterr().out
    reloaded = store.get_or_create_collector_progress(
        country_code="SK",
        source_system="slov-lex",
        initial_year=2026,
    )

    assert summary.probes == 1
    assert summary.laws_found == 0
    assert summary.failed_laws == 1
    assert summary.next_law_to_check == "118/2026"
    assert reloaded.next_probe_law == "118/2026"
    assert reloaded.last_processed_law == "117/2026"
    assert "law processing failed country=SK law=118/2026" in output
    assert "temporary connection reset" in output


def test_sqlite_store_initialize_backfills_embedding_metadata_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    store = SqliteLawStore(db_path=db_path)
    with store._connect() as conn:  # noqa: SLF001 - constructing a legacy schema fixture
        conn.executescript(
            """
            CREATE TABLE law_documents (
                document_id TEXT PRIMARY KEY,
                country_code TEXT NOT NULL,
                collection_code TEXT NOT NULL,
                law_year INTEGER NOT NULL,
                law_number INTEGER NOT NULL,
                official_name TEXT NOT NULL,
                lawyer_title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                publication_date TEXT NOT NULL,
                current_status TEXT NOT NULL,
                first_effective_date TEXT NOT NULL,
                applicable_to TEXT,
                superseded_by_url TEXT NOT NULL,
                parent_law_year INTEGER,
                parent_law_number INTEGER,
                first_stored_at TEXT NOT NULL,
                last_stored_at TEXT NOT NULL,
                last_checked_at TEXT NOT NULL,
                last_download_status TEXT NOT NULL,
                last_download_error TEXT NOT NULL,
                download_attempt_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE law_versions (
                version_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_token TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                version_checksum TEXT NOT NULL,
                status TEXT NOT NULL,
                html_checksum TEXT NOT NULL,
                pdf_checksum TEXT NOT NULL,
                html_bytes INTEGER NOT NULL,
                pdf_bytes INTEGER NOT NULL,
                normalized_json TEXT NOT NULL,
                embedding_vector TEXT NOT NULL,
                stored_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    store.initialize()

    with store._connect() as conn:  # noqa: SLF001 - test-only schema inspection
        columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute("PRAGMA table_info(law_versions)").fetchall()
        }

    assert columns["embedding_model"] == "TEXT"
    assert columns["embedding_dimensions"] == "INTEGER"


def test_sqlite_store_initialize_backfills_source_artifact_storage_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-source-artifacts.sqlite3"
    store = SqliteLawStore(db_path=db_path)
    with store._connect() as conn:  # noqa: SLF001 - constructing a legacy schema fixture
        conn.executescript(
            """
            CREATE TABLE source_artifacts (
                artifact_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                source_system TEXT NOT NULL,
                artifact_kind TEXT NOT NULL,
                source_url TEXT NOT NULL,
                checksum TEXT NOT NULL,
                content_text TEXT NOT NULL,
                content_blob BLOB,
                content_bytes INTEGER NOT NULL,
                http_etag TEXT NOT NULL,
                http_last_modified TEXT NOT NULL,
                should_redownload INTEGER NOT NULL,
                verification_status TEXT NOT NULL,
                download_error TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                last_checked_at TEXT NOT NULL
            );
            """
        )

    store.initialize()

    with store._connect() as conn:  # noqa: SLF001 - test-only schema inspection
        columns = {
            str(row["name"]): str(row["type"])
            for row in conn.execute("PRAGMA table_info(source_artifacts)").fetchall()
        }

    assert columns["storage_backend"] == "TEXT"
    assert columns["storage_path"] == "TEXT"


def test_laws_collector_logs_embedding_pipeline_steps(tmp_path: Path, capsys) -> None:
    _, service = _build_service(tmp_path)

    service.sync((baseline_snapshots()[0],))

    output = capsys.readouterr().out

    assert "start law country=SK law=25/2025" in output
    assert "database upload law=25/2025 document_status=created" in output
    assert "vector start law=25/2025" in output
    assert "vector done law=25/2025" in output
    assert "embedding_model=mock-embedding-32d" in output
    assert "embedding_dimensions=32" in output


def test_laws_collector_logs_embedding_runtime_on_startup(monkeypatch, caplog) -> None:
    class FakeStore:
        def initialize(self) -> None:
            return None

    class FakeService:
        def sync(self, snapshots: tuple[object, ...]) -> object:
            return type(
                "Summary",
                (),
                {
                    "processed": len(snapshots),
                    "new_documents": 0,
                    "new_versions": 0,
                    "metadata_updates": 0,
                    "skipped": 0,
                },
            )()

    class FakeDefinition:
        collector_name = "fake_collector"

        def create_service(self, *, config: object, store: object) -> FakeService:
            return FakeService()

        def baseline_snapshots(self) -> tuple[object, ...]:
            return (object(),)

        def delta_snapshots(self) -> tuple[object, ...]:
            return ()

    class FakeConfig:
        country_code = "SK"
        db_backend = "sqlite"

    fake_store = FakeStore()
    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL_OPTION", "local")
    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setenv("LAWS_WORKER_FIXTURE", "baseline")
    monkeypatch.setenv("LAWS_WORKER_MAX_CYCLES", "1")
    caplog.set_level(logging.INFO, logger="laws-collector")
    monkeypatch.setattr(laws_collector_worker.LawsCollectorConfig, "from_env", lambda: FakeConfig())
    monkeypatch.setattr(laws_collector_worker, "get_country_laws_collector_definition", lambda _code: FakeDefinition())
    monkeypatch.setattr(laws_collector_worker.SqliteLawStore, "from_config", lambda _config: fake_store)

    laws_collector_worker.run_worker()

    output = caplog.text

    assert "[laws-collector] startup" in output
    assert "embedding_option=local" in output
    assert "embedding_model=all-MiniLM-L6-v2" in output
    assert "embedding_device=" in output


def test_laws_collector_stops_when_live_zip_tail_is_up_to_date(monkeypatch, caplog) -> None:
    class FakeStore:
        def initialize(self) -> None:
            return None

    class FakeService:
        pass

    class FakeDefinition:
        collector_name = "fake_collector"

        def create_service(self, *, config: object, store: object) -> FakeService:
            return FakeService()

    class FakeConfig:
        country_code = "SK"
        db_backend = "sqlite"
        import_mode = "zip"
        import_zip_max_threads = 5

        def validate(self) -> None:
            return None

    class FakeZipRunner:
        def __init__(self, **_kwargs: object) -> None:
            return None

        def run(self, *, max_running_seconds: float = 0) -> object:
            return type(
                "ZipSummary",
                (),
                {
                    "phase": "monthly",
                    "import_key": "slov-lex:zip:monthly:test",
                    "entries_processed": 0,
                    "sync_summary": type(
                        "SyncSummary",
                        (),
                        {
                            "processed": 0,
                            "new_documents": 0,
                            "new_versions": 0,
                            "metadata_updates": 0,
                            "skipped": 0,
                        },
                    )(),
                    "archive_completed": True,
                    "monthly_completed": True,
                    "last_processed_law": "99/2026",
                    "stopped_due_to_max_running_time": False,
                },
            )()

    class FakeSequentialRunner:
        calls = 0

        def __init__(self, **_kwargs: object) -> None:
            return None

        def run(self, *, max_probes: int, max_running_seconds: float = 0) -> object:
            FakeSequentialRunner.calls += 1
            return type(
                "SequentialSummary",
                (),
                {
                    "probes": 1,
                    "laws_found": 0,
                    "failed_laws": 0,
                    "years_advanced": 0,
                    "stopped_on_current_year_gap": True,
                    "last_processed_law": "117/2026",
                    "next_law_to_check": "118/2026",
                    "stopped_due_to_max_running_time": False,
                },
            )()

    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL_OPTION", "cloud")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LAWS_WORKER_FIXTURE", "live")
    monkeypatch.setenv("LAWS_WORKER_MAX_CYCLES", "0")
    monkeypatch.setenv("LAWS_WORKER_MAX_PROBES", "1")
    monkeypatch.setenv("LAWS_WORKER_POLL_SECONDS", "1")
    caplog.set_level(logging.INFO, logger="laws-collector")
    monkeypatch.setattr(laws_collector_worker.LawsCollectorConfig, "from_env", lambda: FakeConfig())
    monkeypatch.setattr(laws_collector_worker, "get_country_laws_collector_definition", lambda _code: FakeDefinition())
    monkeypatch.setattr(laws_collector_worker.SqliteLawStore, "from_config", lambda _config: FakeStore())
    monkeypatch.setattr(laws_collector_worker, "SlovLexZipImportRunner", FakeZipRunner)
    monkeypatch.setattr(laws_collector_worker, "SlovLexSequentialImportRunner", FakeSequentialRunner)

    laws_collector_worker.run_worker()

    assert FakeSequentialRunner.calls == 1
    assert "worker stopped because laws collector is up to date" in caplog.text
    assert "last_processed_law=117/2026" in caplog.text
    assert "next_law_to_check=118/2026" in caplog.text


def test_laws_collector_splits_large_laws_into_multiple_embedding_chunks(tmp_path: Path) -> None:
    store, base_service = _build_service(tmp_path)
    captured_batches: list[tuple[str, ...]] = []

    class RecordingEmbeddingClient:
        @property
        def model_name(self) -> str:
            return "recording-embedding-3d"

        def embed_texts(self, texts: tuple[str, ...]) -> EmbeddingBatchResult:
            captured_batches.append(tuple(texts))
            return EmbeddingBatchResult(
                model_name=self.model_name,
                vectors=[[1.0, 2.0, 3.0] for _ in texts],
            )

    snapshot = replace(
        baseline_snapshots()[0],
        html_content=("Dlhy text o zakone. " * 1200).strip(),
    )
    service = SlovakLawsCollectorService(
        config=base_service.config,
        store=store,
        embedding_client=RecordingEmbeddingClient(),
    )

    service.sync((snapshot,))
    embedding_model, embedding_dimensions, embedding_vector = _get_embedding_metadata(
        store,
        law_year=snapshot.year,
        law_number=snapshot.number,
    )

    assert len(captured_batches) == 1
    assert len(captured_batches[0]) > 1
    assert embedding_model == "recording-embedding-3d"
    assert embedding_dimensions == 3
    assert embedding_vector == [1.0, 2.0, 3.0]


def test_laws_collector_persists_metadata_and_relations(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    snapshot = replace(
        baseline_snapshots()[0],
        metadata=LawMetadataRecord(
            law_identifier_text="25/2025 Z. z.",
            title="Stavebny zakon",
            law_type="Zakon",
            approval_date="2025-01-02",
            publication_date="2025-01-10",
            effective_from="2025-02-01",
            effective_to="2025-12-31",
            author="Narodna rada Slovenskej republiky",
            legal_areas=("Stat", "Stavebne pravo"),
            issue_reference="12/2025",
        ),
        relations=(
            LawRelationRecord(
                relation_type="amends",
                relation_label="Predpis meni",
                target_law_identifier_text="50/2001 Z. z.",
                target_title="Povodny zakon",
                target_url="https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2001/50",
                target_law_year=2001,
                target_law_number=50,
            ),
            LawRelationRecord(
                relation_type="implements",
                relation_label="Vykonavacie predpisy",
                target_law_identifier_text="12/2026 Z. z.",
                target_title="Vykonavaci predpis",
                target_url="https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2026/12",
                target_law_year=2026,
                target_law_number=12,
            ),
        ),
    )

    service.sync((snapshot,))
    counts = store.get_counts()
    metadata_row, relation_rows = _get_law_metadata(store, law_year=snapshot.year, law_number=snapshot.number)

    assert counts.metadata == 1
    assert counts.relations == 2
    assert metadata_row is not None
    assert metadata_row["law_identifier_text"] == "25/2025 Z. z."
    assert metadata_row["law_type"] == "Zakon"
    assert json.loads(str(metadata_row["legal_areas_json"])) == ["Stat", "Stavebne pravo"]
    assert [row["relation_type"] for row in relation_rows] == ["amends", "implements"]
    assert relation_rows[0]["target_law_identifier_text"] == "50/2001 Z. z."


def test_laws_collector_persists_source_artifact_references_for_live_style_snapshots(
    tmp_path: Path,
) -> None:
    store, service = _build_service(tmp_path)
    snapshot = replace(
        baseline_snapshots()[0],
        html_content="Uplne znenie zakona.",
        html_source_content=b"<html><body><p>Uplne znenie zakona.</p></body></html>",
        pdf_content=b"%PDF-1.4 test-law",
    )

    service.sync((snapshot,))
    artifacts = _get_source_artifacts(store, law_year=snapshot.year, law_number=snapshot.number)

    assert [row["artifact_kind"] for row in artifacts] == ["html", "pdf"]
    for row in artifacts:
        assert row["storage_backend"] == "local_file"
        assert Path(str(row["storage_path"])).exists()
        assert row["content_blob"] is None
    assert artifacts[0]["content_text"] == "Uplne znenie zakona."
    assert Path(str(artifacts[0]["storage_path"])).read_text(encoding="utf-8").startswith("<html>")


def test_laws_collector_resync_replaces_legacy_pdf_blob_with_storage_reference(
    tmp_path: Path,
) -> None:
    store, service = _build_service(tmp_path)
    snapshot = replace(
        baseline_snapshots()[0],
        html_content="Uplne znenie zakona.",
        html_source_content=b"<html><body><p>Uplne znenie zakona.</p></body></html>",
        pdf_content=b"%PDF-1.4 test-law",
    )

    service.sync((snapshot,))
    with store._connect() as conn:  # noqa: SLF001 - mutate to simulate pre-migration rows
        conn.execute(
            """
            UPDATE source_artifacts
            SET storage_backend = '',
                storage_path = '',
                content_blob = ?
            WHERE artifact_kind = 'pdf'
            """,
            (b"legacy-pdf-blob",),
        )

    service.sync((snapshot,))
    artifacts = _get_source_artifacts(store, law_year=snapshot.year, law_number=snapshot.number)
    pdf_artifact = next(row for row in artifacts if row["artifact_kind"] == "pdf")

    assert pdf_artifact["storage_backend"] == "local_file"
    assert Path(str(pdf_artifact["storage_path"])).exists()
    assert pdf_artifact["content_blob"] is None


def test_slovlex_live_snapshot_loader_parses_metadata_and_relations(monkeypatch) -> None:
    html = """
    <h1>Zakon o testovani</h1>
    <table id="InfoTable">
      <tr><td class="title">Číslo predpisu:</td><td class="value_bold">461/2003 Z. z.</td></tr>
      <tr><td class="title">Názov:</td><td class="value">Zákon o sociálnom poistení</td></tr>
      <tr><td class="title">Typ:</td><td class="value_bold">Zákon</td></tr>
      <tr><td class="title">Dátum schválenia:</td><td class="value">30.10.2003</td></tr>
      <tr><td class="title">Dátum vyhlásenia:</td><td class="value_bold">27.11.2003</td></tr>
      <tr><td class="title">Dátum účinnosti od:</td><td class="value">01.09.2023</td></tr>
      <tr><td class="title">Dátum účinnosti do:</td><td class="value">30.09.2023</td></tr>
      <tr><td class="title">Autor:</td><td class="value">Národná rada Slovenskej republiky</td></tr>
      <tr><td class="title_po">Právna oblasť:</td><td class="value"><ul><li>Štát</li><li>Trestné právo hmotné</li></ul></td></tr>
      <tr><td class="title">Nachádza sa v čiastke: </td><td class="value"><p><a href="/static/pdf/SK/ZZ/2003/2003c200.pdf">200/2003</a></p></td></tr>
    </table>
    <div class="accordion_section_relations">
      <button class="accordion_relations" aria-expanded="false">Vykonávacie predpisy</button>
      <div class="panel_relations">
        <h4></h4><table class="InfoTable"><tbody>
          <tr>
            <td class="infoTable-nadpis"><a href="/ezbierky-fe/pravne-predpisy/SK/ZZ/2004/157/">157/2004&nbsp;Z.&nbsp;z. </a></td>
            <td>Opatrenie vykonávacie</td>
          </tr>
        </tbody></table>
      </div>
    </div>
    <div class="accordion_section_relations">
      <button class="accordion_relations" aria-expanded="false">Predpis mení</button>
      <div class="panel_relations">
        <h4></h4><table class="InfoTable"><tbody>
          <tr>
            <td class="infoTable-nadpis"><a href="/ezbierky-fe/pravne-predpisy/SK/ZZ/1993/120/">120/1993&nbsp;Z.&nbsp;z. </a></td>
            <td>Zákon Národnej rady Slovenskej republiky</td>
          </tr>
        </tbody></table>
      </div>
    </div>
    <div class="accordion_section_relations">
      <button class="accordion_relations" aria-expanded="false">Predpis je menený</button>
      <div class="panel_relations">
        <h4></h4><table class="InfoTable"><tbody>
          <tr>
            <td class="infoTable-nadpis"><a href="/ezbierky-fe/pravne-predpisy/SK/ZZ/2026/44/">44/2026&nbsp;Z.&nbsp;z. </a></td>
            <td>Zákon, ktorým sa mení a dopĺňa Trestný zákon</td>
          </tr>
        </tbody></table>
      </div>
    </div>
    <div class="accordion_section_relations">
      <button class="accordion_relations" aria-expanded="false">Predpis ruší</button>
      <div class="panel_relations">
        <h4></h4><table class="InfoTable"><tbody>
          <tr>
            <td class="infoTable-nadpis"><a href="/ezbierky-fe/pravne-predpisy/SK/ZZ/1956/54/">54/1956&nbsp;Zb. </a></td>
            <td>Zákon o nemocenskom poistení zamestnancov</td>
          </tr>
        </tbody></table>
      </div>
    </div>
    <tr class="effectivenessHistoryItem" data-iri="/static/SK/ZZ/2003/461/20230901" data-vyhlasene="0" data-ucinnostod="2023-09-01" data-ucinnostdo="2023-09-30"></tr>
    <div class="text" id="par1">Prva cast zakona</div>
    <a href="/static/pdf/SK/ZZ/2003/461/ZZ_2003_461.pdf">PDF</a>
    """
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    )

    def fake_fetch_resource(*, url: str, timeout_seconds: float) -> FetchedResource:
        if url.endswith(".html"):
            return FetchedResource(url=url, body=html.encode("utf-8"), etag="etag-1", last_modified="Mon")
        return FetchedResource(url=url, body=pdf_bytes, etag="etag-pdf", last_modified="Tue")

    monkeypatch.setattr(slovlex_live_source, "_fetch_resource", fake_fetch_resource)
    monkeypatch.setattr(slovlex_live_source, "_extract_pdf_text", lambda _payload: "Prva cast zakona")
    loader = SlovLexLiveSnapshotLoader()

    snapshot = loader.load_snapshot(
        target=ImportTarget(year=2003, number=461),
        timeout_seconds=1.0,
    )

    assert snapshot.metadata is not None
    assert snapshot.metadata.law_identifier_text == "461/2003 Z. z."
    assert snapshot.metadata.law_type == "Zákon"
    assert snapshot.metadata.approval_date == "2003-10-30"
    assert snapshot.metadata.legal_areas == ("Štát", "Trestné právo hmotné")
    assert snapshot.metadata.issue_reference == "200/2003"
    assert [relation.relation_type for relation in snapshot.relations] == [
        "implements",
        "amends",
        "amended_by",
        "repeals",
    ]
    assert snapshot.relations[2].target_law_identifier_text == "44/2026 Z. z."
    assert snapshot.relations[2].target_law_year == 2026
    assert snapshot.relations[3].target_law_number == 54


def test_slovlex_sequential_import_runner_logs_when_no_new_laws(tmp_path: Path, capsys) -> None:
    store, service = _build_service(tmp_path)
    runner = SlovLexSequentialImportRunner(config=service.config, store=store, service=service)

    def fake_probe(*, target: ImportTarget, timeout_seconds: float) -> object:
        return type(
            "Probe",
            (),
            {
                "target": target,
                "exists": False,
                "status_code": 404,
                "url": target.url,
            },
        )()

    runner._probe_target = fake_probe  # type: ignore[method-assign]
    runner.run(max_probes=1, today=date(1993, 1, 2))

    output = capsys.readouterr().out

    assert "No new laws for SK, last processed law none at n/a" in output


def test_slovlex_sequential_import_runner_ingests_before_advancing_progress(tmp_path: Path) -> None:
    store, service = _build_service(tmp_path)
    captured: list[LawSnapshot] = []
    runner = SlovLexSequentialImportRunner(config=service.config, store=store, service=service)
    snapshot = replace(
        baseline_snapshots()[0],
        year=1945,
        number=1,
        publication_date="1945-01-01",
        effective_from="1945-01-01",
        version_token="19450101",
        source_url="https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1945/1/",
        html_url="https://static.slov-lex.sk/static/SK/ZZ/1945/1/vyhlasene_znenie.html",
        pdf_url="https://static.slov-lex.sk/pdf/SK/ZZ/1945/1/19450101.pdf",
    )

    def fake_probe(*, target: ImportTarget, timeout_seconds: float) -> object:
        return type(
            "Probe",
            (),
            {
                "target": target,
                "exists": True,
                "status_code": 200,
                "url": target.url,
            },
        )()

    class RecordingLoader:
        def load_snapshot(self, *, target: ImportTarget, timeout_seconds: float = 12.0) -> LawSnapshot:
            captured.append(snapshot)
            return snapshot

    runner._probe_target = fake_probe  # type: ignore[method-assign]
    runner.snapshot_loader = RecordingLoader()

    summary = runner.run(max_probes=1, today=date(1945, 1, 2))
    embedding_model, embedding_dimensions, embedding_vector = _get_embedding_metadata(
        store,
        law_year=snapshot.year,
        law_number=snapshot.number,
    )

    assert len(captured) == 1
    assert summary.laws_found == 1
    assert summary.last_processed_law == "1/1945"
    assert summary.next_law_to_check == "2/1945"
    assert embedding_model == "mock-embedding-32d"
    assert embedding_dimensions == 32
    assert len(embedding_vector) == 32


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
        initial_import_from=date(1945, 1, 1),
        historical_import_from=date(1945, 1, 1),
    )

    assert config.country_db_name == "laws_cz"
    assert config.db_path.name == "cz_laws.sqlite3"


def test_laws_collector_local_embedding_mode_supports_semantic_search(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class LocalSemanticBackend:
        def encode_texts(self, texts: tuple[str, ...] | list[str]) -> list[list[float]]:
            return [self._vector_for(text) for text in texts]

        def _vector_for(self, text: str) -> list[float]:
            normalized = _normalize_text(text)
            if "stavebn" in normalized or "permit" in normalized or "construction" in normalized:
                return [1.0, 0.0, 0.0]
            if "social" in normalized or "poisten" in normalized:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL_OPTION", "local")
    monkeypatch.setenv("SYSTEM_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setattr(embedding_module, "_default_local_embedding_root", lambda: tmp_path / "aimodels")
    monkeypatch.setattr(embedding_module, "_load_local_embedding_backend", lambda _config: LocalSemanticBackend())

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
    )
    store = SqliteLawStore.from_config(config)
    store.initialize()
    service = SlovakLawsCollectorService(config=config, store=store)

    service.sync(baseline_snapshots())
    results = service.search_semantic("construction permit requirements", limit=2)
    embedding_model, embedding_dimensions, embedding_vector = _get_embedding_metadata(
        store,
        law_year=2025,
        law_number=25,
    )

    assert results
    assert results[0].law_year == 2025
    assert results[0].law_number == 25
    assert results[0].official_name == "Stavebny zakon"
    assert results[0].score > 0.99
    assert embedding_model == "all-MiniLM-L6-v2"
    assert embedding_dimensions == 3
    assert embedding_vector == [1.0, 0.0, 0.0]
