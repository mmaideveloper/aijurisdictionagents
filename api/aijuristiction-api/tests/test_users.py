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


def test_subscription_lifecycle(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    sign_up_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900121212",
            "email": "plans@example.com",
            "password": "secret-pass",
            "first_name": "Plan",
            "last_name": "User",
        },
    )
    assert sign_up_response.status_code == 201
    user_id = sign_up_response.json()["user_id"]

    plans_response = client.get("/v1/users/subscriptions/plans", headers=AUTH_HEADERS)
    assert plans_response.status_code == 200
    plans = plans_response.json()
    assert {item["plan_code"] for item in plans} == {"free", "case", "basic", "premium"}

    subscriptions_response = client.get(f"/v1/users/{user_id}/subscriptions", headers=AUTH_HEADERS)
    assert subscriptions_response.status_code == 200
    existing = subscriptions_response.json()
    assert existing[0]["plan_code"] == "free"
    assert existing[0]["status"] == "paid"

    request_response = client.post(
        f"/v1/users/{user_id}/subscriptions",
        headers=AUTH_HEADERS,
        json={"plan_code": "basic"},
    )
    assert request_response.status_code == 201
    requested = request_response.json()
    assert requested["status"] == "pending"

    paying_response = client.patch(
        f"/v1/users/subscriptions/{requested['subscription_id']}",
        headers=AUTH_HEADERS,
        json={"status": "paying"},
    )
    assert paying_response.status_code == 200
    assert paying_response.json()["status"] == "paying"

    paid_response = client.patch(
        f"/v1/users/subscriptions/{requested['subscription_id']}",
        headers=AUTH_HEADERS,
        json={"status": "paid"},
    )
    assert paid_response.status_code == 200
    paid = paid_response.json()
    assert paid["status"] == "paid"
    assert paid["starts_at"] is not None
    assert paid["ends_at"] is not None


def test_subscription_checkout_payment_failure_does_not_upgrade_for_non_whitelisted_phone(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    sign_up_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900565656",
            "email": "checkout@example.com",
            "password": "secret-pass",
            "first_name": "Checkout",
            "last_name": "User",
        },
    )
    assert sign_up_response.status_code == 201
    user_id = sign_up_response.json()["user_id"]

    checkout_response = client.post(
        f"/v1/users/{user_id}/subscriptions/checkout",
        headers=AUTH_HEADERS,
        json={"plan_code": "premium", "payment_provider": "paypal"},
    )
    assert checkout_response.status_code == 201
    checkout = checkout_response.json()
    assert checkout["payment_provider"] == "paypal"
    assert checkout["payment_status"] == "pending"
    assert checkout["amount_eur"] == 100
    assert checkout["checkout_url"].startswith("https://www.sandbox.paypal.com")

    confirm_response = client.post(
        f"/v1/users/subscriptions/{checkout['subscription_id']}/confirm-payment",
        headers=AUTH_HEADERS,
        json={"payment_id": checkout["payment_id"]},
    )
    assert confirm_response.status_code == 402

    subscriptions_response = client.get(f"/v1/users/{user_id}/subscriptions", headers=AUTH_HEADERS)
    assert subscriptions_response.status_code == 200
    subscriptions = subscriptions_response.json()
    assert subscriptions[0]["subscription_id"] == checkout["subscription_id"]
    assert subscriptions[0]["status"] == "canceled"
    assert subscriptions[1]["plan_code"] == "free"
    assert subscriptions[1]["status"] == "paid"


def test_subscription_checkout_and_payment_confirmation_success_for_whitelisted_phone(
    monkeypatch, tmp_path: Path
) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    sign_up_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421944400166",
            "email": "checkout-allowed@example.com",
            "password": "secret-pass",
            "first_name": "Allowed",
            "last_name": "User",
        },
    )
    assert sign_up_response.status_code == 201
    user_id = sign_up_response.json()["user_id"]

    checkout_response = client.post(
        f"/v1/users/{user_id}/subscriptions/checkout",
        headers=AUTH_HEADERS,
        json={"plan_code": "premium", "payment_provider": "paypal"},
    )
    assert checkout_response.status_code == 201
    checkout = checkout_response.json()

    confirm_response = client.post(
        f"/v1/users/subscriptions/{checkout['subscription_id']}/confirm-payment",
        headers=AUTH_HEADERS,
        json={"payment_id": checkout["payment_id"]},
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "paid"


def test_subscription_checkout_accepts_google_pay(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    sign_up_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900676767",
            "email": "googlepay@example.com",
            "password": "secret-pass",
            "first_name": "Google",
            "last_name": "Pay",
        },
    )
    assert sign_up_response.status_code == 201
    user_id = sign_up_response.json()["user_id"]

    checkout_response = client.post(
        f"/v1/users/{user_id}/subscriptions/checkout",
        headers=AUTH_HEADERS,
        json={"plan_code": "basic", "payment_provider": "google_pay"},
    )
    assert checkout_response.status_code == 201
    assert checkout_response.json()["checkout_url"].startswith("https://pay.google.com")
