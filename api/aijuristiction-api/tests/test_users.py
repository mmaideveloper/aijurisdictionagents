from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.email import EmailNotificationService
from app.services.email_scheduler import EmailScheduler
from app.services.email_queue import EmailQueueConfig, EmailQueueStore
from app.users.api import get_email_scheduler, get_user_store

client = TestClient(app)
AUTH_HEADERS = {"x-api-key": "aijuris"}


def _configure_db_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DB_OPTION", "local")
    monkeypatch.setenv("STORAGE_OPTION", "local")
    monkeypatch.setenv("DB_LOCAL", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("STORE_LOCAL", str(tmp_path / "blob"))
    monkeypatch.setenv("EMAIL_DB_OPTION", "local")
    monkeypatch.setenv("EMAIL_DB_LOCAL", str(tmp_path / "email.sqlite3"))
    monkeypatch.setenv("EMAIL_SCHEDULER_ENABLED", "false")


def _fetch_emails(email_db_path: Path) -> list[tuple[str, str, str, str]]:
    with sqlite3.connect(email_db_path) as conn:
        return conn.execute(
            "SELECT recipient, subject, status, attempts FROM email_outbox ORDER BY created_at ASC"
        ).fetchall()


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

    queued = _fetch_emails(tmp_path / "email.sqlite3")
    assert queued == [("founder@example.com", "Welcome to AI Jurisdiction", "pending", 0)]

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


def test_sign_up_complete_requires_valid_email_code(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    send_code_response = client.post(
        "/v1/users/sign-up/send-code",
        headers=AUTH_HEADERS,
        json={"email": "verify@example.com"},
    )
    assert send_code_response.status_code == 202

    with sqlite3.connect(tmp_path / "api.sqlite3") as conn:
        row = conn.execute(
            "SELECT code_hash FROM registration_codes WHERE email = ?",
            ("verify@example.com",),
        ).fetchone()
    assert row is not None

    invalid_complete = client.post(
        "/v1/users/sign-up/complete",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900111333",
            "email": "verify@example.com",
            "password": "secret-pass",
            "verification_code": "123456",
        },
    )
    assert invalid_complete.status_code == 400

    with sqlite3.connect(tmp_path / "api.sqlite3") as conn:
        code_hash = conn.execute(
            "SELECT code_hash FROM registration_codes WHERE email = ?",
            ("verify@example.com",),
        ).fetchone()[0]

    valid_code = None
    for candidate in range(0, 1_000_000):
        code = f"{candidate:06d}"
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if digest == code_hash:
            valid_code = code
            break
    assert valid_code is not None

    complete_response = client.post(
        "/v1/users/sign-up/complete",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900111333",
            "email": "verify@example.com",
            "password": "secret-pass",
            "verification_code": valid_code,
        },
    )
    assert complete_response.status_code == 201


def test_device_bound_sign_in_flow(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)
    sign_up_response = client.post(
        "/v1/users/sign-up",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900121314",
            "email": "device-login@example.com",
            "password": "secret-pass",
        },
    )
    assert sign_up_response.status_code == 201
    send_code_response = client.post(
        "/v1/users/sign-in/send-code",
        headers=AUTH_HEADERS,
        json={"phone_number": "+421900121314", "device_id": "test-device-1"},
    )
    assert send_code_response.status_code == 202

    with sqlite3.connect(tmp_path / "api.sqlite3") as conn:
        code_hash = conn.execute(
            "SELECT code_hash FROM registration_codes WHERE email = ?",
            ("signin:+421900121314:test-device-1",),
        ).fetchone()[0]

    valid_code = None
    for candidate in range(0, 1_000_000):
        code = f"{candidate:06d}"
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if digest == code_hash:
            valid_code = code
            break
    assert valid_code is not None

    verify_response = client.post(
        "/v1/users/sign-in/verify-code",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900121314",
            "device_id": "test-device-1",
            "verification_code": valid_code,
        },
    )
    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["device_auth_token"]

    silent_login_response = client.post(
        "/v1/users/sign-in/device",
        headers=AUTH_HEADERS,
        json={
            "phone_number": "+421900121314",
            "device_id": "test-device-1",
            "device_token": payload["device_auth_token"],
        },
    )
    assert silent_login_response.status_code == 200
    silent_payload = silent_login_response.json()
    assert silent_payload["user_id"] == payload["user_id"]
    assert silent_payload["device_auth_token"]


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


def test_sign_up_returns_conflict_for_postgres_style_duplicate_user(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    class FakePostgresIntegrityError(Exception):
        pass

    class DuplicateUserStore:
        def create_user(self, **_kwargs):
            raise FakePostgresIntegrityError(
                'duplicate key value violates unique constraint "users_email_key"'
            )

    app.dependency_overrides[get_user_store] = lambda: DuplicateUserStore()
    scheduler = EmailScheduler.from_env()
    app.dependency_overrides[get_email_scheduler] = lambda: scheduler
    monkeypatch.setattr("app.users.api._psycopg_module", type("FakePsycopg", (), {"IntegrityError": FakePostgresIntegrityError}))
    try:
        response = client.post(
            "/v1/users/sign-up",
            headers=AUTH_HEADERS,
            json={
                "phone_number": "+421900111222",
                "email": "founder@example.com",
                "password": "secret-pass",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "Email is already registered"


def test_subscription_lifecycle_queues_notifications(monkeypatch, tmp_path: Path) -> None:
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

    request_response = client.post(
        f"/v1/users/{user_id}/subscriptions",
        headers=AUTH_HEADERS,
        json={"plan_code": "basic"},
    )
    assert request_response.status_code == 201
    requested = request_response.json()

    paying_response = client.patch(
        f"/v1/users/subscriptions/{requested['subscription_id']}",
        headers=AUTH_HEADERS,
        json={"status": "paying"},
    )
    assert paying_response.status_code == 200

    failed_response = client.patch(
        f"/v1/users/subscriptions/{requested['subscription_id']}",
        headers=AUTH_HEADERS,
        json={"status": "failed"},
    )
    assert failed_response.status_code == 200

    rows = _fetch_emails(tmp_path / "email.sqlite3")
    assert [row[1] for row in rows] == [
        "Welcome to AI Jurisdiction",
        "Subscription change requested",
        "Subscription status changed",
        "Payment failed",
    ]


def test_scheduler_marks_failed_after_two_attempts(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)
    monkeypatch.setenv("EMAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("EMAIL_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "1")

    store = EmailQueueStore(EmailQueueConfig.from_env())
    store.initialize()
    store.enqueue_email(
        email_id="email-1",
        recipient="nobody@example.com",
        subject="S1",
        body="B1",
        metadata={"event": "test"},
    )

    scheduler = EmailScheduler.from_env()
    assert scheduler.run_once(limit=10) == 0
    assert scheduler.run_once(limit=10) == 0

    with sqlite3.connect(tmp_path / "email.sqlite3") as conn:
        status, attempts = conn.execute(
            "SELECT status, attempts FROM email_outbox WHERE email_id='email-1'"
        ).fetchone()
    assert status == "failed"
    assert attempts == 2


def test_email_service_defaults_to_jurisdigta_smtp(monkeypatch) -> None:
    for name in (
        "EMAIL_SENDER",
        "EMAIL_TRANSPORT",
        "EMAIL_SMTP_HOST",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_USERNAME",
        "EMAIL_SMTP_PASSWORD",
        "EMAIL_SMTP_USE_TLS",
    ):
        monkeypatch.delenv(name, raising=False)

    service = EmailNotificationService.from_env()

    assert service.sender == "no-reply@jurisdigta.eu"
    assert service.smtp_host == "mail.webhourse.sk"
    assert service.smtp_port == 587
    assert service.smtp_username == "no-reply@jurisdigta.eu"
    assert service.smtp_password is None
    assert service.smtp_use_tls is True


def test_claim_pending_prevents_double_pick(monkeypatch, tmp_path: Path) -> None:
    _configure_db_env(monkeypatch, tmp_path)

    store = EmailQueueStore(EmailQueueConfig.from_env())
    store.initialize()
    store.enqueue_email(
        email_id="email-1",
        recipient="dup@example.com",
        subject="S1",
        body="B1",
        metadata={"event": "test"},
    )

    first_batch = store.claim_pending(limit=10)
    second_batch = store.claim_pending(limit=10)

    assert len(first_batch) == 1
    assert first_batch[0].email_id == "email-1"
    assert second_batch == []


def test_email_queue_postgres_config_does_not_create_local_sqlite_dirs(tmp_path: Path) -> None:
    sqlite_parent = tmp_path / "missing" / "sqlite"
    config = EmailQueueConfig(
        db_option="postgres",
        db_local=sqlite_parent / "email.sqlite3",
        db_cloud="postgresql://example",
    )
    assert not sqlite_parent.exists()

    EmailQueueStore(config)

    assert not sqlite_parent.exists()


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
    rows = _fetch_emails(tmp_path / "email.sqlite3")
    assert [row[1] for row in rows] == [
        "Welcome to AI Jurisdiction",
        "Subscription status changed",
    ]


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
    rows = _fetch_emails(tmp_path / "email.sqlite3")
    assert [row[1] for row in rows] == [
        "Welcome to AI Jurisdiction",
        "Payment confirmed",
    ]


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
