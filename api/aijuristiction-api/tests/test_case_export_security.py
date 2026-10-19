from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.cases_api import get_store
from app.case_security import auth_store
from app.case_exports_api import process_exports
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.case_exports import now


@pytest.fixture
def scenario():
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = [store.create_user(email=f"security-{i}@example.invalid", password="synthetic-only") for i in range(3)]
    credentials = []
    for user in users:
        token = store.issue_device_auth_token(user_id=user.user_id, device_id="synthetic-security-test")
        credentials.append({"x-api-key": "aijuris", "x-jurisdigta-user-id": user.user_id,
                            "x-jurisdigta-device-id": "synthetic-security-test", "x-jurisdigta-device-token": token})
    with store._connect() as conn:
        store._execute(conn, "UPDATE users SET role = 'admin' WHERE user_id = ?", (users[2].user_id,))
    case = store.create_case(user_id=users[0].user_id, company_id=None, title="Synthetic encrypted case")
    store.add_case_document(case_id=case.case_id, kind="uploaded", version=1, original_filename="source.txt", payload=b"Synthetic encrypted evidence")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[auth_store] = lambda: store
    try:
        yield TestClient(app), store, users, credentials, case
    finally:
        app.dependency_overrides.clear()


def test_real_auth_denies_impersonation_and_missing_token(scenario):
    client, store, users, credentials, case = scenario
    path = f"/v1/cases/{case.case_id}/history?user_id={users[0].user_id}"
    assert client.get(path, headers={"x-api-key": "aijuris"}).status_code == 401
    assert client.get("/v1/case-workflows/runs/latest", params={"case_id": case.case_id, "user_id": users[0].user_id}, headers=credentials[1]).status_code == 401
    assert client.get(path, headers=credentials[1]).status_code == 401
    assert client.get(path, headers=credentials[0]).status_code == 200
    assert client.get(f"/v1/cases/{case.case_id}/history?user_id={users[1].user_id}", headers=credentials[1]).status_code == 404


def test_admin_permission_consent_archive_and_replay(scenario):
    client, store, users, credentials, case = scenario
    from app.decision_trace_api import require_decision_trace_admin
    from app.ai_model_admin_api import AdminContext
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as denied:
        require_decision_trace_admin(AdminContext(user_id=users[2].user_id, email=users[2].email), store)
    assert denied.value.status_code == 403
    payload = {"case_ids": [case.case_id], "purpose": "Synthetic support review"}
    assert client.post("/v1/case-exports", headers=credentials[2], json=payload).status_code == 403
    with store._connect() as conn:
        store._execute(conn, "INSERT INTO case_export_permissions VALUES (?, ?)", (users[2].user_id, now()))
    response = client.post("/v1/case-exports", headers=credentials[2], json=payload)
    assert response.status_code == 202
    request_id = response.json()["request_id"]
    download = f"/v1/case-exports/{request_id}/download"
    decision = f"/v1/case-exports/{request_id}/decision"
    assert client.post(download, headers=credentials[2]).status_code == 403
    assert client.post(decision, headers=credentials[1], json={"decision": "approved"}).status_code == 403
    assert client.post(decision, headers=credentials[0], json={"decision": "approved"}).status_code == 200
    process_exports(store)
    response = client.post(download, headers={**credentials[2], "content-type": "application/json"})
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        with ZipFile(BytesIO(archive.read(f"cases/{case.case_id}.zip"))) as case_zip:
            contents = [case_zip.read(name) for name in case_zip.namelist()]
            assert any(b"Synthetic encrypted evidence" in value for value in contents)
            assert not any(b"jdenc1:" in value for value in contents)
    assert client.post(download, headers=credentials[2]).status_code == 403


@pytest.mark.parametrize("operation", ["history", "citations", "ai-model-audit", "export", "documents/context", "documents/debug", "document", "patch", "delete"])
def test_other_owner_cannot_access_or_mutate_case(scenario, operation):
    client, store, users, credentials, case = scenario
    method = "GET"
    suffix = operation
    payload = None
    if operation == "document":
        suffix = "documents/" + store.list_case_documents(case_id=case.case_id)[0].doc_id
    elif operation == "patch":
        method, suffix = "PATCH", ""
        payload = {"user_id": users[1].user_id, "title": "Unauthorized rename"}
    elif operation == "delete":
        method, suffix = "DELETE", ""
    response = client.request(method, f"/v1/cases/{case.case_id}" + ("/" + suffix if suffix else ""),
                              params={"user_id": users[1].user_id}, headers=credentials[1], json=payload)
    assert response.status_code == 404
    assert store.get_case(case_id=case.case_id).title == "Synthetic encrypted case"


def test_missing_key_fails_closed_with_safe_service_error(scenario):
    from pathlib import Path
    client, store, users, credentials, case = scenario
    Path(store.case_cipher.key_file).unlink()
    response = client.get(f"/v1/cases/{case.case_id}/history?user_id={users[0].user_id}", headers=credentials[0])
    assert response.status_code == 503
    assert "Synthetic encrypted" not in response.text
    assert response.headers["cache-control"] == "no-store"
