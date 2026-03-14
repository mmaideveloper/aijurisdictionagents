from __future__ import annotations

import logging

from app.services.email_scheduler import EmailScheduler

from aijurisdictionagents.api_db import User, UserSubscription

logger = logging.getLogger("aijuristiction-api.users.notifications")


def queue_registration_email(*, scheduler: EmailScheduler, user: User) -> None:
    _queue_email_safely(
        scheduler=scheduler,
        recipient=user.email,
        subject="Welcome to AI Jurisdiction",
        body=(
            f"Hello {user.full_name},\n\n"
            "your account was created successfully. "
            "You can now sign in and start working with your legal assistant.\n"
        ),
        context="registration",
        metadata={"event": "registration", "user_id": user.user_id},
    )


def queue_subscription_change_email(*, scheduler: EmailScheduler, user: User, item: UserSubscription) -> None:
    _queue_email_safely(
        scheduler=scheduler,
        recipient=user.email,
        subject="Subscription change requested",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your subscription change request to plan '{item.plan_code}' was recorded and is now pending.\n"
        ),
        context="subscription_change",
        metadata={"event": "subscription_change", "subscription_id": item.subscription_id},
    )


def queue_subscription_status_email(*, scheduler: EmailScheduler, user: User, item: UserSubscription) -> None:
    if item.status == "paid":
        _queue_email_safely(
            scheduler=scheduler,
            recipient=user.email,
            subject="Payment confirmed",
            body=(
                f"Hello {user.full_name},\n\n"
                f"payment for your '{item.plan_code}' subscription was confirmed and your plan is active.\n"
            ),
            context="subscription_payment",
            metadata={"event": "subscription_payment", "subscription_id": item.subscription_id},
        )
        return
    if item.status == "failed":
        _queue_email_safely(
            scheduler=scheduler,
            recipient=user.email,
            subject="Payment failed",
            body=(
                f"Hello {user.full_name},\n\n"
                f"payment for your '{item.plan_code}' subscription failed. Please retry your payment method.\n"
            ),
            context="subscription_payment_failed",
            metadata={"event": "subscription_payment_failed", "subscription_id": item.subscription_id},
        )
        return

    _queue_email_safely(
        scheduler=scheduler,
        recipient=user.email,
        subject="Subscription status changed",
        body=(
            f"Hello {user.full_name},\n\n"
            f"your subscription '{item.plan_code}' status changed to '{item.status}'.\n"
        ),
        context="subscription_status",
        metadata={"event": "subscription_status", "subscription_id": item.subscription_id, "status": item.status},
    )


def _queue_email_safely(
    *,
    scheduler: EmailScheduler,
    recipient: str,
    subject: str,
    body: str,
    metadata: dict[str, str],
    context: str,
) -> None:
    try:
        scheduler.enqueue(recipient=recipient, subject=subject, body=body, metadata=metadata)
    except Exception:  # pragma: no cover
        logger.exception("Unable to enqueue email notification (%s)", context)
