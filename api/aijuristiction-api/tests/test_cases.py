from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import sqlite3
import time
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import app
from aijurisdictionagents.api_db import AIModelUsageAuditEntry, ApiDatabaseStore


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

    response = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Case 0"},
    )
    assert response.status_code == 201
    created_ids = [response.json()["case_id"]]

    second = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Case 2"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "Maximum number of cases reached (1)"

    rename = client.patch(
        f"/v1/cases/{created_ids[0]}",
        headers=_headers(),
        json={"user_id": user_id, "title": "Renamed"},
    )
    assert rename.status_code == 200
    assert rename.json()["title"] == "Renamed"

    delete = client.delete(
        f"/v1/cases/{created_ids[0]}?user_id={user_id}",
        headers=_headers(),
    )
    assert delete.status_code == 204

    listing = client.get(f"/v1/cases?user_id={user_id}", headers=_headers())
    assert listing.status_code == 200
    assert listing.json() == []


def test_unlimited_access_email_bypasses_case_limit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    monkeypatch.setenv("JURISDIGTA_UNLIMITED_ACCESS_EMAILS", "mmaideveloper@gmail.com")

    client = TestClient(app)
    response = client.post(
        "/v1/users/sign-up",
        headers=_headers(),
        json={
            "phone_number": "+421900000370",
            "email": "mmaideveloper@gmail.com",
            "password": "secret",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["user_id"]

    for index in range(3):
        created = client.post(
            "/v1/cases",
            headers=_headers(),
            json={"user_id": user_id, "title": f"Unlimited case {index}"},
        )
        assert created.status_code == 201

    listing = client.get(f"/v1/cases?user_id={user_id}", headers=_headers())
    assert listing.status_code == 200
    assert len(listing.json()) == 3


def test_free_case_becomes_readonly_after_one_day(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    db_path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("DB_LOCAL", str(db_path))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client, idx=21)
    created = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Readonly case"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    expired_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE cases SET created_at = ?, updated_at = ? WHERE case_id = ?",
            (expired_at, expired_at, case_id),
        )

    history = client.get(
        f"/v1/cases/{case_id}/history?user_id={user_id}",
        headers=_headers(),
    )
    assert history.status_code == 200

    rename = client.patch(
        f"/v1/cases/{case_id}",
        headers=_headers(),
        json={"user_id": user_id, "title": "Should fail"},
    )
    assert rename.status_code == 403
    rename_detail = rename.json()["detail"]
    assert rename_detail["code"] == "case_write_window_expired"
    assert "read-only" in rename_detail["message"]
    assert rename_detail["params"] == {"plan": "Free", "days": 1}

    upload = client.post(
        f"/v1/cases/{case_id}/documents?user_id={user_id}",
        headers=_headers(),
        files=[("files", ("evidence.txt", b"payload", "text/plain"))],
    )
    assert upload.status_code == 403
    assert upload.json()["detail"]["code"] == "case_write_window_expired"


def test_case_history_paging_and_document_download(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setenv("EMAIL_SCHEDULER_ENABLED", "false")

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

    inline_document = client.get(
        f"/v1/cases/{case_id}/documents/{doc_id}?user_id={user_id}&disposition=inline",
        headers=_headers(),
    )
    assert inline_document.status_code == 200
    assert inline_document.headers["content-disposition"].startswith("inline;")

    selected_email = client.post(
        f"/v1/cases/{case_id}/documents/send-email",
        headers=_headers(),
        json={
            "user_id": user_id,
            "recipient": "client@example.com",
            "case_subject": "History case",
            "doc_ids": [doc_id],
        },
    )
    assert selected_email.status_code == 200
    assert selected_email.json()["attachment_count"] == 1

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
        f'filename="history-case_{generated_doc_id}_dokument.pdf"'
    )
    generated_pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(generated_pdf.content)).pages
    )
    assert PdfReader(BytesIO(generated_pdf.content)).metadata.title == "Dokument"
    assert "JurisDigta" in generated_pdf_text
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
    assert generated_pdf.headers["content-disposition"].endswith(
        f'filename="payment-confirmation_{old_doc_id}_potvrdenie.pdf"'
    )
    generated_pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(generated_pdf.content)).pages
    )
    assert PdfReader(BytesIO(generated_pdf.content)).metadata.title == "Potvrdenie"
    assert "Potvrdenie\n" in generated_pdf_text
    assert "Potvrdenie o zaplatení" in generated_pdf_text
    assert "Marek Novak" in generated_pdf_text
    assert "5000 eur" in generated_pdf_text
    assert "Dokument je pripravený na stiahnutie" not in generated_pdf_text


def test_generated_case_document_pdf_reads_generated_document_storage(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client, idx=23)
    created = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Power of attorney"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    store = ApiDatabaseStore.from_env()
    store.initialize()
    generated_doc_id = store.add_case_document(
        case_id=case_id,
        kind="generated_document",
        version=1,
        original_filename="splnomocnenie.txt",
        payload=(
            "**Splnomocnenie**\n\n"
            "Splnomocnenec: Emilia Matonokova\n"
            "Spolocnost: Esolutions SK s.r.o.\n"
            "Prava: Vsetky pravne ukony tykajuce sa pouzivania firemneho auta.\n"
            "Podpis: ________________________\n"
        ).encode("utf-8"),
        uploaded_by_user_id=user_id,
    )

    generated_pdf = client.get(
        f"/v1/cases/{case_id}/documents/{generated_doc_id}/pdf?user_id={user_id}",
        headers=_headers(),
    )
    assert generated_pdf.status_code == 200
    generated_pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(generated_pdf.content)).pages
    )
    assert "Emilia Matonokova" in generated_pdf_text
    assert "firemneho auta" in generated_pdf_text


def test_paid_user_can_export_case_zip_with_documents_model_audit_and_checksums(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client, idx=25)
    subscription_response = client.post(
        f"/v1/users/{user_id}/subscriptions",
        headers=_headers(),
        json={"plan_code": "case"},
    )
    assert subscription_response.status_code == 201
    subscription_id = subscription_response.json()["subscription_id"]
    paid_response = client.patch(
        f"/v1/users/subscriptions/{subscription_id}",
        headers=_headers(),
        json={"status": "paid"},
    )
    assert paid_response.status_code == 200

    created = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Golden export case"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    store = ApiDatabaseStore.from_env()
    store.initialize()
    store.add_case_message(case_id=case_id, role="user", content="Priprav potvrdenie.")
    store.add_case_message(
        case_id=case_id,
        role="assistant",
        content="Právne citácie\n- Občiansky zákonník § 588",
        agent_name="LawyerSlovakia",
    )
    uploaded_doc_id = store.add_case_text_document(
        case_id=case_id,
        original_filename="facts.txt",
        content="Source facts",
        uploaded_by_user_id=user_id,
    )
    generated_doc_id = store.add_case_document(
        case_id=case_id,
        kind="generated_document",
        version=1,
        original_filename="potvrdenie.txt",
        payload="Potvrdenie\n\nSuma: 1000 EUR\nPodpis: __________".encode("utf-8"),
        uploaded_by_user_id=user_id,
    )
    usage_id = store.record_ai_model_usage(
        provider="azurefoundry",
        model="gpt-4.1",
        route_type="external",
        input_tokens=120,
        output_tokens=80,
        case_id=case_id,
        user_id=user_id,
        subscription_id=subscription_id,
        plan_code="case",
        task_type="chat_reply",
        session_id="session-1",
        question_id="question-1",
        question_text="Priprav potvrdenie.",
        answer_id="answer-1",
        audit_metadata={
            "law_citations": [
                {
                    "label": "Občiansky zákonník",
                    "summary": "Kúpna zmluva",
                }
            ]
        },
    )

    response = client.get(
        f"/v1/cases/{case_id}/export?user_id={user_id}",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert response.headers["x-case-export-schema"] == "jurisdigta.case-export.v1"
    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {
            "manifest.json",
            "case.json",
            "messages.jsonl",
            "ai-model-audit.json",
            "citations.json",
            "warnings.json",
            "sha256sums.txt",
        }.issubset(names)
        assert any(name.endswith("_facts.txt") for name in names)
        assert any(name.endswith("_potvrdenie.txt") for name in names)
        assert any(name.startswith("documents/generated/rendered-pdf/") for name in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["case_id"] == case_id
        assert manifest["message_count"] == 2
        assert manifest["document_count"] == 2
        assert manifest["ai_model_audit_count"] == 1
        audit = json.loads(archive.read("ai-model-audit.json"))
        assert audit["entries"][0]["usage_id"] == usage_id
        assert audit["entries"][0]["provider"] == "azurefoundry"
        assert audit["entries"][0]["model"] == "gpt-4.1"
        assert audit["entries"][0]["route_type"] == "external"
        citations = json.loads(archive.read("citations.json"))
        assert citations["items"]
        checksums = archive.read("sha256sums.txt").decode("utf-8")
        assert "manifest.json" in checksums
        assert "sha256sums.txt" not in checksums
        case_payload = json.loads(archive.read("case.json"))
        assert case_payload["user_id"] == user_id
        assert "password" not in json.dumps(case_payload).lower()
        assert uploaded_doc_id in json.dumps(manifest)
        assert generated_doc_id in json.dumps(manifest)


def test_free_user_case_export_is_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client, idx=26)
    created = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Free export blocked"},
    )
    assert created.status_code == 201

    response = client.get(
        f"/v1/cases/{created.json()['case_id']}/export?user_id={user_id}",
        headers=_headers(),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Case export is available only for active paid subscriptions."


def test_generated_case_document_pdf_uses_first_selected_document_block(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "storage"))

    client = TestClient(app)
    user_id = _create_user(client, idx=24)
    created = client.post(
        "/v1/cases",
        headers=_headers(),
        json={"user_id": user_id, "title": "Power of attorney"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    store = ApiDatabaseStore.from_env()
    store.initialize()
    doc_id = store.add_case_text_document(
        case_id=case_id,
        original_filename="assistant-technical.json",
        content='{"case":{"status":"document_ready"}}',
        uploaded_by_user_id=user_id,
    )
    store.add_case_message(
        case_id=case_id,
        role="assistant",
        content=(
            "Rozumiem, pripravim dokument.\n\n"
            "Zhrnutie:\n"
            "- dokument bude slovensky\n\n"
            "---\n\n"
            "**Splnomocnenie (Slovenska verzia)**\n\n"
            "Ja, Jan Novak, tymto splnomocnujem Mariu Mrkvickovu na zastupovanie.\n\n"
            "Datum: 25. juna 2026\n\n"
            "Podpis: ________________________\n\n"
            "---\n\n"
            "**Splnomocnenie (English version)**\n\n"
            "I, Jan Novak, hereby authorize Maria Mrkvickova to represent me in all legal "
            "and administrative actions related to the matter, including receiving documents "
            "and signing procedural submissions on my behalf.\n\n"
            "Datum: June 25, 2026\n\n"
            "Podpis: ________________________\n\n"
            "---\n\n"
            "Technicke udaje som ulozil do dokumentu pripadu: "
            f"/v1/cases/{case_id}/documents/{doc_id}?user_id={user_id}\n\n"
            "Prosim, doplnte dalsie udaje, ak chcete dokument rozsirit."
        ),
        agent_name="LawyerSlovakia",
    )

    generated_pdf = client.get(
        f"/v1/cases/{case_id}/documents/{doc_id}/pdf?user_id={user_id}",
        headers=_headers(),
    )

    assert generated_pdf.status_code == 200
    assert generated_pdf.headers["content-disposition"].endswith(
        f'filename="power-of-attorney_{doc_id}_splnomocnenie.pdf"'
    )
    generated_pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(generated_pdf.content)).pages
    )
    assert PdfReader(BytesIO(generated_pdf.content)).metadata.title == "Splnomocnenie"
    assert "Splnomocnenie (Slovenska verzia)" in generated_pdf_text
    assert "Jan Novak" in generated_pdf_text
    assert "tymto splnomocnujem" in generated_pdf_text
    assert "Rozumiem" not in generated_pdf_text
    assert "Zhrnutie" not in generated_pdf_text
    assert "English version" not in generated_pdf_text
    assert "hereby authorize" not in generated_pdf_text
    assert "Technicke udaje" not in generated_pdf_text
    assert "Prosim, doplnte" not in generated_pdf_text
    assert "**" not in generated_pdf_text
    assert "---" not in generated_pdf_text


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


def test_case_ai_model_audit_lists_question_model_usage() -> None:
    import app.cases_api as cases_api

    client = TestClient(app)

    class _FakeStore:
        def get_case(self, *, case_id: str):
            return SimpleNamespace(case_id=case_id, user_id="user-1", status="active")

        def list_ai_model_usage_audit(self, *, case_id: str, limit: int = 100, offset: int = 0):
            assert case_id == "case-1"
            assert limit == 3
            assert offset == 0
            return [
                AIModelUsageAuditEntry(
                    usage_id="usage-1",
                    case_id=case_id,
                    user_id="user-1",
                    subscription_id="sub-1",
                    plan_code="case",
                    task_type="chat_reply",
                    model_group_id="",
                    provider="azurefoundry",
                    model="gpt-4.1",
                    route_type="external",
                    input_tokens=120,
                    cached_input_tokens=0,
                    output_tokens=80,
                    total_tokens=200,
                    estimated_cost_provider_currency=0.0,
                    estimated_cost_eur=0.01,
                    provider_currency="EUR",
                    exchange_rate_used=1.0,
                    request_started_at="2026-06-26T10:00:00Z",
                    request_completed_at="2026-06-26T10:00:02Z",
                    latency_ms=2000,
                    status="ok",
                    fallback_reason="",
                    confidentiality_warning_ack_id="",
                    session_id="session-1",
                    question_id="question-1",
                    question_preview="What model answered this question?",
                    question_sha256="a" * 64,
                    answer_id="answer-1",
                    audit_metadata={"source": "chat.direct_reply"},
                    created_at="2026-06-26T10:00:02Z",
                )
            ]

    app.dependency_overrides[cases_api.get_store] = lambda: _FakeStore()
    try:
        response = client.get(
            "/v1/cases/case-1/ai-model-audit?user_id=user-1&offset=0&limit=2",
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.pop(cases_api.get_store, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "case-1"
    assert payload["has_more"] is False
    assert payload["entries"][0]["question_id"] == "question-1"
    assert payload["entries"][0]["question_preview"] == "What model answered this question?"
    assert payload["entries"][0]["model"] == "gpt-4.1"
    assert payload["entries"][0]["route_type"] == "external"


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
