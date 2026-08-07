from __future__ import annotations

import json
import re
import sqlite3

from fastapi.testclient import TestClient

from app.cases_api import _STORE_CACHE
from app.main import app
from aijurisdictionagents.api_db import ApiDatabaseStore


def _headers() -> dict[str, str]:
    return {"x-api-key": "aijuris"}


def test_slovak_guest_document_share_otp_pdf_and_revocation(monkeypatch, tmp_path) -> None:
    database = tmp_path / "api.sqlite3"
    storage = tmp_path / "storage"
    email_database = tmp_path / "email.sqlite3"
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(database))
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("STORE_LOCAL", str(storage))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(email_database))
    monkeypatch.setenv("JURISDIGTA_AGENT_BASE_URL", "https://agent.test")
    _STORE_CACHE.clear()

    client = TestClient(app)
    signup = client.post(
        "/v1/users/sign-up",
        headers=_headers(),
        json={
            "phone_number": "+421900557001",
            "email": "sender557@example.com",
            "password": "secret",
        },
    )
    assert signup.status_code == 201
    user_id = signup.json()["user_id"]
    created_case = client.post(
        "/v1/cases", headers=_headers(), json={"user_id": user_id, "title": "Citlivý prípad"}
    )
    assert created_case.status_code == 201
    case_id = created_case.json()["case_id"]
    store = ApiDatabaseStore(db_path=database, blob_root=storage)
    store.initialize()
    doc_id = store.add_case_document(
        case_id=case_id,
        kind="generated_document",
        version=1,
        original_filename="dokument.txt",
        payload="**Dohoda**\n\nObsah dokumentu".encode(),
        uploaded_by_user_id=user_id,
    )

    invitation = client.post(
        f"/v1/cases/{case_id}/documents/send-email",
        headers=_headers(),
        json={
            "user_id": user_id,
            "recipient": "guest557@example.com",
            "case_subject": "must-not-appear",
            "doc_ids": [doc_id],
            "locale": "sk",
        },
    )
    assert invitation.status_code == 200
    invitation_payload = invitation.json()
    assert invitation_payload["attachment_count"] == 0
    share_token = invitation_payload["share_url"].rsplit("/", 1)[1]

    with sqlite3.connect(email_database) as conn:
        invitation_row = conn.execute(
            "SELECT subject, body, metadata_json FROM email_outbox WHERE metadata_json LIKE '%document_share_invitation%'"
        ).fetchone()
    assert invitation_row is not None
    assert invitation_row[0] == "Bol vám zdieľaný právny dokument | JurisDigta"
    assert "must-not-appear" not in invitation_row[1]
    assert "attachments" not in json.loads(invitation_row[2])

    code_request = client.post(f"/v1/document-shares/{share_token}/request-code")
    assert code_request.status_code == 200
    assert code_request.json()["locale"] == "sk"
    with sqlite3.connect(email_database) as conn:
        otp_row = conn.execute(
            "SELECT body FROM email_outbox WHERE metadata_json LIKE '%one_time_code%'"
        ).fetchone()
    assert otp_row is not None
    code_match = re.search(r"\b(\d{6})\b", otp_row[0])
    assert code_match is not None

    verified = client.post(
        f"/v1/document-shares/{share_token}/verify", json={"code": code_match.group(1)}
    )
    assert verified.status_code == 200
    session_token = verified.json()["session_token"]
    pdf = client.get(
        "/v1/document-shares/content/pdf", headers={"Authorization": f"Bearer {session_token}"}
    )
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["cache-control"].startswith("no-store")
    assert pdf.headers["referrer-policy"] == "no-referrer"

    replay = client.post(
        f"/v1/document-shares/{share_token}/verify", json={"code": code_match.group(1)}
    )
    assert replay.status_code == 400
    revoked = client.delete(
        f"/v1/cases/{case_id}/documents/shares/{invitation_payload['share_id']}?user_id={user_id}",
        headers=_headers(),
    )
    assert revoked.status_code == 204
    unavailable = client.get(
        "/v1/document-shares/content/pdf", headers={"Authorization": f"Bearer {session_token}"}
    )
    assert unavailable.status_code == 404
