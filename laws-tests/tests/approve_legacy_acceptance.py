"""Explicit synthetic grants for the existing real reader/account acceptance suite."""

import json
from pathlib import Path
from uuid import uuid4

from aijurisdictionagents.api_db import ApiDatabaseStore

from laws_tests.config import Settings
from laws_tests.db import connect

root = Path(__file__).resolve().parents[2]
cfg = Settings.load()
assert cfg.environment == "development"
account = json.loads((root / "runs/issue840/synthetic-account.json").read_text(encoding="utf-8"))
assert account["email"] == "laws-tests-840@example.invalid"
reader = json.loads((root / "runs/issue840/reader-fixture.json").read_text(encoding="utf-8"))
with connect(cfg.database_url) as conn:
    conn.execute(
        "INSERT INTO test_users(user_id,approved) VALUES(%s,true) ON CONFLICT(user_id) DO UPDATE SET approved=true",
        (account["user_id"],),
    )
    for bank in ("firearms-sk-2026", reader["run_id"], reader["run_id"] + "-preview"):
        conn.execute(
            "INSERT INTO bank_access(user_id,test_id,status) VALUES(%s,%s,'approved') ON CONFLICT(user_id,test_id) DO UPDATE SET status='approved'",
            (account["user_id"], bank),
        )
store = ApiDatabaseStore(
    db_path=Path("unused"),
    blob_root=root / "runs/issue840/blobs",
    db_option="postgres",
    db_cloud=cfg.identity_database_url,
)
device = str(uuid4())
token = store.issue_device_auth_token(
    user_id=account["user_id"], device_id=device, expires_in_days=1
)
(root / "runs/issue840/browser-authorization.json").write_text(
    json.dumps({"user_id": account["user_id"], "device_id": device, "device_token": token}),
    encoding="utf-8",
)
print("Explicit synthetic reader grants prepared; credentials withheld.")
