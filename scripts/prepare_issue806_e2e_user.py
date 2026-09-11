"""Seed a synthetic paid user; keep transient login material outside evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import secrets
import uuid

import psycopg

from aijurisdictionagents.api_db import ApiDatabaseStore

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "runs/storage/issue806-user.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--otp", action="store_true")
    parser.add_argument("--allow-retest", action="store_true", help="Give this synthetic user a multi-case plan")
    args = parser.parse_args()
    if args.otp:
        values = json.loads(PRIVATE.read_text())
        with psycopg.connect(host="127.0.0.1", port=5432, dbname="issue806_reporting",
                             user="postgres", password="postgres") as db:
            row = db.execute("SELECT body FROM email_outbox WHERE recipient=%s ORDER BY created_at DESC LIMIT 1",
                             (values["email"],)).fetchone()
            if not row or not (code := re.search(r"login code is: (\d+)", row[0])):
                raise RuntimeError("Synthetic user's login code is not in the local PostgreSQL outbox")
            values["otp"] = code[1]
        PRIVATE.write_text(json.dumps(values), encoding="utf-8")
        print("Synthetic OTP ready for browser entry; value redacted.")
        return
    store = ApiDatabaseStore(db_path=ROOT / "runs/storage/api/sqlite/unused.sqlite3",
                             blob_root=ROOT / "runs/storage/api/files", db_option="postgres",
                             db_cloud="postgresql://postgres:postgres@127.0.0.1:5432/issue806_reporting")
    if args.allow_retest:
        user_id = json.loads(PRIVATE.read_text())["userId"]
        plan = store.request_subscription_change(user_id=user_id, plan_code="basic")
        store.update_subscription_status(subscription_id=plan.subscription_id, status="paid")
        print("Synthetic account has a paid multi-case plan for retesting.")
        return
    password = secrets.token_urlsafe(24)
    run_id = "issue806-user-" + uuid.uuid4().hex[:10]
    user = store.create_user(email=run_id + "@example.invalid", password=password,
                             full_name="Synthetic Reporting User")
    plan = store.request_subscription_change(user_id=user.user_id, plan_code="case")
    store.update_subscription_status(subscription_id=plan.subscription_id, status="paid")
    PRIVATE.write_text(json.dumps({"userId": user.user_id, "email": user.email,
                                   "password": password, "runId": run_id}), encoding="utf-8")
    print("Synthetic paid user prepared. Login material is transient and redacted.")


if __name__ == "__main__":
    main()
