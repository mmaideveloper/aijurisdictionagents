from __future__ import annotations

from io import BytesIO
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore


def _headers() -> dict[str, str]:
    return {"x-api-key": "aijuris"}


def _create_user(client: TestClient, idx: int = 1) -> str:
    response = client.post(
        "/v1/users/sign-up",
        headers=_headers(),
        json={
            "phone_number": f"+42190000000{idx}",
            "email": f"case-user-{idx}@example.com",
            "password": "secret",
        },
    )
    assert response.status_code == 201
    return response.json()["user_id"]


def test_case_lifecycle_and_limit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client)

    created_ids: list[str] = []
    for index in range(5):
        response = client.post(
            "/v1/cases",
            headers=_headers(),
            json={"user_id": user_id, "title": f"Case {index}"},
        )
        assert response.status_code == 201
        created_ids.append(response.json()["case_id"])

    sixth = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Case 6"},
    )
    assert sixth.status_code == 409

    rename = client.patch(
        f"/v1/cases/{created_ids[0]}",
        headers=_headers(),
        json={"user_id": user_id, "title": "Renamed"},
    )
    assert rename.status_code == 200
    assert rename.json()["title"] == "Renamed"

    delete = client.delete(
        f"/v1/cases/{created_ids[1]}?user_id={user_id}",
        headers=_headers(),
    )
    assert delete.status_code == 204

    listing = client.get(f"/v1/cases?user_id={user_id}", headers=_headers())
    assert listing.status_code == 200
    assert len(listing.json()) == 4


def test_case_history_paging_and_document_download(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client, idx=2)
    created = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "History case"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    store = ApiDatabaseStore.from_env()
    store.initialize()
    for index in range(7):
        role = "user" if index % 2 == 0 else "assistant"
        store.add_case_message(
            case_id=case_id,
            role=role,
            content=f"Message {index}",
            agent_name="LawyerSlovakia" if role == "assistant" else "User",
        )
        time.sleep(0.002)
    doc_id = store.add_case_text_document(
        case_id=case_id,
        original_filename="evidence.txt",
        content="Case evidence payload",
        uploaded_by_user_id=user_id,
    )

    first_page = client.get(
        f"/v1/cases/{case_id}/history?user_id={user_id}&offset=0&limit=5",
        headers=_headers(),
    )
    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["has_more"] is True
    assert len(payload["messages"]) == 5
    assert payload["messages"][0]["content"] == "Message 2"
    assert payload["messages"][-1]["content"] == "Message 6"
    assert payload["documents"][0]["doc_id"] == doc_id

    second_page = client.get(
        f"/v1/cases/{case_id}/history?user_id={user_id}&offset=5&limit=5",
        headers=_headers(),
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["has_more"] is False
    assert [item["content"] for item in second_payload["messages"]] == ["Message 0", "Message 1"]

    document = client.get(
        f"/v1/cases/{case_id}/documents/{doc_id}?user_id={user_id}",
        headers=_headers(),
    )
    assert document.status_code == 200
    assert document.content == b"Case evidence payload"
    assert document.headers["content-disposition"].endswith('filename="evidence.txt"')

    generated_doc_id = store.add_case_text_document(
        case_id=case_id,
        original_filename="assistant-technical.json",
        content='{"case":{"status":"intake_open"}}',
        uploaded_by_user_id=user_id,
    )
    store.add_case_message(
        case_id=case_id,
        role="assistant",
        content=(
            "Dokument je pripraveny na stiahnutie.\n\n"
            f"Technicke udaje som ulozil do dokumentu pripadu: /v1/cases/{case_id}/documents/{generated_doc_id}?user_id={user_id}"
        ),
        agent_name="LawyerSlovakia",
    )

    generated_pdf = client.get(
        f"/v1/cases/{case_id}/documents/{generated_doc_id}/pdf?user_id={user_id}",
        headers=_headers(),
    )
    assert generated_pdf.status_code == 200
    assert generated_pdf.headers["content-type"].startswith("application/pdf")
    assert generated_pdf.content.startswith(b"%PDF")
    assert generated_pdf.headers["content-disposition"].endswith(
        'filename="assistant-technical.pdf"'
    )
    generated_pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(generated_pdf.content)).pages
    )
    assert "JurisDicta" in generated_pdf_text
    assert "Skore overenia dokumentu: -" in generated_pdf_text
    assert "právny návrh" in generated_pdf_text
    assert "Poprad, Slovakia, 05801" in generated_pdf_text


def test_generated_case_document_pdf_falls_back_to_latest_document_message(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client, idx=22)
    created = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Payment confirmation"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    store = ApiDatabaseStore.from_env()
    store.initialize()
    old_doc_id = store.add_case_text_document(
        case_id=case_id,
        original_filename="assistant-technical-old.json",
        content='{"case":{"status":"intake_open"}}',
        uploaded_by_user_id=user_id,
    )
    store.add_case_message(
        case_id=case_id,
        role="assistant",
        content=(
            "LawyerSlovakia: Tu je konečná verzia dokumentu:\n\n"
            "---\n\n"
            "**Potvrdenie o zaplatení**\n\n"
            "Ja, Marek Novak, bytom Poprad, týmto potvrdzujem, že som dňa "
            "1. júna 2026 zaplatil sumu 5000 eur Jano Mrkvička.\n\n"
            "Dátum: 1. júna 2026\n\n"
            "Podpis: ________________________\n\n"
            "---\n\n"
            "Dokument je pripravený na stiahnutie vo formáte PDF."
        ),
        agent_name="LawyerSlovakia",
    )

    generated_pdf = client.get(
        f"/v1/cases/{case_id}/documents/{old_doc_id}/pdf?user_id={user_id}",
        headers=_headers(),
    )
    assert generated_pdf.status_code == 200
    generated_pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(generated_pdf.content)).pages
    )
    assert "Potvrdenie o zaplatení" in generated_pdf_text
    assert "Marek Novak" in generated_pdf_text
    assert "5000 eur" in generated_pdf_text
    assert "Dokument je pripravený na stiahnutie" not in generated_pdf_text


def test_case_history_falls_back_to_summary_when_transcript_missing() -> None:
    import app.cases_api as cases_api

    client = TestClient(app)

    class _FakeStore:
        def get_case(self, *, case_id: str):
            return SimpleNamespace(case_id=case_id, user_id="user-1", status="active")

        def list_case_communications(self, *, case_id: str, limit=None, offset: int = 0):
            return [
                SimpleNamespace(
                    communication_id="comm-1",
                    case_id=case_id,
                    channel="chat",
                    transcript_uri="missing://transcript",
                    summary="ASSISTANT: Summary fallback content (agent=LawyerSlovakia)",
                    created_at="2026-03-21T10:00:00Z",
                ),
            ]

        def list_case_documents(self, *, case_id: str):
            return []

        def read_storage_text(self, *, storage_uri: str) -> str:
            raise FileNotFoundError(storage_uri)

    app.dependency_overrides[cases_api.get_store] = lambda: _FakeStore()
    try:
        response = client.get(
            "/v1/cases/case-1/history?user_id=user-1&offset=0&limit=5",
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.pop(cases_api.get_store, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"][0]["content"] == "Summary fallback content"
    assert payload["messages"][0]["agent_name"] == "LawyerSlovakia"


def test_download_case_document_returns_404_when_payload_missing() -> None:
    import app.cases_api as cases_api

    client = TestClient(app)

    class _FakeStore:
        def get_case(self, *, case_id: str):
            return SimpleNamespace(case_id=case_id, user_id="user-1", status="active")

        def get_case_document(self, *, case_id: str, doc_id: str):
            return SimpleNamespace(
                doc_id=doc_id,
                case_id=case_id,
                storage_uri=f"{case_id}/source/v1_missing.txt",
                original_filename="missing.txt",
            )

        def read_storage_bytes(self, *, storage_uri: str) -> bytes:
            raise FileNotFoundError(storage_uri)

    app.dependency_overrides[cases_api.get_store] = lambda: _FakeStore()
    try:
        response = client.get(
            "/v1/cases/case-1/documents/doc-1?user_id=user-1",
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.pop(cases_api.get_store, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Stored payload is unavailable for document doc-1"


def test_session_history_document_reuses_same_doc_id_and_refreshes_payload(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    store = ApiDatabaseStore.from_env()
    store.initialize()
    user = store.create_user(
        email="history-refresh@example.com",
        password="secret",
        phone_number="+421900000099",
    )
    case = store.create_case(user_id=user.user_id, company_id=None, title="History refresh case")

    first_doc_id = store.add_case_session_history_document(
        case_id=case.case_id,
        session_id="session-1",
        content="USER: first turn",
        uploaded_by_user_id=user.user_id,
    )
    second_doc_id = store.add_case_session_history_document(
        case_id=case.case_id,
        session_id="session-1",
        content="USER: first turn\nASSISTANT: refreshed turn",
        uploaded_by_user_id=user.user_id,
    )

    assert second_doc_id == first_doc_id
    stored_document = store.get_case_document(case_id=case.case_id, doc_id=first_doc_id)
    assert stored_document.processing_status == "uploaded"
    assert store.read_storage_text(storage_uri=stored_document.storage_uri) == (
        "USER: first turn\nASSISTANT: refreshed turn"
    )
