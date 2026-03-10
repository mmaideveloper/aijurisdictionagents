from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH_HEADERS = {"x-api-key": "aijuris"}


def _configure_db_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))


def test_sign_up_sign_in_and_update_profile(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    sign_up_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421 900 111 222",
            "email": "founder@example.com",
            "password": "secret-pass",
            "first_name": "Marek",
            "last_name": "Founder",
        },
    )
    assert sign_up_response.status_code == 201
    signed_up = sign_up_response.json()
    assert signed_up["phone_number"] == "+421900111222"
    assert signed_up["email"] == "founder@example.com"
    assert signed_up["first_name"] == "Marek"
    assert signed_up["last_name"] == "Founder"
    assert signed_up["full_name"] == "Marek Founder"

    phone_sign_in_response = client.post(
        "/v1/users/sign-in/phone",
        headers=AUTH_HEADERS,
        json={"phone_number": "+421900111222"},
    )
    assert phone_sign_in_response.status_code == 200
    assert phone_sign_in_response.json()["user_id"] == signed_up["user_id"]

    email_sign_in_response = client.post(
        "/v1/users/sign-in",
        headers=AUTH_HEADERS,
        json={
            "email": "founder@example.com",
            "password": "secret-pass",
        },
    )
    assert email_sign_in_response.status_code == 200
    assert email_sign_in_response.json()["user_id"] == signed_up["user_id"]

    update_response = client.patch(
        f"/v1/users/{signed_up['user_id']}",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900333444",
            "password": "new-secret",
            "first_name": "Marek",
            "last_name": "Updated",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["phone_number"] == "+421900333444"
    assert updated["last_name"] == "Updated"
    assert updated["full_name"] == "Marek Updated"

    old_phone_response = client.post(
        "/v1/users/sign-in/phone",
        headers=AUTH_HEADERS,
        json={"phone_number": "+421900111222"},
    )
    assert old_phone_response.status_code == 404

    new_phone_response = client.post(
        "/v1/users/sign-in/phone",
        headers=AUTH_HEADERS,
        json={"phone_number": "+421900333444"},
    )
    assert new_phone_response.status_code == 200

    old_password_response = client.post(
        "/v1/users/sign-in",
        headers=AUTH_HEADERS,
        json={
            "email": "founder@example.com",
            "password": "secret-pass",
        },
    )
    assert old_password_response.status_code == 401

    new_password_response = client.post(
        "/v1/users/sign-in",
        headers=AUTH_HEADERS,
        json={
            "email": "founder@example.com",
            "password": "new-secret",
        },
    )
    assert new_password_response.status_code == 200


def test_sign_up_rejects_duplicate_phone_and_email(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    first_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900111222",
            "email": "founder@example.com",
            "password": "secret-pass",
            "first_name": "Marek",
            "last_name": "Founder",
        },
    )
    assert first_response.status_code == 201

    duplicate_phone = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900111222",
            "email": "other@example.com",
            "password": "secret-pass",
            "first_name": "Ina",
            "last_name": "User",
        },
    )
    assert duplicate_phone.status_code == 409
    assert "phone" in duplicate_phone.json()["detail"].lower()

    duplicate_email = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900999888",
            "email": "founder@example.com",
            "password": "secret-pass",
            "first_name": "Ina",
            "last_name": "User",
        },
    )
    assert duplicate_email.status_code == 409
    assert "email" in duplicate_email.json()["detail"].lower()
