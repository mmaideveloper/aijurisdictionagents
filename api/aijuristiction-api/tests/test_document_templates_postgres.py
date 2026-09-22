from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from app.document_templates.store import DocumentTemplateStore, DocumentTemplateStoreConfig
from app.document_templates.models import DocumentTemplateCreateRequest, DocumentTemplateUpdateRequest


DATABASE_URL = os.getenv("DB_CLOUD", "").strip()
DATABASE_HOST = urlparse(DATABASE_URL).hostname if DATABASE_URL else None

pytestmark = pytest.mark.skipif(
    DATABASE_HOST not in {"127.0.0.1", "localhost", "::1"},
    reason="Document-template PostgreSQL integration requires a loopback DB_CLOUD.",
)


@pytest.fixture
def postgres_template_config(tmp_path: Path) -> Iterator[DocumentTemplateStoreConfig]:
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
        yield config
    finally:
        if not schema_name.startswith("test_document_templates_"):
            raise RuntimeError("Refusing to drop an unexpected PostgreSQL schema")
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )


def test_clean_postgres_case_type_seed_and_reopen(postgres_template_config: DocumentTemplateStoreConfig) -> None:
    import psycopg

    DocumentTemplateStore(postgres_template_config)
    with psycopg.connect(postgres_template_config.db_cloud) as connection:
        initial_keys = [str(row[0]) for row in connection.execute(
            "SELECT case_type_key FROM case_types ORDER BY case_type_key"
        ).fetchall()]

    DocumentTemplateStore(postgres_template_config)
    with psycopg.connect(postgres_template_config.db_cloud) as connection:
        reopened_keys = [str(row[0]) for row in connection.execute(
            "SELECT case_type_key FROM case_types ORDER BY case_type_key"
        ).fetchall()]

    assert initial_keys
    assert len(initial_keys) == len(set(initial_keys))
    assert reopened_keys == initial_keys


@pytest.mark.parametrize("required", [False, True])
def test_postgres_template_review_flag_roundtrip(
    postgres_template_config: DocumentTemplateStoreConfig, required: bool,
) -> None:
    import psycopg

    store = DocumentTemplateStore(postgres_template_config)
    created = store.create(DocumentTemplateCreateRequest(
        template_key="synthetic.review_flag", jurisdiction="SK", category="synthetic",
        title="Synthetic review flag", template_kind="contract", source_format="TXT",
        source_url="https://example.invalid/synthetic", human_review_required=required,
    ))
    assert created.human_review_required is required
    updated = store.update(
        template_key=created.template_key, jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(human_review_required=not required),
    )
    assert updated.human_review_required is (not required)
    retained = store.update(
        template_key=created.template_key, jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(description="Synthetic metadata update"),
    )
    assert retained.human_review_required is (not required)
    with psycopg.connect(postgres_template_config.db_cloud) as connection:
        rows = connection.execute(
            "SELECT human_review_required, pg_typeof(human_review_required)::text "
            "FROM document_templates WHERE template_key = %s ORDER BY version",
            (created.template_key,),
        ).fetchall()
    assert rows == [(int(required), "integer"), (int(not required), "integer"), (int(not required), "integer")]


def test_postgres_legacy_review_refresh_is_versioned_and_idempotent(
    postgres_template_config: DocumentTemplateStoreConfig,
) -> None:
    import psycopg

    store = DocumentTemplateStore(postgres_template_config)
    key = "sk.company.share_transfer"
    previous = store.get(template_key=key, jurisdiction="SK")
    # Reproduce the persisted release metadata from before Priority 3 controls.
    with psycopg.connect(postgres_template_config.db_cloud) as connection:
        connection.execute(
            "UPDATE document_templates SET human_review_required = 0, submission_mode = 'draft' "
            "WHERE template_id = %s", (previous.template_id,),
        )
    refreshed = DocumentTemplateStore(postgres_template_config).get(template_key=key, jurisdiction="SK")
    assert refreshed.human_review_required is True
    assert refreshed.submission_mode == "human_review_draft"
    assert refreshed.version == previous.version + 1
    reopened_store = DocumentTemplateStore(postgres_template_config)
    assert reopened_store.get(template_key=key, jurisdiction="SK").version == refreshed.version
    protected = reopened_store.update(
        template_key=key, jurisdiction="SK",
        payload=DocumentTemplateUpdateRequest(human_review_required=False),
    )
    assert protected.human_review_required is True
    assert protected.submission_mode == "human_review_draft"
