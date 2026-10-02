"""Authenticate the isolated synthetic user; never print passwords, OTPs or tokens."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
import httpx
import psycopg

from prepare_issue_746_e2e import API_DB

root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env")
directory = root / "runs/e2e/issue746"
manifest = json.loads((directory / "input-manifest.json").read_text(encoding="utf-8"))
device_id = manifest["runId"]
payload = {"email": manifest["email"], "password": os.environ["JURISDIGTA_E2E_TEST_USER_PASSWORD"],
           "device_id": device_id}
headers = {"x-api-key": os.getenv("API_KEY", "aijuris")}
with httpx.Client(base_url="http://127.0.0.1:8246", headers=headers, timeout=90) as client:
    response = client.post("/v1/users/sign-in", json=payload)
    if response.status_code == 428:
        with psycopg.connect(API_DB) as conn:
            row = conn.execute("SELECT body FROM email_outbox WHERE recipient=%s ORDER BY created_at DESC LIMIT 1",
                               (manifest["email"],)).fetchone()
        match = re.search(r"login code is: (\d+)", row[0]) if row else None
        if not match:
            raise RuntimeError("Synthetic login verification unavailable")
        payload["verification_code"] = match.group(1)
        response = client.post("/v1/users/sign-in", json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"Synthetic login failed: HTTP {response.status_code}")
    user = response.json()
    if not user.get("device_auth_token"):
        raise RuntimeError("Synthetic login did not issue a device token")
    private = {"userId": user["user_id"], "email": user["email"], "name": user["full_name"],
               "deviceId": device_id, "deviceAuthToken": user["device_auth_token"], "role": user.get("role", "user")}
    # This private bootstrap is not evidence; delete after acceptance.
    (directory / "private-auth.json").write_text(json.dumps(private), encoding="utf-8")
print("Synthetic user authenticated via real API; values redacted.")
