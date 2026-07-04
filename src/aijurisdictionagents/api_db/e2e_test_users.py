from __future__ import annotations

from dataclasses import dataclass

from .store import ApiDatabaseStore, User

E2E_TEST_FREE_EMAIL = "mcp-claude-test-free@jurisdigta.eu"
E2E_TEST_PAID_EMAIL = "mcp-claude-test-paid@jurisdigta.eu"
E2E_TEST_USER_EMAILS = frozenset({E2E_TEST_FREE_EMAIL, E2E_TEST_PAID_EMAIL})


@dataclass(frozen=True)
class ProvisionedE2ETestUser:
    email: str
    user_id: str
    plan_code: str
    created: bool


def provision_e2e_test_users(*, store: ApiDatabaseStore, password: str) -> list[ProvisionedE2ETestUser]:
    normalized_password = password.strip()
    if not normalized_password or normalized_password == "unknown-variable":
        raise ValueError("A non-placeholder E2E test user password is required")
    free_user, free_created = _ensure_user(
        store=store,
        email=E2E_TEST_FREE_EMAIL,
        password=normalized_password,
        full_name="JurisDigta Claude E2E Free",
    )
    paid_user, paid_created = _ensure_user(
        store=store,
        email=E2E_TEST_PAID_EMAIL,
        password=normalized_password,
        full_name="JurisDigta Claude E2E Paid",
    )
    _ensure_free_plan_only(store=store, user=free_user)
    _ensure_paid_case_plan(store=store, user=paid_user)
    return [
        ProvisionedE2ETestUser(
            email=free_user.email,
            user_id=free_user.user_id,
            plan_code=store.get_effective_subscription_plan(user_id=free_user.user_id).plan_code,
            created=free_created,
        ),
        ProvisionedE2ETestUser(
            email=paid_user.email,
            user_id=paid_user.user_id,
            plan_code=store.get_effective_subscription_plan(user_id=paid_user.user_id).plan_code,
            created=paid_created,
        ),
    ]


def _ensure_user(
    *,
    store: ApiDatabaseStore,
    email: str,
    password: str,
    full_name: str,
) -> tuple[User, bool]:
    user = store.find_user_by_email(email=email)
    if user is None:
        return store.create_user(email=email, password=password, full_name=full_name), True
    updated = store.update_user(
        user_id=user.user_id,
        phone_number=user.phone_number,
        first_name=user.first_name,
        last_name=user.last_name,
        address=user.address,
        city=user.city,
        country=user.country,
        zip_code=user.zip_code,
        tax_number=user.tax_number,
        identity_card_number=user.identity_card_number,
        date_of_birth=user.date_of_birth,
        social_security_number=user.social_security_number,
        password=password,
    )
    return updated, False


def _ensure_free_plan_only(*, store: ApiDatabaseStore, user: User) -> None:
    for subscription in store.list_user_subscriptions(user_id=user.user_id):
        if subscription.plan_code != "free" and subscription.status in {"pending", "paying", "paid"}:
            store.update_subscription_status(
                subscription_id=subscription.subscription_id,
                status="canceled",
            )


def _ensure_paid_case_plan(*, store: ApiDatabaseStore, user: User) -> None:
    for subscription in store.list_user_subscriptions(user_id=user.user_id):
        if subscription.plan_code == "case" and subscription.status == "paid":
            return
    subscription = store.request_subscription_change(user_id=user.user_id, plan_code="case")
    store.update_subscription_status(subscription_id=subscription.subscription_id, status="paid")
