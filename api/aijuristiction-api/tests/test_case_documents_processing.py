from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore
from services.document_processor.worker import run_document_processor


def _headers() -> dict[str, str]:
    return {"x-api-key": "aijuris"}


def _configure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))


def _create_user(client: TestClient, phone: str, email: str) -> str:
    response = client.post(
        "/v1/users/sign-up",
        headers=_headers(),
        json={"phone_number": phone, "email": email, "password": "secret"},
    )
    assert response.status_code == 201
    return response.json()["user_id"]


def test_case_document_upload_limit_and_processing_context(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCUMENT_PROCESSOR", "azure")
    client = TestClient(app)
    user_id = _create_user(client, "+421900222111", "docs@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Documents"},
    ).json()["case_id"]

    upload = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[
            ("files", ("one.txt", b"alpha evidence", "text/plain")),
            ("files", ("two.txt", b"beta evidence", "text/plain")),
        ],
    )
    assert upload.status_code == 201
    assert len(upload.json()["uploaded"]) == 2

    blocked = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[("files", ("three.txt", b"gamma evidence", "text/plain"))],
    )
    assert blocked.status_code == 409

    before = client.get(
        f"/v1/cases/{case_id}/documents/context?user_id={user_id}",
        headers=_headers(),
    )
    assert before.status_code == 200
    assert before.json()["processed_documents"] == []
    assert before.json()["unprocessed_documents"] == ["two.txt", "one.txt"]

    processed = run_document_processor(limit=10)
    assert len(processed) == 2

    after = client.get(
        f"/v1/cases/{case_id}/documents/context?user_id={user_id}",
        headers=_headers(),
    )
    assert after.status_code == 200
    assert sorted(after.json()["processed_documents"]) == ["one.txt", "two.txt"]
    assert after.json()["unprocessed_documents"] == []

    history = client.get(f"/v1/cases/{case_id}/history?user_id={user_id}", headers=_headers())
    assert history.status_code == 200
    assert {item["processing_status"] for item in history.json()["documents"]} == {"processed"}


def test_case_document_upload_processes_immediately_in_local_mode(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("DOCUMENT_PROCESSOR", "local")
    client = TestClient(app)
    user_id = _create_user(client, "+421900222112", "docs-local@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Immediate processing"},
    ).json()["case_id"]

    upload = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[("files", ("one.txt", b"alpha evidence", "text/plain"))],
    )
    assert upload.status_code == 201
    uploaded = upload.json()["uploaded"]
    assert len(uploaded) == 1
    assert uploaded[0]["processing_status"] == "processed"
    assert upload.json()["processed_document_count"] == 1
    assert upload.json()["unprocessed_document_count"] == 0

    context = client.get(
        f"/v1/cases/{case_id}/documents/context?user_id={user_id}",
        headers=_headers(),
    )
    assert context.status_code == 200
    assert context.json()["processed_documents"] == ["one.txt"]
    assert context.json()["unprocessed_documents"] == []

    store = ApiDatabaseStore.from_env()
    store.initialize()
    contents = store.list_case_document_contents(case_id=case_id)
    assert len(contents) == 1
    doc_id, filename, text, vector = contents[0]
    assert doc_id
    assert filename == "one.txt"
    assert text == "alpha evidence"
    assert vector.startswith("[")


def test_whitelisted_phone_gets_extended_free_document_limit(monkeypatch, tmp_path) -> None:
    _configure(monkeypatch, tmp_path)
    client = TestClient(app)
    user_id = _create_user(client, "+421944400166", "test-phone@example.com")
    case_id = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Premium by phone"},
    ).json()["case_id"]

    files = [("files", (f"doc-{index}.txt", f"evidence-{index}".encode(), "text/plain")) for index in range(3)]
    response = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=files,
    )
    assert response.status_code == 201
    assert len(response.json()["uploaded"]) == 3

    store = ApiDatabaseStore.from_env()
    store.initialize()
    assert store.get_document_upload_limit(user_id=user_id) == 50
