from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.contact_api import CONTACT_RECIPIENT, _rate_limit_hits, get_contact_email_service
from app.main import app


class _FakeEmailService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        self.calls.append(
            {
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "attachments": attachments,
            }
        )


def test_contact_request_queues_email_to_public_contact_address() -> None:
    _rate_limit_hits.clear()
    email_service = _FakeEmailService()
    app.dependency_overrides[get_contact_email_service] = lambda: email_service
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/contact",
            headers={"origin": "https://jurisdigta.eu", "user-agent": "pytest"},
            json={
                "name": "Marek Founder",
                "email": "marek@example.com",
                "company": "JurisDigta",
                "topic": "Demo",
                "message": "Please contact me about the corporate demo request.",
                "website": "",
                "started_at": 123,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {
        "status": "sent",
        "recipient": CONTACT_RECIPIENT,
    }
    assert len(email_service.calls) == 1
    sent = email_service.calls[0]
    assert sent["recipient"] == "info@jurisdigta.eu"
    assert sent["subject"] == "JurisDigta contact request: Demo"
    assert "Email: marek@example.com" in sent["body"]
    assert "Please contact me about the corporate demo request." in sent["body"]


def test_contact_request_accepts_short_test_message() -> None:
    _rate_limit_hits.clear()
    email_service = _FakeEmailService()
    app.dependency_overrides[get_contact_email_service] = lambda: email_service
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/contact",
            json={
                "name": "mm",
                "email": "mmaideveloper@gmail.com",
                "company": "mm",
                "topic": "mm",
                "message": "mmmmm",
                "website": "",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert email_service.calls[0]["recipient"] == "info@jurisdigta.eu"
    assert "Email: mmaideveloper@gmail.com" in email_service.calls[0]["body"]
    assert "mmmmm" in email_service.calls[0]["body"]


def test_contact_request_requires_captcha_when_enabled(monkeypatch) -> None:
    _rate_limit_hits.clear()
    monkeypatch.setenv("CONTACT_CAPTCHA_REQUIRED", "true")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    email_service = _FakeEmailService()
    app.dependency_overrides[get_contact_email_service] = lambda: email_service
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/contact",
            json={
                "name": "Marek Founder",
                "email": "marek@example.com",
                "topic": "Demo",
                "message": "Please contact me about the corporate demo request.",
                "website": "",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert email_service.calls == []


def test_contact_request_verifies_captcha_before_sending(monkeypatch) -> None:
    _rate_limit_hits.clear()
    class _FakeTurnstileResponse:
        def __enter__(self) -> "_FakeTurnstileResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"success": true}'

    def fake_urlopen(request: object, timeout: int) -> _FakeTurnstileResponse:
        assert timeout == 8
        assert request is not None
        return _FakeTurnstileResponse()

    monkeypatch.setenv("CONTACT_CAPTCHA_REQUIRED", "true")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "secret")
    monkeypatch.setattr("app.contact_api.urlopen", fake_urlopen)
    email_service = _FakeEmailService()
    app.dependency_overrides[get_contact_email_service] = lambda: email_service
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/contact",
            json={
                "name": "Marek Founder",
                "email": "marek@example.com",
                "topic": "Demo",
                "message": "Please contact me about the corporate demo request.",
                "website": "",
                "turnstile_token": "token",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert email_service.calls[0]["recipient"] == "info@jurisdigta.eu"


def test_contact_request_rate_limits_by_client_ip(monkeypatch) -> None:
    _rate_limit_hits.clear()
    monkeypatch.setenv("CONTACT_RATE_LIMIT_MAX_REQUESTS", "1")
    monkeypatch.setenv("CONTACT_RATE_LIMIT_WINDOW_SECONDS", "600")
    email_service = _FakeEmailService()
    app.dependency_overrides[get_contact_email_service] = lambda: email_service
    client = TestClient(app)
    payload = {
        "name": "Marek Founder",
        "email": "marek@example.com",
        "topic": "Demo",
        "message": "Please contact me about the corporate demo request.",
        "website": "",
    }
    try:
        first_response = client.post("/v1/contact", headers={"x-forwarded-for": "203.0.113.9"}, json=payload)
        second_response = client.post("/v1/contact", headers={"x-forwarded-for": "203.0.113.9"}, json=payload)
    finally:
        app.dependency_overrides.clear()
        _rate_limit_hits.clear()

    assert first_response.status_code == 202
    assert second_response.status_code == 429
    assert len(email_service.calls) == 1


def test_contact_request_rejects_honeypot_and_links() -> None:
    _rate_limit_hits.clear()
    email_service = _FakeEmailService()
    app.dependency_overrides[get_contact_email_service] = lambda: email_service
    client = TestClient(app)
    try:
        honeypot_response = client.post(
            "/v1/contact",
            json={
                "name": "Marek Founder",
                "email": "marek@example.com",
                "topic": "Demo",
                "message": "Please contact me about the corporate demo request.",
                "website": "spam",
            },
        )
        link_response = client.post(
            "/v1/contact",
            json={
                "name": "Marek Founder",
                "email": "marek@example.com",
                "topic": "Demo",
                "message": "Please visit https://example.com for my request.",
                "website": "",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert honeypot_response.status_code == 400
    assert link_response.status_code == 400
    assert email_service.calls == []
