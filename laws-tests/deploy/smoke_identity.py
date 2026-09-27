"""Restricted deployment-only synthetic identity. JSON stdout must be captured, never logged."""

import json
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from aijurisdictionagents.api_db import ApiDatabaseStore
from dotenv import dotenv_values

from laws_tests.config import Settings
from laws_tests.db import connect

cfg = Settings.load()
admin = dotenv_values("/run/secrets/migration.env")["LAWS_TEST_MIGRATION_DATABASE_URL"]
identity_url = urlsplit(admin)._replace(path=urlsplit(cfg.identity_database_url).path).geturl()
if sys.argv[1] == "create":
    store = ApiDatabaseStore(
        db_path=Path("unused"),
        blob_root=Path("/tmp/laws-tests-smoke"),
        db_option="postgres",
        db_cloud=identity_url,
    )
    email = f"laws-tests-smoke-{uuid4()}@example.invalid"
    user = store.create_user(
        email=email, password=secrets.token_urlsafe(40), full_name="Synthetic deployment smoke"
    )
    device_id = str(uuid4())
    token = store.issue_device_auth_token(
        user_id=user.user_id, device_id=device_id, expires_in_days=1
    )
    print(
        json.dumps(
            {"user_id": user.user_id, "email": email, "device_id": device_id, "device_token": token}
        )
    )
elif sys.argv[1] == "cleanup":
    record = json.load(sys.stdin)
    if not record["email"].startswith("laws-tests-smoke-") or not record["email"].endswith(
        "@example.invalid"
    ):
        raise SystemExit("Refusing non-synthetic cleanup")
    with connect(identity_url) as conn:
        user = conn.execute(
            "SELECT user_id FROM users WHERE user_id=%s AND email=%s",
            (record["user_id"], record["email"]),
        ).fetchone()
        if user:
            with connect(cfg.database_url) as tests:
                tests.execute("DELETE FROM test_sessions WHERE user_id=%s", (record["user_id"],))
                tests.execute("DELETE FROM web_sessions WHERE user_id=%s", (record["user_id"],))
                tests.execute("DELETE FROM login_requests WHERE user_id=%s", (record["user_id"],))
            conn.execute(
                "DELETE FROM users WHERE user_id=%s AND email=%s",
                (record["user_id"], record["email"]),
            )
    print("Synthetic smoke records removed.")
else:
    raise SystemExit("Expected create or cleanup")
