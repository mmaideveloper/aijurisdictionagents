"""Run on jurisdigta-server: provision encrypted-USB profiles without exporting secrets."""

import json
import os
import pwd
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit


def write_new(path: Path, values: dict):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        print(f"{path.name}: already exists; preserved")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write("".join(f"{key}={value}\n" for key, value in values.items()))
    print(f"{path.name}: provisioned (values redacted)")


def main():
    mount = Path("/mnt/jurisdigta-backup")
    source = subprocess.check_output(
        ["findmnt", "-no", "SOURCE", "--target", str(mount)], text=True
    ).strip()
    kind = subprocess.check_output(["lsblk", "-ndo", "TYPE", source], text=True).strip()
    if kind != "crypt" or not os.path.ismount(mount):
        raise SystemExit("Verified encrypted USB mount required")
    script = """import json,os
from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.llm.routing import _resolve_azure_openai_api_version
s=ApiDatabaseStore.from_env()
p=next(p for p in s.list_ai_model_providers() if p.provider_id=='azurefoundryeu' and p.enabled)
m=next(m for m in s.list_ai_model_profiles(provider_id=p.provider_id) if m.model_code=='gpt-5-mini' and m.enabled)
c=next(c for c in s.list_ai_model_credentials(provider_id=p.provider_id,reveal=True) if c.enabled and c.secret_type=='api_key')
print(json.dumps({'identity':s.db_cloud,'laws':os.getenv('LAWS_DB_CLOUD',''),'endpoint':p.base_url,'version':_resolve_azure_openai_api_version(model=m.model_code,provider_api_version=p.api_version),'model':m.deployment_name,'key':c.secret_value}))
"""
    result = subprocess.run(
        ["docker", "exec", "-i", "jurisdigta-api", "python", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,  # Handle return codes below without exposing captured secrets.
    )
    if result.returncode:
        raise SystemExit("Approved server credential lookup failed (details redacted)")
    approved = json.loads(result.stdout)
    if not approved.get("key"):
        raise SystemExit("Approved model credential missing")
    uri = urlsplit(approved["identity"])
    if uri.scheme not in {"postgres", "postgresql"}:
        raise SystemExit("Production identity must use PostgreSQL")
    laws_uri = urlsplit(approved["laws"])
    if laws_uri.scheme not in {"postgres", "postgresql"} or (
        laws_uri.hostname,
        laws_uri.port or 5432,
    ) != (uri.hostname, uri.port or 5432):
        raise SystemExit(
            "Collector on the approved database server required; configure separate migration access otherwise"
        )
    password = secrets.token_urlsafe(40)
    host = uri.hostname or ""
    netloc = f"laws_tests_app:{quote(password)}@{host}:{uri.port or 5432}"
    prod = {
        "LAWS_TEST_DATABASE_URL": urlunsplit(("postgresql", netloc, "/laws-tests", uri.query, "")),
        "LAWS_TEST_IDENTITY_DATABASE_URL": approved["identity"],
        "LAWS_TEST_PUBLIC_URL": "https://tests.jurisdigta.eu",
        "LAWS_TEST_AUTH_URL": "https://web.jurisdigta.eu/tests-authorize",
        "LAWS_TEST_ENVIRONMENT": "production",
        "AZURE_OPENAI_ENDPOINT": approved["endpoint"],
        "AZURE_OPENAI_DEPLOYMENT": approved["model"],
        "AZURE_OPENAI_API_VERSION": approved["version"],
        "AZURE_OPENAI_API_KEY": approved["key"],
    }
    usb = mount / "jurisdigta-env/profiles/laws-tests"
    write_new(usb / "prod/.env-laws-test", prod)
    write_new(
        usb / "prod/.env-laws-test.migration",
        {
            "LAWS_TEST_MIGRATION_DATABASE_URL": urlunsplit(
                (uri.scheme, uri.netloc, "/laws-tests", uri.query, "")
            )
        },
    )
    # Local database credentials are independent. The real model credential is approved
    # for E2E by the repository's existing server-import policy.
    local_password = secrets.token_urlsafe(40)
    dev = {
        **prod,
        "LAWS_TEST_ENVIRONMENT": "development",
        "LAWS_TEST_PUBLIC_URL": "http://127.0.0.1:8410",
        "LAWS_TEST_AUTH_URL": "http://127.0.0.1:8412/tests-authorize",
        "LAWS_TEST_DATABASE_URL": f"postgresql://postgres:{quote(local_password)}@127.0.0.1:5440/laws-tests",
        "LAWS_TEST_IDENTITY_DATABASE_URL": f"postgresql://postgres:{quote(local_password)}@127.0.0.1:5440/laws_tests_identity_840",
        "LAWS_TEST_LOCAL_PASSWORD": local_password,
    }
    write_new(usb / "dev/.env-laws-test", dev)
    # Upgrade only this project's identity role; never export identity admin credentials.
    prod_path = usb / "prod/.env-laws-test"
    stored = dict(
        line.split("=", 1)
        for line in prod_path.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    # Apply the operator-confirmed hostname correction without rotating any credentials.
    if any(stored.get(key) != prod[key] for key in ("LAWS_TEST_PUBLIC_URL", "LAWS_TEST_AUTH_URL")):
        stored["LAWS_TEST_PUBLIC_URL"] = prod["LAWS_TEST_PUBLIC_URL"]
        stored["LAWS_TEST_AUTH_URL"] = prod["LAWS_TEST_AUTH_URL"]
        temporary = prod_path.with_name(".env-laws-test.routing-new")
        write_new(temporary, stored)
        temporary.replace(prod_path)
        print("Production public hostname aligned; credential values preserved")
    identity_uri = urlsplit(stored["LAWS_TEST_IDENTITY_DATABASE_URL"])
    if identity_uri.username != "laws_tests_identity":
        identity_password = secrets.token_urlsafe(40)
        stored["LAWS_TEST_IDENTITY_DATABASE_URL"] = urlunsplit(
            (
                "postgresql",
                f"laws_tests_identity:{quote(identity_password)}@{identity_uri.hostname}:{identity_uri.port or 5432}",
                identity_uri.path,
                identity_uri.query,
                "",
            )
        )
        temporary = prod_path.with_name(".env-laws-test.new")
        write_new(temporary, stored)
        temporary.replace(prod_path)
        print("Dedicated identity reader profile: prepared (role applied only at gated deployment)")
    if (
        not stored.get("LAWS_TEST_LAWS_DATABASE_URL")
        or stored.get("LAWS_TEST_LAWS_DATABASE_URL") == "unknown-variable"
    ):
        stored["LAWS_TEST_LAWS_DATABASE_URL"] = urlunsplit(
            (
                "postgresql",
                f"laws_tests_reader:{quote(secrets.token_urlsafe(40))}@{laws_uri.hostname}:{laws_uri.port or 5432}",
                laws_uri.path,
                laws_uri.query,
                "",
            )
        )
        temporary = prod_path.with_name(".env-laws-test.reader-new")
        write_new(temporary, stored)
        temporary.replace(prod_path)
        print(
            "Dedicated public law reader profile: prepared (role applied only at gated deployment)"
        )
    dev_path = usb / "dev/.env-laws-test"
    dev_stored = dict(
        line.split("=", 1)
        for line in dev_path.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    if not dev_stored.get("LAWS_TEST_LAWS_DATABASE_URL"):
        dev_stored["LAWS_TEST_LAWS_DATABASE_URL"] = (
            urlsplit(dev_stored["LAWS_TEST_DATABASE_URL"])
            ._replace(path="/laws_tests_sources_840")
            .geturl()
        )
        temporary = dev_path.with_name(".env-laws-test.reader-new")
        write_new(temporary, dev_stored)
        temporary.replace(dev_path)
    operator = pwd.getpwnam("jurisdigta-admin")
    os.chown(usb / "dev", operator.pw_uid, operator.pw_gid)
    os.chmod(usb, 0o711)
    os.chown(usb / "dev/.env-laws-test", operator.pw_uid, operator.pw_gid)
    runtime = Path("/srv/jurisdigta/secrets")
    runtime.mkdir(parents=True, exist_ok=True)
    for filename in (".env-laws-test", ".env-laws-test.migration"):
        dest = runtime / filename
        if not dest.exists() or filename == ".env-laws-test":
            descriptor = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write((usb / "prod" / filename).read_bytes())
        if filename == ".env-laws-test":
            os.chown(dest, 10840, 10840)
        print(f"Server runtime {filename}: present; values redacted")
    print(
        "Profiles provisioned; database roles, DNS, identity route and deployment validation remain separate release gates."
    )


if __name__ == "__main__":
    main()
