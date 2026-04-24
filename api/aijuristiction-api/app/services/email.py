from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("aijuristiction-api.email")

DEFAULT_EMAIL_SENDER = "no-reply@jurisdigta.eu"
DEFAULT_SMTP_HOST = "mail.webhourse.sk"
DEFAULT_SMTP_PORT = 587


@dataclass(frozen=True)
class EmailNotificationService:
    sender: str
    transport: str
    smtp_host: str
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool

    @classmethod
    def from_env(cls) -> "EmailNotificationService":
        sender = os.getenv("EMAIL_SENDER", DEFAULT_EMAIL_SENDER).strip() or DEFAULT_EMAIL_SENDER
        return cls(
            sender=sender,
            transport=os.getenv("EMAIL_TRANSPORT", "log").strip().lower() or "log",
            smtp_host=os.getenv("EMAIL_SMTP_HOST", DEFAULT_SMTP_HOST).strip() or DEFAULT_SMTP_HOST,
            smtp_port=int(os.getenv("EMAIL_SMTP_PORT", str(DEFAULT_SMTP_PORT))),
            smtp_username=_optional_env("EMAIL_SMTP_USERNAME") or sender,
            smtp_password=_optional_env("EMAIL_SMTP_PASSWORD"),
            smtp_use_tls=_env_bool("EMAIL_SMTP_USE_TLS", default=True),
        )

    def send_email(self, *, recipient: str, subject: str, body: str) -> None:
        if self.transport == "smtp":
            self._send_via_smtp(recipient=recipient, subject=subject, body=body)
            return
        logger.info(
            "Email notification (%s): from=%s to=%s subject=%s body=%s",
            self.transport,
            self.sender,
            recipient,
            subject,
            body,
        )

    def _send_via_smtp(self, *, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
            if self.smtp_use_tls:
                smtp.starttls()
            if self.smtp_username and self.smtp_password:
                smtp.login(self.smtp_username, self.smtp_password)
            smtp.send_message(message)


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}
