from pathlib import Path
import sqlite3

from aijurisdictionagents.api_db import ApiDataConfig, ApiDatabaseStore


def test_api_database_layer_end_to_end(tmp_path: Path) -> None:
    store = ApiDatabaseStore(db_path=tmp_path / "api.sqlite3", blob_root=tmp_path / "blob")
    store.initialize()

    user = store.create_user(
        phone_number="+421900111222",
        email="founder@example.com",
        password="secret-pass",
        first_name="Founder",
        last_name="User",
    )
    authenticated = store.authenticate_user(email="founder@example.com", password="secret-pass")
    assert authenticated is not None
    assert authenticated.user_id == user.user_id
    assert authenticated.phone_number == "+421900111222"

    phone_authenticated = store.find_user_by_phone(phone_number="+421900111222")
    assert phone_authenticated is not None
    assert phone_authenticated.user_id == user.user_id

    company = store.create_company(legal_name="Acme Legal s.r.o.")
    store.add_user_to_company(user_id=user.user_id, company_id=company.company_id, role="owner")

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
    monkeypatch.setenv("DB_LOCAL", "./databases/api.sqlite3")

    store = ApiDatabaseStore.from_env()

    assert store.db_path.name == "api.sqlite3"
    assert store.db_path.parent.name == "databases"
    assert store.db_path.parent.parent == Path(__file__).resolve().parents[1]


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
        raise AssertionError("Expected ValueError when cloud options are set without secrets")


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
