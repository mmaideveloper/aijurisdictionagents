from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


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
