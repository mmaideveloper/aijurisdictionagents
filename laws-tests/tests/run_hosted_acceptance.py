"""Real acceptance on an ephemeral hosted Linux runner; never reads laptop profiles."""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

import psycopg
from dotenv import set_key

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "runs/hosted-e2e/private-logs"
EVIDENCE = ROOT / "runs/hosted-e2e/evidence"


def model_settings(environ):
    names = ("ENDPOINT", "API_VERSION", "DEPLOYMENT", "API_KEY")
    values = {}
    for name in names:
        key = "E2E_AZURE_FOUNDRY_" + name
        value = environ.get(key, "").strip()
        if not value or value == "unknown-variable" or "\n" in value or "\r" in value:
            raise ValueError(f"Missing or invalid {key}")
        values[key] = value
    endpoint = urlsplit(values["E2E_AZURE_FOUNDRY_ENDPOINT"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError("Invalid E2E endpoint")
    if values["E2E_AZURE_FOUNDRY_DEPLOYMENT"] != "gpt-5-mini":
        raise ValueError("Hosted acceptance requires gpt-5-mini")
    return values


def run(name, args, cwd=ROOT):
    print(f"phase={name} status=started", flush=True)
    with (LOGS / (name + ".log")).open("wb") as log:
        result = subprocess.run(args, cwd=cwd, stdout=log, stderr=log, check=False)
    if result.returncode:
        raise RuntimeError(f"{name} failed (details withheld; private logs are not artifacts)")
    print(f"phase={name} status=passed", flush=True)


@contextmanager
def services(specifications):
    processes = []
    try:
        for name, args, cwd, extra in specifications:
            log = (LOGS / (name + ".log")).open("wb")
            try:
                process = subprocess.Popen(
                    args, cwd=cwd, env={**os.environ, **extra}, stdout=log, stderr=log
                )
            finally:
                log.close()
            processes.append(process)
        yield processes
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def ready(url, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(1)
    raise RuntimeError("Local service readiness failed")


def prepare(port, created):
    # This entry point may only create generated config in a clean hosted checkout.
    if (
        os.getenv("GITHUB_ACTIONS") != "true"
        or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted"
        or sys.platform != "linux"
    ):
        raise ValueError("Use a GitHub-hosted Linux runner")
    if (ROOT / ".env").exists() or (ROOT / ".env-laws-test").exists():
        raise ValueError("Refusing to overwrite existing runtime configuration")
    values = model_settings(os.environ)
    base = f"postgresql://postgres:synthetic-ci-password@127.0.0.1:{port}/"
    identity = base + "laws_tests_identity_hosted"
    with psycopg.connect(base + "postgres", autocommit=True) as conn:
        for name in ("laws-tests", "laws_tests_identity_hosted"):
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(
                    psycopg.sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                        psycopg.sql.Identifier(name)
                    )
                )
    baseline = {
        **values,
        "AI_MODEL_CREDENTIAL_ENCRYPTION_KEY": secrets.token_urlsafe(48),
        "DB_OPTION": "postgres",
        "DB_CLOUD": identity,
        "LLM_PROVIDER": "azurefoundry",
        "STORAGE_OPTION": "local",
        "STORE_LOCAL": str(ROOT / "runs/storage/laws-tests/blobs"),
        "EMAIL_DB_OPTION": "postgres",
        "EMAIL_DB_CLOUD": identity,
        "EMAIL_TRANSPORT": "log",
        "EMAIL_SCHEDULER_ENABLED": "false",
        "LOCAL_LLM_IO_LOGGING": "0",
        "API_KEY": "aijuris",
    }
    config = {
        "LAWS_TEST_DATABASE_URL": base + "laws-tests",
        "LAWS_TEST_IDENTITY_DATABASE_URL": identity,
        "LAWS_TEST_PUBLIC_URL": "http://127.0.0.1:8410",
        "LAWS_TEST_AUTH_URL": "http://127.0.0.1:8412/tests-authorize",
        "LAWS_TEST_ENVIRONMENT": "development",
        **{
            key.replace("E2E_AZURE_FOUNDRY_", "AZURE_OPENAI_"): value
            for key, value in values.items()
        },
    }
    for filename, settings in ((".env", baseline), (".env-laws-test", config)):
        path = ROOT / filename
        path.touch(mode=0o600)
        created.append(path)
        path.chmod(0o600)
        for key, value in settings.items():
            set_key(path, key, value)
    os.environ.update(baseline)
    os.environ["LAWS_TEST_E2E_PYTHON"] = sys.executable
    from aijurisdictionagents.db_migrations import apply_sql_migrations

    apply_sql_migrations(project="api", db_option="postgres", target=identity, dry_run=False)
    run(
        "real-model-bootstrap",
        [
            sys.executable,
            "scripts/bootstrap_e2e_model_credentials.py",
            "--required-model",
            "gpt-5-mini",
            "--verify-model",
        ],
    )
    run("migrate", [sys.executable, "-m", "laws_tests.cli", "migrate"])
    run("seed", [sys.executable, "-m", "laws_tests.cli", "seed-development"])
    from aijurisdictionagents.api_db import ApiDatabaseStore

    store = ApiDatabaseStore(
        db_path=Path("unused"),
        blob_root=ROOT / "runs/storage/laws-tests/blobs",
        db_option="postgres",
        db_cloud=identity,
    )
    password = secrets.token_urlsafe(24)
    user = store.create_user(
        email="laws-tests-840@example.invalid",
        password=password,
        full_name="Synthetic hosted acceptance",
    )
    account = ROOT / "runs/issue840/synthetic-account.json"
    account.parent.mkdir(parents=True, exist_ok=True)
    account.write_text(
        json.dumps(
            {
                "email": user.email,
                "password": password,
                "user_id": user.user_id,
                "database_port": port,
            }
        )
    )
    account.chmod(0o600)


def acceptance():
    python = sys.executable
    web = ROOT / "laws-tests/web"
    account_web = ROOT / "frontend/aijurisdictionfronend"
    vite = ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1"]
    run("reader-fixture", [python, "laws-tests/tests/reader_fixture.py"])
    run("reader-grants", [python, "laws-tests/tests/approve_legacy_acceptance.py"])
    legacy = [
        (service, [python, "laws-tests/tests/run_local_service.py", service], ROOT, {})
        for service in ("tests", "identity", "mcp")
    ]
    legacy += [
        ("tests-web", [*vite, "--port", "8410"], web, {}),
        (
            "account-web",
            [*vite, "--port", "8412"],
            account_web,
            {
                "VITE_API_BASE_URL": "http://127.0.0.1:8413",
                "VITE_LAWS_TEST_PUBLIC_URL": "http://127.0.0.1:8410",
            },
        ),
    ]
    with services(legacy):
        for url in (
            "http://127.0.0.1:8413/health",
            "http://127.0.0.1:8414/health",
            "http://127.0.0.1:8410/api/health",
            "http://127.0.0.1:8412",
        ):
            ready(url)
        run("account-reader-browser", ["npx", "playwright", "test"], web)
    run("reader-cleanup", [python, "laws-tests/tests/reader_fixture.py", "cleanup"])
    run("account-cleanup", [python, "laws-tests/tests/cleanup_acceptance.py"])
    run("private-fixture", [python, "laws-tests/tests/private_fixture.py"])
    private = [
        (
            "private-api",
            [
                python,
                "-m",
                "uvicorn",
                "laws_tests.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8941",
                "--no-access-log",
            ],
            ROOT,
            {},
        ),
        ("private-worker", [python, "-m", "laws_tests.jobs"], ROOT, {}),
        ("private-web", [*vite, "--port", "8940", "--mode", "private-e2e"], web, {}),
    ]
    with services(private):
        ready("http://127.0.0.1:8940/api/health")
        run(
            "private-browser",
            ["npx", "playwright", "test", "--config", "private.playwright.config.ts"],
            web,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5440)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError("Invalid local PostgreSQL port")
    LOGS.mkdir(parents=True, exist_ok=True, mode=0o700)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    os.environ["PYTHONPATH"] = os.pathsep.join((str(ROOT / "laws-tests/api"), str(ROOT / "src")))
    result = {
        "sha": os.getenv("GITHUB_SHA"),
        "runner": "github-hosted-ubuntu",
        "status": "failed",
        "model": "gpt-5-mini",
        "provider": "azurefoundry",
        "databasePort": args.port,
    }
    created = []
    failed = False
    cleanup_failed = False
    try:
        prepare(args.port, created)
        acceptance()
        result["status"] = "passed"
    except (ValueError, RuntimeError, OSError, psycopg.Error) as exc:
        failed = True
        result["failureType"] = type(exc).__name__
        print(
            "Hosted acceptance failed; private runtime logs are excluded from artifacts.",
            flush=True,
        )
    finally:
        # Config may have been written even if later bootstrap failed.
        if ROOT / ".env-laws-test" in created:
            for script in ("private_fixture.py", "reader_fixture.py", "cleanup_acceptance.py"):
                try:
                    run(
                        "final-cleanup-" + script.removesuffix(".py"),
                        [sys.executable, "laws-tests/tests/" + script, "cleanup"],
                    )
                except (RuntimeError, OSError):
                    failed = True
                    cleanup_failed = True
        for path in created:
            path.unlink(missing_ok=True)
        if failed:
            result["status"] = "failed"
        result["cleanupPassed"] = not cleanup_failed
        # Only exception class names: never export raw logs, messages, prompts or credentials.
        result["diagnostics"] = {
            path.stem: re.findall(
                r"(?m)^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):",
                path.read_text(errors="replace"),
            )[-8:]
            for path in LOGS.glob("*.log")
        }
        (EVIDENCE / "result-manifest.json").write_text(json.dumps(result, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
