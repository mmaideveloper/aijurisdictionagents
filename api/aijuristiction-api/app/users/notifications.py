from __future__ import annotations

import logging
from typing import Any

from app.services.email_scheduler import EmailScheduler
from app.services.email_templates import (
    build_subscription_change_email,
    build_subscription_status_email,
    build_welcome_email,
)

from aijurisdictionagents.api_db import User, UserSubscription

logger = logging.getLogger("aijuristiction-api.users.notifications")


def queue_registration_email(*, scheduler: EmailScheduler, user: User) -> None:
    email = build_welcome_email(full_name=user.full_name)
    _queue_email_safely(
        scheduler=scheduler,
        recipient=user.email,
        subject=email.subject,
        body=email.text_body,
        context="registration",
        metadata=email.metadata(event="registration", user_id=user.user_id),
    )


def queue_subscription_change_email(*, scheduler: EmailScheduler, user: User, item: UserSubscription) -> None:
    email = build_subscription_change_email(full_name=user.full_name, plan_code=item.plan_code)
    _queue_email_safely(
        scheduler=scheduler,
        recipient=user.email,
        subject=email.subject,
        body=email.text_body,
        context="subscription_change",
        metadata=email.metadata(event="subscription_change", subscription_id=item.subscription_id),
    )


def queue_subscription_status_email(*, scheduler: EmailScheduler, user: User, item: UserSubscription) -> None:
    email = build_subscription_status_email(
        full_name=user.full_name,
        plan_code=item.plan_code,
        status=item.status,
    )
    if item.status == "paid":
        event = "subscription_payment"
        context = "subscription_payment"
    elif item.status == "failed":
        event = "subscription_payment_failed"
        context = "subscription_payment_failed"
    else:
        event = "subscription_status"
        context = "subscription_status"
    metadata = email.metadata(event=event, subscription_id=item.subscription_id)
    if item.status not in {"paid", "failed"}:
        metadata["status"] = item.status
    _queue_email_safely(
        scheduler=scheduler,
        recipient=user.email,
        subject=email.subject,
        body=email.text_body,
        context=context,
        metadata=metadata,
    )


def _queue_email_safely(
    *,
    scheduler: EmailScheduler,
    recipient: str,
    subject: str,
    body: str,
    metadata: dict[str, Any],
    context: str,
) -> None:
    try:
        scheduler.enqueue(recipient=recipient, subject=subject, body=body, metadata=metadata)
    except Exception:  # pragma: no cover
        logger.exception("Unable to enqueue email notification (%s)", context)
