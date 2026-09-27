"""Used only as a captured child process by E2E; never log the returned synthetic OTP."""

from pathlib import Path
import re
from dotenv import dotenv_values
import psycopg

cfg = dotenv_values(Path(__file__).resolve().parents[2] / ".env-laws-test")
if cfg.get("LAWS_TEST_ENVIRONMENT") != "development":
    raise SystemExit("Synthetic OTP reader is local-development only")
with psycopg.connect(cfg["LAWS_TEST_IDENTITY_DATABASE_URL"]) as conn:
    row = conn.execute(
        "SELECT body FROM email_outbox WHERE recipient='laws-tests-840@example.invalid' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise SystemExit("Synthetic OTP not yet queued")
    found = re.search(r"code is:\s*(\d+)", row[0])
    if not found:
        raise SystemExit("Synthetic OTP format not recognized")
    print(found.group(1))
