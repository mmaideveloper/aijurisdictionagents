"""Minimal runnable demo for API health/version and email-backed user flow.

Run API first:
    uvicorn app.main:app --reload --port 8080 --app-dir api/aijuristiction-api

By default, API uses LLM_PROVIDER=azurefoundry.
The default local SQLite metadata database is stored at `./databases/api.sqlite3`.
For local smoke testing without Azure credentials:
    LLM_PROVIDER=mock uvicorn app.main:app --reload --port 8080 --app-dir api/aijuristiction-api

Then:
    python examples/minimal_demo.py
"""

from __future__ import annotations

import json
import sqlite3
import time
from urllib import request

API_BASE = "http://localhost:8080"
API_KEY = "aijuris"


def get_json(url: str) -> dict:
    with request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))




def count_queued_emails(db_path: str = "./databases/email.sqlite3") -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM email_outbox WHERE status = 'pending'").fetchone()
    return int(row[0]) if row else 0


def post_json(path: str, payload: dict) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{API_BASE}{path}",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    health = get_json(f"{API_BASE}/health")
    version = get_json(f"{API_BASE}/version")
    print("health:", health)
    print("version:", version)
    print("api_version:", version.get("api_version"))
    print("core_version:", version.get("core_version"))

    suffix = int(time.time())
    user = post_json(
        "/v1/users/sign-up",
        {
            "phone_number": f"+421900{suffix % 1_000_000:06d}",
            "email": f"minimal-demo-{suffix}@example.com",
            "password": "demo-secret",
            "first_name": "Minimal",
            "last_name": "Demo",
        },
    )
    print("signed_up_user:", user)
    print("pending_email_notifications:", count_queued_emails())
    print("Note: scheduler sends queued emails once per minute (max 2 attempts per message).")
