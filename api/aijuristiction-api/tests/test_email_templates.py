from __future__ import annotations

import base64
from typing import Any, cast

from app.services.email import EmailNotificationService
from app.services.email_queue import EmailQueueStore, QueuedEmail
from app.services.email_scheduler import EmailScheduler
from app.services.email_templates import (
    FOOTER_CID,
    HEADER_CID,
    build_welcome_email,
    ensure_branded_email_metadata,
)


def test_branded_metadata_adds_inline_cid_assets_and_skips_otp() -> None:
    metadata = ensure_branded_email_metadata(
        subject="Payment confirmed",
        body="Hello, payment was confirmed.",
        metadata={"event": "subscription_payment"},
    )

    assert f"cid:{HEADER_CID}" in metadata["html_body"]
    assert f"cid:{FOOTER_CID}" in metadata["html_body"]
    assert metadata["template"] == "jurisdigta-email-v1"
    assert any(item["content_id"] == HEADER_CID for item in metadata["attachments"])
    assert any(item["content_id"] == FOOTER_CID for item in metadata["attachments"])

    otp_metadata = {"event": "sign_in_code"}
    assert (
        ensure_branded_email_metadata(
            subject="Your login code",
            body="your one time login code is: 123456",
            metadata=otp_metadata,
        )
        is otp_metadata
    )


def test_scheduler_brands_legacy_non_otp_email_and_keeps_code_plain() -> None:
    sent: list[dict[str, Any]] = []

    class FakeQueueStore:
        def claim_pending(self, *, limit: int = 50) -> list[QueuedEmail]:
            return [
                QueuedEmail(
                    "email-1",
                    "paid@example.com",
                    "Payment confirmed",
                    "Hello, payment was confirmed.",
                    {"event": "subscription_payment"},
                    0,
                ),
                QueuedEmail(
                    "email-2",
                    "otp@example.com",
                    "Your login code",
                    "your one time login code is: 123456",
                    {"event": "sign_in_code"},
                    0,
                ),
            ]

        def mark_sent(self, *, email_id: str) -> None:
            sent.append({"marked_sent": email_id})

        def mark_failed_attempt(self, *, email_id: str, error_message: str) -> None:  # pragma: no cover
            raise AssertionError(error_message)

    class FakeEmailService:
        def send_email(self, **kwargs: Any) -> None:
            sent.append(kwargs)

    scheduler = EmailScheduler(
        queue_store=cast(EmailQueueStore, FakeQueueStore()),
        email_service=cast(EmailNotificationService, FakeEmailService()),
    )

    assert scheduler.run_once(limit=10) == 2

    first_email = sent[0]
    assert f"cid:{HEADER_CID}" in first_email["html_body"]
    assert any(item["content_id"] == HEADER_CID for item in first_email["attachments"])
    second_email = sent[2]
    assert second_email["html_body"] is None
    assert second_email["attachments"] == []


def test_branded_document_share_email_uses_selected_slovak_locale() -> None:
    metadata = ensure_branded_email_metadata(
        subject="Bol vám zdieľaný právny dokument | JurisDigta",
        body="Otvorte chránený dokument.",
        metadata={
            "event": "document_share_invitation",
            "locale": "sk",
            "html_body": "<p><a href='https://agent.test/shared-documents/token'>Otvoriť chránený dokument</a></p>",
        },
    )

    assert '<html lang="sk">' in metadata["html_body"]
    assert "Tento e-mail zámerne neobsahuje nepotrebné údaje" in metadata["html_body"]
    header = next(item for item in metadata["attachments"] if item["content_id"] == HEADER_CID)
    footer = next(item for item in metadata["attachments"] if item["content_id"] == FOOTER_CID)
    header_svg = base64.b64decode(header["content_base64"]).decode("utf-8")
    footer_svg = base64.b64decode(footer["content_base64"]).decode("utf-8")
    assert "Oznámenie právneho pracovného postupu" in header_svg
    assert "Právne dokumenty s podporou AI" in footer_svg
    assert "Professional legal workflow notification" not in header_svg


def test_smtp_sender_attaches_inline_assets_as_related(monkeypatch: Any) -> None:
    delivered: list[Any] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def starttls(self) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            return None

        def send_message(self, message: Any) -> None:
            delivered.append(message)

    monkeypatch.setattr("app.services.email.smtplib.SMTP", FakeSMTP)
    email = build_welcome_email(full_name="Test User")
    service = EmailNotificationService(
        sender="no-reply@jurisdigta.eu",
        transport="smtp",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
        smtp_use_tls=False,
    )

    service.send_email(
        recipient="recipient@example.com",
        subject=email.subject,
        body=email.text_body,
        html_body=email.html_body,
        attachments=email.inline_attachments,
    )

    assert len(delivered) == 1
    raw = delivered[0].as_string()
    assert "multipart/related" in raw
    assert f"Content-ID: <{HEADER_CID}>" in raw
    assert f"Content-ID: <{FOOTER_CID}>" in raw
    assert f"cid:{HEADER_CID}" in raw
    assert "image/svg+xml" in raw
