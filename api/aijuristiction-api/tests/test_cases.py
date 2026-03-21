from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

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
