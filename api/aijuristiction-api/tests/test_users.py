from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.email_scheduler import EmailScheduler
from app.services.email_queue import EmailQueueConfig, EmailQueueStore

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
