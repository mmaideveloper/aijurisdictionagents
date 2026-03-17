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
from urllib.error import HTTPError

API_BASE = "http://localhost:8080"
API_KEY = "aijuris"


def fetch_json(url: str, *, headers: dict[str, str] | None = None) -> tuple[dict, dict[str, str]]:
    req = request.Request(url, headers=headers or {}, method="GET")
    with request.urlopen(req, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8")), dict(response.headers.items())




def count_queued_emails(db_path: str = "./databases/email.sqlite3") -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM email_outbox WHERE status = 'pending'").fetchone()
    return int(row[0]) if row else 0


def post_json(
    path: str,
    payload: dict,
    *,
    request_id: str,
    correlation_id: str,
) -> tuple[dict, dict[str, str]]:
    raw = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{API_BASE}{path}",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "x-request-id": request_id,
            "x-correlation-id": correlation_id,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8")), dict(response.headers.items())


if __name__ == "__main__":
    probe_request_id = f"minimal-probe-{int(time.time())}"
    probe_headers = {
        "x-request-id": probe_request_id,
        "x-correlation-id": probe_request_id,
    }
    health, health_headers = fetch_json(f"{API_BASE}/health", headers=probe_headers)
    version, version_headers = fetch_json(f"{API_BASE}/version", headers=probe_headers)
    print("health:", health)
    print("version:", version)
    print("api_version:", version.get("api_version"))
    print("core_version:", version.get("core_version"))
    print("health_request_id:", health_headers.get("x-request-id"))
    print("health_correlation_id:", health_headers.get("x-correlation-id"))
    print("version_request_id:", version_headers.get("x-request-id"))
    print("version_correlation_id:", version_headers.get("x-correlation-id"))

    suffix = int(time.time())
    signup_request_id = f"minimal-signup-{suffix}"
    try:
        user, user_headers = post_json(
            "/v1/users/sign-up",
            {
                "phone_number": f"+421900{suffix % 1_000_000:06d}",
                "email": f"minimal-demo-{suffix}@example.com",
                "password": "demo-secret",
                "first_name": "Minimal",
                "last_name": "Demo",
            },
            request_id=signup_request_id,
            correlation_id=signup_request_id,
        )
        print("signed_up_user:", user)
        print("signup_request_id:", user_headers.get("x-request-id"))
        print("signup_correlation_id:", user_headers.get("x-correlation-id"))
        print("pending_email_notifications:", count_queued_emails())
        print("Note: scheduler sends queued emails once per minute (max 2 attempts per message).")
        print("Use the request/correlation IDs above to query ACA logs or Application Insights.")
    except HTTPError as exc:
        print("sign_up_status:", exc.code)
        print("sign_up_body:", exc.read().decode("utf-8"))
        raise
