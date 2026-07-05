from __future__ import annotations

import os

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.api_db.e2e_test_users import provision_e2e_test_users


def main() -> int:
    password = os.getenv("JURISDIGTA_E2E_TEST_USER_PASSWORD", "").strip()
    store = ApiDatabaseStore.from_env()
    store.initialize()
    users = provision_e2e_test_users(store=store, password=password)
    for user in users:
        action = "created" if user.created else "updated"
        print(f"{action}: {user.email} plan={user.plan_code} user_id={user.user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
