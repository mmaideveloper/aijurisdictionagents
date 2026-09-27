"""Create isolated synthetic local acceptance storage. Never prints credentials."""

from pathlib import Path
import secrets
import subprocess
import time
import json
from urllib.parse import quote

from dotenv import dotenv_values, set_key
import psycopg

ROOT = Path(__file__).resolve().parents[2]


def main():
    target = ROOT / ".env-laws-test"
    existing = dotenv_values(target) if target.exists() else {}
    from laws_tests.config import Settings

    Settings.load()  # Explicit dedicated development profile, no shared secret fallback.
    if existing.get("LAWS_TEST_ENVIRONMENT") != "development":
        raise SystemExit("Dedicated laws-tests development profile required")
    password = existing.get("LAWS_TEST_LOCAL_PASSWORD")
    if not password or password == "unknown-variable":
        raise SystemExit("Missing LAWS_TEST_LOCAL_PASSWORD; pull laws-tests-dev profile")
    storage = ROOT / "runs/storage/laws-tests/postgres/data"
    storage.mkdir(parents=True, exist_ok=True)
    envfile = ROOT / "runs/issue840/postgres.env"
    envfile.parent.mkdir(parents=True, exist_ok=True)
    envfile.write_text(f"POSTGRES_PASSWORD={password}\n", encoding="utf-8")
    try:
        names = subprocess.check_output(
            ["docker", "ps", "-a", "--format", "{{.Names}}"], text=True
        ).splitlines()
        if "laws-tests-840-postgres" not in names:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    "laws-tests-840-postgres",
                    "--env-file",
                    str(envfile),
                    "-p",
                    "127.0.0.1:5440:5432",
                    "-v",
                    f"{storage.as_posix()}:/var/lib/postgresql/data",
                    "pgvector/pgvector:pg16",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        else:
            info = json.loads(
                subprocess.check_output(["docker", "inspect", "laws-tests-840-postgres"], text=True)
            )[0]
            mounts = [m["Source"].replace("\\", "/").lower() for m in info["Mounts"]]
            if storage.as_posix().lower() not in mounts:
                raise SystemExit(
                    "Existing container belongs to another worktree; use an isolated runner"
                )
            subprocess.run(
                ["docker", "start", "laws-tests-840-postgres"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
    finally:
        envfile.unlink(missing_ok=True)
    # Reconcile this isolated container after an authoritative development-profile rotation.
    for _ in range(60):
        ready = subprocess.run(
            ["docker", "exec", "laws-tests-840-postgres", "pg_isready", "-U", "postgres"],
            capture_output=True,
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    sql = (
        psycopg.sql.SQL("ALTER USER postgres PASSWORD {}")
        .format(psycopg.sql.Literal(password))
        .as_string()
    )
    changed = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "laws-tests-840-postgres",
            "psql",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
        text=True,
        capture_output=True,
    )
    if changed.returncode:
        raise SystemExit("Local profile reconciliation failed (details redacted)")
    base = f"postgresql://postgres:{quote(password)}@127.0.0.1:5440/"
    for attempt in range(60):
        try:
            with psycopg.connect(base + "postgres", autocommit=True) as conn:
                for name in ("laws-tests", "laws_tests_identity_840"):
                    if not conn.execute(
                        "SELECT 1 FROM pg_database WHERE datname=%s", (name,)
                    ).fetchone():
                        conn.execute(
                            psycopg.sql.SQL("CREATE DATABASE {}").format(
                                psycopg.sql.Identifier(name)
                            )
                        )
            break
        except psycopg.OperationalError:
            time.sleep(1)
    else:
        raise SystemExit("Local PostgreSQL did not become ready")
    values = {
        "LAWS_TEST_DATABASE_URL": base + "laws-tests",
        "LAWS_TEST_IDENTITY_DATABASE_URL": base + "laws_tests_identity_840",
        "LAWS_TEST_PUBLIC_URL": "http://127.0.0.1:8410",
        "LAWS_TEST_AUTH_URL": "http://127.0.0.1:8412/tests-authorize",
        "LAWS_TEST_ENVIRONMENT": "development",
        "LAWS_TEST_LOCAL_PASSWORD": password,
        **{
            k: existing[k]
            for k in (
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_API_VERSION",
                "AZURE_OPENAI_DEPLOYMENT",
                "AZURE_OPENAI_API_KEY",
            )
        },
    }
    target.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    # The approved legacy importer reloads .env after clearing the process override.
    # Pin the repository's mandated real provider for its identity bootstrap.
    set_key(ROOT / ".env", "LLM_PROVIDER", "azurefoundry")
    # Pass the destination to the approved importer in-process, never in emitted command text.
    imported = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts/import_e2e_model_credentials_from_server.ps1"),
            "-DatabaseUrl",
            base + "laws_tests_identity_840",
            "-LocalPostgresContainer",
            "laws-tests-840-postgres",
            "-UseExistingPostgres",
            "-RequiredModel",
            "gpt-5-mini",
            "-VerifyModel",
        ],
        cwd=ROOT,
    )
    if imported.returncode:
        raise SystemExit(
            "Approved model import failed; inspect redacted prerequisite output above."
        )
    from aijurisdictionagents.api_db import ApiDatabaseStore

    store = ApiDatabaseStore(
        db_path=ROOT / "runs/storage/api/sqlite/unused",
        blob_root=ROOT / "runs/issue840/blobs",
        db_option="postgres",
        db_cloud=values["LAWS_TEST_IDENTITY_DATABASE_URL"],
    )
    user = store.find_user_by_email(email="laws-tests-840@example.invalid")
    synthetic_password = secrets.token_urlsafe(24)
    if user is None:
        user = store.create_user(
            email="laws-tests-840@example.invalid",
            password=synthetic_password,
            full_name="Synthetic Laws Test",
        )
    else:
        # Existing synthetic user is deliberately reset for a fresh run.
        from aijurisdictionagents.api_db.store import _hash_password

        with psycopg.connect(values["LAWS_TEST_IDENTITY_DATABASE_URL"]) as conn:
            conn.execute(
                "UPDATE users SET password_hash=%s WHERE user_id=%s",
                (_hash_password(synthetic_password), user.user_id),
            )
    evidence = ROOT / "runs/issue840"
    # Isolate repeated acceptance runs; this fixed account exists only in this local fixture DB.
    with psycopg.connect(values["LAWS_TEST_DATABASE_URL"]) as conn:
        if conn.execute("SELECT to_regclass('test_sessions')").fetchone()[0]:
            conn.execute("DELETE FROM test_sessions WHERE user_id=%s", (user.user_id,))
            conn.execute("DELETE FROM web_sessions WHERE user_id=%s", (user.user_id,))
    (evidence / "synthetic-account.json").write_text(
        json.dumps({"email": user.email, "password": synthetic_password, "user_id": user.user_id}),
        encoding="utf-8",
    )
    print("Local laws-tests PostgreSQL and synthetic identity: ready. Secrets redacted.")


if __name__ == "__main__":
    main()
