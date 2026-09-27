"""Remove only the isolated synthetic acceptance account; never log credentials."""

import json
from pathlib import Path

from laws_tests.config import Settings
from laws_tests.db import connect

root = Path(__file__).resolve().parents[2]
record_path = root / "runs/issue840/synthetic-account.json"
if record_path.exists():
    cfg = Settings.load()
    if cfg.environment != "development":
        raise SystemExit("Local development cleanup only")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record["email"] != "laws-tests-840@example.invalid":
        raise SystemExit("Refusing non-synthetic cleanup")
    with connect(cfg.database_url) as conn:
        for table in ("test_sessions", "web_sessions", "login_requests"):
            conn.execute(f"DELETE FROM {table} WHERE user_id=%s", (record["user_id"],))
    with connect(cfg.identity_database_url) as conn:
        conn.execute("DELETE FROM email_outbox WHERE recipient=%s", (record["email"],))
        conn.execute(
            "DELETE FROM users WHERE user_id=%s AND email=%s", (record["user_id"], record["email"])
        )
    record_path.unlink()
    print("Synthetic acceptance identity and credentials removed.")
