"""Release migration with a database backup; secret values never enter process arguments."""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg
from dotenv import dotenv_values

from laws_tests.db import migrate

sha = sys.argv[1]
if len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
    raise SystemExit("Invalid SHA")
profile = dotenv_values("/run/secrets/migration.env")
url = profile.get("LAWS_TEST_MIGRATION_DATABASE_URL")
if not url or url == "unknown-variable":
    raise SystemExit("Missing LAWS_TEST_MIGRATION_DATABASE_URL")
uri = urlsplit(url)
if uri.path != "/laws-tests":
    raise SystemExit("Unexpected migration database")
runtime = dotenv_values("/run/secrets/.env-laws-test")
app_uri = urlsplit(runtime["LAWS_TEST_DATABASE_URL"])
identity_uri = urlsplit(runtime["LAWS_TEST_IDENTITY_DATABASE_URL"])
laws_uri = urlsplit(runtime.get("LAWS_TEST_LAWS_DATABASE_URL") or "")
if laws_uri.username != "laws_tests_reader" or (laws_uri.hostname, laws_uri.port or 5432) != (
    uri.hostname,
    uri.port or 5432,
):
    raise SystemExit("Dedicated same-server public law reader profile required")
if app_uri.username != "laws_tests_app":
    raise SystemExit("Unexpected application role")
if identity_uri.username != "laws_tests_identity" or identity_uri.hostname != uri.hostname:
    raise SystemExit("Dedicated same-server identity role required")
admin_url = uri._replace(path="/postgres").geturl()
with psycopg.connect(admin_url, autocommit=True) as conn:
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='laws_tests_reader'").fetchone():
        conn.execute(
            psycopg.sql.SQL("CREATE ROLE laws_tests_reader LOGIN PASSWORD {}").format(
                psycopg.sql.Literal(unquote(laws_uri.password or ""))
            )
        )
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='laws_tests_identity'").fetchone():
        conn.execute(
            psycopg.sql.SQL("CREATE ROLE laws_tests_identity LOGIN PASSWORD {}").format(
                psycopg.sql.Literal(unquote(identity_uri.password or ""))
            )
        )
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='laws_tests_app'").fetchone():
        conn.execute(
            psycopg.sql.SQL("CREATE ROLE laws_tests_app LOGIN PASSWORD {}").format(
                psycopg.sql.Literal(unquote(app_uri.password or ""))
            )
        )
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname='laws-tests'").fetchone():
        conn.execute('CREATE DATABASE "laws-tests"')
env = {**os.environ, "PGPASSWORD": unquote(uri.password or "")}
backup = Path("/backups") / (sha + ".dump")
if not backup.exists():
    pending_backup = backup.with_suffix(".partial")
    result = subprocess.run(
        [
            "pg_dump",
            "-h",
            uri.hostname or "",
            "-p",
            str(uri.port or 5432),
            "-U",
            unquote(uri.username or ""),
            "-d",
            "laws-tests",
            "-Fc",
            "-f",
            str(pending_backup),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,  # Handle return codes below without exposing captured secrets.
    )
    if result.returncode:
        pending_backup.unlink(missing_ok=True)
        raise SystemExit("Database backup failed; details withheld to protect configuration")
    pending_backup.replace(backup)
    backup.chmod(0o600)
migrate(url, Path("/app"))
# Import the explicitly authorized preview only into an empty course bank. Never downgrade
# or overwrite a later reviewed import, and never mark preview content legally reviewed.
with psycopg.connect(url) as conn:
    conn.execute("SELECT pg_advisory_xact_lock(840002)")
    if not conn.execute("SELECT 1 FROM test_definitions LIMIT 1").fetchone():
        conn.execute(Path("/app/databases/laws-tests/seeds/preview.sql").read_text(encoding="utf-8"))
with psycopg.connect(url) as conn:
    conn.execute('GRANT CONNECT ON DATABASE "laws-tests" TO laws_tests_app')
    conn.execute("GRANT USAGE ON SCHEMA public TO laws_tests_app")
    conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM laws_tests_app")
    conn.execute("GRANT SELECT ON test_definitions,questions,subquestions TO laws_tests_app")
    conn.execute(
        "GRANT SELECT,INSERT,UPDATE,DELETE ON login_requests,web_sessions,test_sessions,attempts TO laws_tests_app"
    )
identity_admin = uri._replace(path=identity_uri.path).geturl()
with psycopg.connect(identity_admin) as conn:
    conn.execute(
        psycopg.sql.SQL("GRANT CONNECT ON DATABASE {} TO laws_tests_identity").format(
            psycopg.sql.Identifier(unquote(identity_uri.path.lstrip("/")))
        )
    )
    conn.execute("GRANT USAGE ON SCHEMA public TO laws_tests_identity")
    conn.execute("GRANT SELECT(user_id,is_enabled) ON users TO laws_tests_identity")
    conn.execute(
        "GRANT SELECT(user_id,device_id,token_hash,expires_at), UPDATE(last_used_at) ON device_auth_tokens TO laws_tests_identity"
    )
with psycopg.connect(uri._replace(path=laws_uri.path).geturl()) as conn:
    conn.execute(
        psycopg.sql.SQL("GRANT CONNECT ON DATABASE {} TO laws_tests_reader").format(
            psycopg.sql.Identifier(unquote(laws_uri.path.lstrip("/")))
        )
    )
    conn.execute("GRANT USAGE ON SCHEMA public TO laws_tests_reader")
    conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM laws_tests_reader")
    conn.execute(
        "GRANT SELECT ON law_documents,law_versions,law_metadata,law_provisions,source_artifacts TO laws_tests_reader"
    )
print("Recovery point created; laws-tests migrations and read-only source grants verified.")
