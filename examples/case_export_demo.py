"""Minimal runnable demo for exporting a synthetic paid case as a ZIP."""

from __future__ import annotations

import os
from pathlib import Path
import sys


repo_root = Path(__file__).resolve().parents[1]
api_root = repo_root / "api" / "aijuristiction-api"
src_root = repo_root / "src"
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

run_root = repo_root / "runs" / "case-export-demo"
os.environ["DB_OPTION"] = "local"
os.environ["STORAGE_OPTION"] = "local"
os.environ["DB_LOCAL"] = str(run_root / "api.sqlite3")
os.environ["STORE_LOCAL"] = str(run_root / "storage")
os.environ.setdefault("LLM_PROVIDER", "mock")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


HEADERS = {"x-api-key": "aijuris"}


def main() -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)

    user = client.post(
        "/v1/users/sign-up",
        headers=HEADERS,
        json={
            "phone_number": "+421900471000",
            "email": "case-export-demo@example.test",
            "password": "secret",
        },
    )
    if user.status_code not in {201, 409}:
        raise SystemExit(f"Could not create demo user: {user.status_code} {user.text}")

    if user.status_code == 201:
        user_id = str(user.json()["user_id"])
    else:
        signed_in = client.post(
            "/v1/users/sign-in",
            headers=HEADERS,
            json={"email": "case-export-demo@example.test", "password": "secret"},
        )
        signed_in.raise_for_status()
        user_id = str(signed_in.json()["user_id"])

    checkout = client.post(
        f"/v1/users/{user_id}/subscriptions",
        headers=HEADERS,
        json={"plan_code": "case"},
    )
    checkout.raise_for_status()
    subscription_id = str(checkout.json()["subscription_id"])
    paid = client.patch(
        f"/v1/users/subscriptions/{subscription_id}",
        headers=HEADERS,
        json={"status": "paid"},
    )
    paid.raise_for_status()

    created = client.post(
        "/v1/cases",
        headers=HEADERS,
        json={"user_id": user_id, "title": "Demo golden export case"},
    )
    created.raise_for_status()
    case_id = str(created.json()["case_id"])

    from aijurisdictionagents.api_db import ApiDatabaseStore  # noqa: PLC0415

    store = ApiDatabaseStore.from_env()
    store.initialize()
    store.add_case_message(
        case_id=case_id,
        role="user",
        content="Priprav jednoduché potvrdenie o zaplatení na test exportu.",
    )
    store.add_case_document(
        case_id=case_id,
        kind="generated_document",
        version=1,
        original_filename="potvrdenie.txt",
        payload="Potvrdenie\n\nSuma: 1000 EUR\nPodpis: __________".encode("utf-8"),
        uploaded_by_user_id=user_id,
    )

    exported = client.get(f"/v1/cases/{case_id}/export?user_id={user_id}", headers=HEADERS)
    exported.raise_for_status()
    output = run_root / "case-export.zip"
    output.write_bytes(exported.content)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
