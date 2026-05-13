from __future__ import annotations

from dataclasses import dataclass
import base64
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Any, cast

logger = logging.getLogger("aijuristiction-api.email")

DEFAULT_EMAIL_SENDER = "no-reply@jurisdigta.eu"
DEFAULT_SMTP_HOST = "mail.webhouse.sk"
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

    def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        prepared_attachments = attachments or []
        if self.transport == "smtp":
            self._send_via_smtp(
                recipient=recipient,
                subject=subject,
                body=body,
                html_body=html_body,
                attachments=prepared_attachments,
            )
            return
        logger.info(
            "Email notification (%s): from=%s to=%s subject=%s body_chars=%s html=%s attachments=%s",
            self.transport,
            self.sender,
            recipient,
            subject,
            len(body),
            bool(html_body),
            len(prepared_attachments),
        )

    def _send_via_smtp(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None,
        attachments: list[dict[str, Any]],
    ) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        html_part: EmailMessage | None = None
        if html_body:
            message.add_alternative(html_body, subtype="html")
            html_part = cast(EmailMessage | None, message.get_body(preferencelist=("html",)))
        for attachment in attachments:
            _add_attachment(message=message, html_part=html_part, attachment=attachment)

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
            if self.smtp_use_tls:
                smtp.starttls()
            if self.smtp_username and self.smtp_password:
                smtp.login(self.smtp_username, self.smtp_password)
            smtp.send_message(message)


def _add_attachment(
    *,
    message: EmailMessage,
    html_part: EmailMessage | None,
    attachment: dict[str, Any],
) -> None:
    filename = str(attachment.get("filename") or "attachment.bin")
    mime_type = str(attachment.get("mime_type") or "application/octet-stream")
    payload = _attachment_payload(attachment)
    if payload is None:
        return
    maintype, subtype = _split_mime_type(mime_type)
    content_id = _attachment_content_id(attachment)
    if html_part is not None and content_id:
        html_part.add_related(
            payload,
            maintype=maintype,
            subtype=subtype,
            cid=_format_content_id(content_id),
            filename=filename,
        )
        return
    message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)


def _attachment_payload(attachment: dict[str, Any]) -> bytes | None:
    payload = attachment.get("content")
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    encoded = attachment.get("content_base64")
    if isinstance(encoded, str) and encoded.strip():
        try:
            return base64.b64decode(encoded.encode("utf-8"), validate=True)
        except Exception:
            return None
    return None


def _split_mime_type(mime_type: str) -> tuple[str, str]:
    maintype, separator, subtype = mime_type.partition("/")
    if not separator:
        return "application", "octet-stream"
    return maintype or "application", subtype or "octet-stream"


def _attachment_content_id(attachment: dict[str, Any]) -> str | None:
    raw = attachment.get("content_id")
    if not isinstance(raw, str):
        return None
    content_id = raw.strip().strip("<>")
    return content_id or None


def _format_content_id(content_id: str) -> str:
    return f"<{content_id.strip().strip('<>')}>"


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
