"""Minimal demo for the subscription model introduced in task #86.

Run:
    python examples/subscription_minimal_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from aijurisdictionagents.api_db import ApiDatabaseStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="subscription-demo-") as tmp:
        root = Path(tmp)
        store = ApiDatabaseStore(
            db_path=root / "api.sqlite3",
            blob_root=root / "blob",
        )
        store.initialize()

        user = store.create_user(
            phone_number="+421900123456",
            email="demo@example.com",
            password="demo-secret",
            first_name="Demo",
            last_name="User",
        )

        plans = store.list_subscription_plans()
        print("Available plans:")
        for plan in plans:
            print(
                f"- {plan.plan_code}: {plan.display_name}, {plan.subscription_type}, "
                f"€{plan.price_eur}, max_cases={plan.max_cases}, case_ttl_days={plan.case_ttl_days}"
            )

        request = store.request_subscription_change(user_id=user.user_id, plan_code="basic")
        print(f"\nRequested plan change: {request.plan_code} ({request.status})")

        paid = store.update_subscription_status(
            subscription_id=request.subscription_id,
            status="paid",
        )
        print(f"Activated: status={paid.status}, starts_at={paid.starts_at}, ends_at={paid.ends_at}")


if __name__ == "__main__":
    main()
