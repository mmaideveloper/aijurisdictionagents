from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig


DATABASE_URL = os.getenv("DB_CLOUD", "").strip()
DATABASE_HOST = urlparse(DATABASE_URL).hostname if DATABASE_URL else None

pytestmark = pytest.mark.skipif(
    DATABASE_HOST not in {"127.0.0.1", "localhost", "::1"},
    reason="Document-template PostgreSQL integration requires a loopback DB_CLOUD.",
)


def test_clean_postgres_case_type_seed_and_reopen(tmp_path: Path) -> None:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    schema_name = f"test_document_templates_{uuid4().hex}"
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )
    schema_database_url = make_conninfo(
        DATABASE_URL,
        options=f"-c search_path={schema_name}",
    )
    config = DocumentTemplateStoreConfig(
        db_option="postgres",
        db_cloud=schema_database_url,
        sqlite_path=tmp_path / "unused.sqlite3",
    )

    try:
        DocumentTemplateStore(config)
        with psycopg.connect(schema_database_url) as connection:
            initial_keys = [
                str(row[0])
                for row in connection.execute(
                    "SELECT case_type_key FROM case_types ORDER BY case_type_key"
                ).fetchall()
            ]

        DocumentTemplateStore(config)
        with psycopg.connect(schema_database_url) as connection:
            reopened_keys = [
                str(row[0])
                for row in connection.execute(
                    "SELECT case_type_key FROM case_types ORDER BY case_type_key"
                ).fetchall()
            ]

        assert initial_keys
        assert len(initial_keys) == len(set(initial_keys))
        assert reopened_keys == initial_keys
    finally:
        if not schema_name.startswith("test_document_templates_"):
            raise RuntimeError("Refusing to drop an unexpected PostgreSQL schema")
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )
