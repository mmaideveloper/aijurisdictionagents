import json
import os
from pathlib import Path
import re

from dotenv import load_dotenv
import httpx
import psycopg

root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env")
directory = root / "runs/issue661"
manifest = json.loads((directory / "input-manifest.json").read_text())
payload = {"email": manifest["email"], "password": os.environ["JURISDIGTA_E2E_TEST_USER_PASSWORD"],
           "device_id": manifest["runId"]}
with httpx.Client(base_url="http://127.0.0.1:8661", headers={"x-api-key": "aijuris"}, timeout=90) as client:
    response = client.post("/v1/users/sign-in", json=payload)
    if response.status_code == 428:
        with psycopg.connect("postgresql://postgres:synthetic661@127.0.0.1:55461/issue661_e2e_api") as conn:
            row = conn.execute("SELECT body FROM email_outbox WHERE recipient=%s ORDER BY created_at DESC LIMIT 1",
                               (manifest["email"],)).fetchone()
        match = re.search(r"login code is: (\d+)", row[0]) if row else None
        if not match:
            raise RuntimeError("Synthetic verification unavailable")
        payload["verification_code"] = match.group(1)
        response = client.post("/v1/users/sign-in", json=payload)
    assert response.status_code == 200, f"Sign-in HTTP {response.status_code}"
    user = response.json()
    assert user.get("device_auth_token")
    private = {"userId": user["user_id"], "email": user["email"], "name": user["full_name"],
               "deviceId": manifest["runId"], "deviceAuthToken": user["device_auth_token"], "role": user.get("role", "user")}
    (directory / "private-auth.json").write_text(json.dumps(private))
print("Synthetic sign-in passed; credentials redacted.")
