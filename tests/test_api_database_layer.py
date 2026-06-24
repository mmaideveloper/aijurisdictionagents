from pathlib import Path
import sqlite3
from types import SimpleNamespace

from aijurisdictionagents.api_db import ApiDataConfig, ApiDatabaseStore


def test_api_database_layer_end_to_end(tmp_path: Path) -> None:
    store = ApiDatabaseStore(
        db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blob"
    )
    store.initialize()

    user = store.create_user(
        phone_number="+421900111222",
        email="founder@example.com",
        password="secret-pass",
        first_name="Founder",
        last_name="User",
    )
    authenticated = store.authenticate_user(
        email="founder@example.com", password="secret-pass"
    )
    assert authenticated is not None
    assert authenticated.user_id == user.user_id
    assert authenticated.phone_number == "+421900111222"

    phone_authenticated = store.find_user_by_phone(phone_number="+421900111222")
    assert phone_authenticated is not None
    assert phone_authenticated.user_id == user.user_id

    company = store.create_company(legal_name="Acme Legal s.r.o.")
    store.add_user_to_company(
        user_id=user.user_id, company_id=company.company_id, role="owner"
    )

    case = store.create_case(
        user_id=user.user_id,
        company_id=company.company_id,
        title="Supplier payment dispute",
    )

    doc_id = store.add_case_document(
        case_id=case.case_id,
        kind="source",
        version=1,
        original_filename="invoice.pdf",
        payload=b"file-content",
        uploaded_by_user_id=user.user_id,
    )
    assert doc_id

    communication_id = store.add_case_communication(
        case_id=case.case_id,
        channel="chat",
        summary="Client provided additional context",
        transcript_payload=b"chat transcript",
        extension="txt",
    )
    assert communication_id

    case_root = tmp_path / "blob" / case.case_id
    assert case_root.exists()
    assert (case_root / "source" / "v1_invoice.pdf").exists()


def test_api_database_config_from_env_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))

    config = ApiDataConfig.from_env()
    config.validate()

    store = ApiDatabaseStore.from_env()
    assert store.db_path == tmp_path / "api.sqlite3"
    assert store.blob_root == tmp_path / "blob"


def test_api_database_config_resolves_relative_db_from_repo_root(monkeypatch) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", "./runs/storage/api/sqlite/api.sqlite3")

    store = ApiDatabaseStore.from_env()

    assert store.db_path.name == "api.sqlite3"
    assert store.db_path.parent.name == "sqlite"
    assert store.db_path.parent.parent.name == "api"
    assert store.db_path.parent.parent.parent.name == "storage"
    assert store.db_path.parent.parent.parent.parent.name == "runs"
    assert store.db_path.parent.parent.parent.parent.parent == Path(__file__).resolve().parents[1]


def test_api_database_config_requires_cloud_values(monkeypatch) -> None:
    monkeypatch.setenv("DB_OPTION", "azure")
    monkeypatch.setenv("STORAGE_OPTION", "azure")
    monkeypatch.delenv("DB_CLOUD", raising=False)
    monkeypatch.delenv("STORE_CLOUD", raising=False)

    config = ApiDataConfig.from_env()

    try:
        config.validate()
    except ValueError as exc:
        assert "DB_CLOUD" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError when cloud options are set without secrets"
        )


def test_azure_storage_uri_keeps_case_folder_prefix(tmp_path: Path) -> None:
    store = ApiDatabaseStore(
        db_path=tmp_path / "api.sqlite3",
        blob_root=tmp_path / "blob",
        storage_option="azure",
        store_cloud="https://example.blob.core.windows.net/cases",
    )
    store.initialize()

    user = store.create_user(
        phone_number="+421900555444",
        email="azure@example.com",
        password="secret",
        first_name="Azure",
        last_name="User",
    )
    case = store.create_case(user_id=user.user_id, company_id=None, title="Cloud case")

    store.add_case_document(
        case_id=case.case_id,
        kind="generated",
        version=2,
        original_filename="memo.docx",
        payload=b"memo",
        uploaded_by_user_id=user.user_id,
    )

    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute("SELECT storage_uri FROM case_documents LIMIT 1").fetchone()

    assert row is not None
    uri = row[0]
    assert uri.startswith("https://example.blob.core.windows.net/cases/")
    assert f"/{case.case_id}/generated/" in uri
    assert (tmp_path / "blob" / case.case_id / "generated" / "v2_memo.docx").exists()


def test_api_database_config_accepts_postgres_and_postgress_alias(monkeypatch) -> None:
    monkeypatch.setenv("DB_OPTION", "postgress")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv(
        "DB_CLOUD", "postgresql://postgres:postgres@localhost:5432/aijurisdiction"
    )

    config = ApiDataConfig.from_env()
    config.validate()

    assert config.db_option == "postgres"
    assert config.db_connection_uri.startswith("postgresql://")


def test_permanent_memory_upsert_and_get(tmp_path: Path) -> None:
    store = ApiDatabaseStore(
        db_path=tmp_path / "api.sqlite3",
        blob_root=tmp_path / "blob",
    )
    store.initialize()

    store.upsert_permanent_memory(
        key="llm_model_setup",
        value={
            "llm_modelname": "gpt-4.1",
            "cutoff_date": "2023-01-01",
            "cutoff_source": "https://platform.openai.com/docs/models",
        },
        entry_type="llm_model_metadata",
        source_url="https://platform.openai.com/docs/models",
    )
    entry = store.get_permanent_memory("llm_model_setup")

    assert entry is not None
    assert entry.entry_type == "llm_model_metadata"
    assert entry.value["cutoff_date"] == "2023-01-01"


def test_postgres_initialize_skips_sqlite_permanent_memory_bootstrap(tmp_path: Path) -> None:
    store = ApiDatabaseStore(
        db_path=tmp_path / "unused.sqlite3",
        blob_root=tmp_path / "blob",
        db_option="azure",
        db_cloud="postgresql://example",
    )
    executed_queries: list[str] = []

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query: str, params=()):
            executed_queries.append(query)
            lowered = query.lower()
            if "information_schema.columns" in lowered:
                return SimpleNamespace(fetchall=lambda: [])
            return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)

    store._connect = lambda: _FakeConn()  # type: ignore[method-assign]
    store._seed_subscription_plans = lambda conn: None  # type: ignore[method-assign]

    store.initialize()

    combined = "\n".join(executed_queries)
    assert "create table if not exists permanent_memory" not in combined.lower()
    assert "autoincrement" not in combined.lower()


def test_postgres_store_init_does_not_create_local_dirs(tmp_path: Path) -> None:
    db_path = tmp_path / "diagnostics" / "unused.sqlite3"
    blob_root = tmp_path / "cache"
    assert not db_path.parent.exists()
    assert not blob_root.exists()

    ApiDatabaseStore(
        db_path=db_path,
        blob_root=blob_root,
        db_option="postgres",
        db_cloud="postgresql://example",
        storage_option="azure",
        store_cloud="UseDevelopmentStorage=true",
    )

    assert not db_path.parent.exists()
    assert not blob_root.exists()


def test_default_unlimited_access_email_gets_internal_unlimited_plan(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("JURISDIGTA_UNLIMITED_ACCESS_EMAILS", raising=False)
    db_path = tmp_path / "api.sqlite3"
    store = ApiDatabaseStore(
        db_path=db_path,
        blob_root=tmp_path / "blob",
    )
    store.initialize()
    user = store.create_user(
        phone_number="+421900370370",
        email="MMAIDEVELOPER@GMAIL.COM",
        password="secret",
    )

    plan = store.get_effective_subscription_plan(user_id=user.user_id)

    assert plan.plan_code == "unlimited"
    assert plan.max_cases > 1_000_000
    assert plan.max_documents_per_case > 1_000_000
    assert plan.case_ttl_days is None
    case = store.create_case(user_id=user.user_id, company_id=None, title="Unlimited access")
    assert store.get_case_write_block_reason(case_id=case.case_id, user_id=user.user_id) is None


def test_list_unprocessed_case_documents_includes_chat_attachments(tmp_path: Path) -> None:
    store = ApiDatabaseStore(
        db_path=tmp_path / "api.sqlite3",
        blob_root=tmp_path / "blob",
    )
    store.initialize()

    user = store.create_user(
        phone_number="+421900444333",
        email="attachments@example.com",
        password="secret",
        first_name="Attachment",
        last_name="User",
    )
    case = store.create_case(
        user_id=user.user_id,
        company_id=None,
        title="Attachment processing",
    )

    chat_attachment_id = store.add_case_text_document(
        case_id=case.case_id,
        original_filename="lease.txt",
        content="Lease clause from chat upload.",
        uploaded_by_user_id=user.user_id,
    )
    session_history_id = store.add_case_session_history_document(
        case_id=case.case_id,
        session_id="session-1",
        content="USER: first turn",
        uploaded_by_user_id=user.user_id,
    )

    unprocessed_ids = {
        document.doc_id for document in store.list_unprocessed_case_documents(limit=10)
    }

    assert chat_attachment_id in unprocessed_ids
    assert session_history_id in unprocessed_ids
