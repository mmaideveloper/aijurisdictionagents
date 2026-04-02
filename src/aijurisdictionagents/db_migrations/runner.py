from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

try:
    import psycopg
except ImportError:  # pragma: no cover - optional dependency for local sqlite-only usage
    psycopg = None

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATABASES_ROOT = _REPO_ROOT / "databases"
_MIGRATION_PROJECT_PATHS = {
    "api": _DATABASES_ROOT / "api" / "migrations",
    "email": _DATABASES_ROOT / "api" / "email",
    "laws": _DATABASES_ROOT / "laws-collector" / "migrations",
}


def list_migration_files(project: str) -> list[Path]:
    project_root = _MIGRATION_PROJECT_PATHS.get(
        project,
        _DATABASES_ROOT / project / "migrations",
    )
    if not project_root.exists():
        raise FileNotFoundError(f"Migration project '{project}' not found at {project_root}")
    return sorted(path for path in project_root.glob("*.sql") if path.is_file())


def apply_sql_migrations(
    *,
    project: str,
    db_option: str,
    target: str,
    dry_run: bool = False,
) -> list[str]:
    migrations = list_migration_files(project)
    if db_option == "local":
        raise ValueError(
            "SQL migration projects target postgres/azure backends. "
            "Local SQLite remains code-driven via ApiDatabaseStore.initialize()."
        )
    if db_option not in {"postgres", "azure"}:
        raise ValueError(f"Unsupported db option for migrations: {db_option}")
    return _apply_postgres_migrations(
        project=project,
        connection_uri=target,
        migrations=migrations,
        dry_run=dry_run,
    )


def _apply_postgres_migrations(
    *,
    project: str,
    connection_uri: str,
    migrations: list[Path],
    dry_run: bool,
) -> list[str]:
    if psycopg is None:  # pragma: no cover
        raise RuntimeError("psycopg is required for postgres/azure migrations")
    with psycopg.connect(connection_uri) as conn:
        if dry_run:
            return _apply_migrations_with_state(
                project=project,
                migrations=migrations,
                dry_run=True,
                fetch_state=lambda: _fetch_applied_postgres(conn, project),
                execute=lambda path, sql, checksum: None,
            )

        _acquire_postgres_advisory_lock(conn, project)
        try:
            _ensure_migration_table_postgres(conn)
            return _apply_migrations_with_state(
                project=project,
                migrations=migrations,
                dry_run=False,
                fetch_state=lambda: _fetch_applied_postgres(conn, project),
                execute=lambda path, sql, checksum: _execute_postgres_migration(
                    conn=conn,
                    project=project,
                    path=path,
                    sql=sql,
                    checksum=checksum,
                ),
            )
        finally:
            _release_postgres_advisory_lock(conn, project)


def _apply_migrations_with_state(
    *,
    project: str,
    migrations: list[Path],
    dry_run: bool,
    fetch_state: Callable[[], dict[str, str]],
    execute: Callable[[Path, str, str], None],
) -> list[str]:
    applied = fetch_state()
    pending: list[str] = []
    for path in migrations:
        sql = path.read_text(encoding="utf-8")
        checksum = _checksum(sql)
        key = path.name
        existing_checksum = applied.get(key)
        if existing_checksum is not None:
            if existing_checksum != checksum:
                raise RuntimeError(
                    f"Migration checksum mismatch for {project}/{path.name}. "
                    "The migration was already applied with different contents."
                )
            continue
        pending.append(path.name)
        if dry_run:
            continue
        execute(path, sql, checksum)
    return pending


def _ensure_migration_table_postgres(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            project TEXT NOT NULL,
            version TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(project, version)
        )
        """
    )
    conn.commit()


def _fetch_applied_postgres(conn: Any, project: str) -> dict[str, str]:
    if not _postgres_relation_exists(conn, "schema_migrations"):
        return {}
    rows = conn.execute(
        "SELECT version, checksum FROM schema_migrations WHERE project = %s",
        (project,),
    ).fetchall()
    return {str(version): str(checksum) for version, checksum in rows}


def _execute_postgres_migration(
    *,
    conn: Any,
    project: str,
    path: Path,
    sql: str,
    checksum: str,
) -> None:
    with conn.transaction():
        conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_migrations(project, version, checksum) VALUES (%s, %s, %s)",
            (project, path.name, checksum),
        )


def _postgres_relation_exists(conn: Any, relation_name: str) -> bool:
    result = conn.execute("SELECT to_regclass(%s)", (f"public.{relation_name}",)).fetchone()
    return bool(result and result[0])


def _acquire_postgres_advisory_lock(conn: Any, project: str) -> None:
    conn.execute("SELECT pg_advisory_lock(%s)", (_migration_lock_key(project),))


def _release_postgres_advisory_lock(conn: Any, project: str) -> None:
    conn.execute("SELECT pg_advisory_unlock(%s)", (_migration_lock_key(project),))


def _migration_lock_key(project: str) -> int:
    digest = hashlib.sha256(project.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
