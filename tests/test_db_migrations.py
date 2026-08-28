from pathlib import Path

from aijurisdictionagents.db_migrations import runner


class _FakeConnection:
    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakePsycopg:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def connect(self, connection_uri: str) -> _FakeConnection:
        assert connection_uri.startswith("postgresql://")
        return self._connection


def test_postgres_migration_dry_run_is_read_only(
    monkeypatch, tmp_path: Path
) -> None:
    migration = tmp_path / "0001_test.sql"
    migration.write_text("CREATE TABLE example(id INT);", encoding="utf-8")

    conn = _FakeConnection()
    monkeypatch.setattr(runner, "psycopg", _FakePsycopg(conn))

    calls: list[str] = []

    def fail_if_called(*args, **kwargs) -> None:
        raise AssertionError("dry-run must not mutate migration state")

    monkeypatch.setattr(runner, "_ensure_migration_table_postgres", fail_if_called)
    monkeypatch.setattr(runner, "_acquire_postgres_advisory_lock", fail_if_called)
    monkeypatch.setattr(runner, "_release_postgres_advisory_lock", fail_if_called)
    monkeypatch.setattr(runner, "_execute_postgres_migration", fail_if_called)
    monkeypatch.setattr(
        runner,
        "_fetch_applied_postgres",
        lambda actual_conn, project: calls.append(f"fetch:{project}") or {},
    )

    pending = runner._apply_postgres_migrations(
        project="api",
        connection_uri="postgresql://postgres:postgres@localhost:5432/aijurisdiction",
        migrations=[migration],
        dry_run=True,
    )

    assert pending == ["0001_test.sql"]
    assert calls == ["fetch:api"]


def test_postgres_migration_apply_uses_lock_and_records_execution(
    monkeypatch, tmp_path: Path
) -> None:
    migration = tmp_path / "0001_test.sql"
    migration.write_text("CREATE TABLE example(id INT);", encoding="utf-8")

    conn = _FakeConnection()
    monkeypatch.setattr(runner, "psycopg", _FakePsycopg(conn))

    events: list[str] = []

    monkeypatch.setattr(
        runner,
        "_acquire_postgres_advisory_lock",
        lambda actual_conn, project: events.append(f"lock:{project}"),
    )
    monkeypatch.setattr(
        runner,
        "_ensure_migration_table_postgres",
        lambda actual_conn: events.append("ensure"),
    )
    monkeypatch.setattr(
        runner,
        "_fetch_applied_postgres",
        lambda actual_conn, project: events.append(f"fetch:{project}") or {},
    )
    monkeypatch.setattr(
        runner,
        "_execute_postgres_migration",
        lambda **kwargs: events.append(f"execute:{kwargs['path'].name}"),
    )
    monkeypatch.setattr(
        runner,
        "_release_postgres_advisory_lock",
        lambda actual_conn, project: events.append(f"unlock:{project}"),
    )

    pending = runner._apply_postgres_migrations(
        project="api",
        connection_uri="postgresql://postgres:postgres@localhost:5432/aijurisdiction",
        migrations=[migration],
        dry_run=False,
    )

    assert pending == ["0001_test.sql"]
    assert events == [
        "lock:api",
        "ensure",
        "fetch:api",
        "execute:0001_test.sql",
        "unlock:api",
    ]


def test_court_decision_metadata_search_index_uses_immutable_expression() -> None:
    migration = Path(
        "databases/court-decision-collector/migrations/0001_search_indexes.sql"
    ).read_text(encoding="utf-8")
    init_schema = Path(
        "databases/court-decision-collector/initdb/001_schema.sql"
    ).read_text(encoding="utf-8")

    for sql in (migration, init_schema):
        metadata_index = sql.split(
            "idx_court_decision_documents_metadata_search_text", maxsplit=1
        )[1].split(");", maxsplit=1)[0]
        assert "concat_ws" not in metadata_index
        assert "'simple'::regconfig" in metadata_index
        assert "COALESCE(court_name, '')" in metadata_index


def test_api_document_template_case_catalog_migration_is_versioned() -> None:
    migrations = runner.list_migration_files("api")
    migration = next(
        path for path in migrations if path.name == "0019_document_templates_case_catalog.sql"
    )
    sql = migration.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS lineage_key" in sql
    assert "ADD COLUMN IF NOT EXISTS version" in sql
    assert "ADD COLUMN IF NOT EXISTS stored_at" in sql
    assert "DROP CONSTRAINT document_templates_jurisdiction_template_key_key" in sql
    assert "UNIQUE (jurisdiction, template_key, version)" in sql
    assert "CREATE TABLE IF NOT EXISTS case_types" in sql
    assert "CREATE TABLE IF NOT EXISTS case_type_templates" in sql
    assert "CREATE TABLE IF NOT EXISTS case_prompts" in sql


def test_api_document_template_fact_schema_migration_is_additive() -> None:
    migrations = runner.list_migration_files("api")
    migration = next(
        path for path in migrations if path.name == "0021_document_template_fact_schema.sql"
    )
    sql = migration.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS fact_schema_json" in sql
    assert "DEFAULT '[]'" in sql
