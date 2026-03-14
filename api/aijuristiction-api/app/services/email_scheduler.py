from __future__ import annotations

import logging
import os
from uuid import uuid4

from app.services.email import EmailNotificationService
from app.services.email_queue import EmailQueueStore

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

    def enqueue(self, *, recipient: str, subject: str, body: str, metadata: dict[str, str]) -> str:
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
                self.email_service.send_email(
                    recipient=item.recipient,
                    subject=item.subject,
                    body=item.body,
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
