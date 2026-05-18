from __future__ import annotations

import logging
import os
import base64
from uuid import uuid4
from typing import Any

from app.services.email import EmailNotificationService
from app.services.email_queue import EmailQueueStore
from app.services.email_templates import ensure_branded_email_metadata

logger = logging.getLogger("aijuristiction-api.email.scheduler")


class EmailScheduler:
    def __init__(self, *, queue_store: EmailQueueStore, email_service: EmailNotificationService) -> None:
        self.queue_store = queue_store
        self.email_service = email_service

    @classmethod
    def from_env(cls) -> "EmailScheduler":
        queue_store = EmailQueueStore.from_env()
        queue_store.initialize()
        return cls(queue_store=queue_store, email_service=EmailNotificationService.from_env())

    def enqueue(self, *, recipient: str, subject: str, body: str, metadata: dict[str, Any]) -> str:
        email_id = str(uuid4())
        self.queue_store.enqueue_email(
            email_id=email_id,
            recipient=recipient,
            subject=subject,
            body=body,
            metadata=metadata,
        )
        return email_id

    def run_once(self, *, limit: int = 50) -> int:
        queued = self.queue_store.claim_pending(limit=limit)
        processed = 0
        for item in queued:
            try:
                metadata = ensure_branded_email_metadata(
                    subject=item.subject,
                    body=item.body,
                    metadata=item.metadata,
                )
                self.email_service.send_email(
                    recipient=item.recipient,
                    subject=item.subject,
                    body=item.body,
                    html_body=_metadata_str(metadata, "html_body"),
                    attachments=_decode_attachments(metadata.get("attachments")),
                )
                self.queue_store.mark_sent(email_id=item.email_id)
                processed += 1
            except Exception as exc:  # pragma: no cover - defensive scheduling path
                logger.exception("Unable to send queued email_id=%s", item.email_id)
                self.queue_store.mark_failed_attempt(email_id=item.email_id, error_message=str(exc))
        return processed


def scheduler_enabled() -> bool:
    value = os.getenv("EMAIL_SCHEDULER_ENABLED", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def scheduler_interval_seconds() -> int:
    raw = os.getenv("EMAIL_SCHEDULER_INTERVAL_SECONDS", "60").strip()
    try:
        value = int(raw)
    except ValueError:
        return 60
    return max(value, 5)


def _metadata_str(metadata: object, key: str) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    return str(value) if isinstance(value, str) and value.strip() else None


def _decode_attachments(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    decoded: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = item.get("content_base64")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            payload = base64.b64decode(content.encode("utf-8"), validate=True)
        except Exception:
            continue
        decoded_item: dict[str, Any] = {
            "filename": str(item.get("filename") or "attachment.bin"),
            "mime_type": str(item.get("mime_type") or "application/octet-stream"),
            "content": payload,
        }
        content_id = _optional_metadata_str(item, "content_id")
        if content_id is not None:
            decoded_item["content_id"] = content_id
        disposition = _optional_metadata_str(item, "disposition")
        if disposition is not None:
            decoded_item["disposition"] = disposition
        decoded.append(decoded_item)
    return decoded


def _optional_metadata_str(item: dict[Any, Any], key: str) -> str | None:
    value = item.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
