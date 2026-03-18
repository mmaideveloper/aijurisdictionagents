from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

try:
    import psycopg
except ImportError as exc:  # pragma: no cover - script-level dependency guard
    raise SystemExit(
        "psycopg is required for this script. Install the same dependencies used by the API."
    ) from exc


_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")


def _build_connection_uri() -> str:
    db_cloud = (os.getenv("DB_CLOUD") or "").strip()
    if db_cloud:
        return db_cloud

    host = (os.getenv("AZURE_POSTGRES_SERVER_NAME") or "").strip().lower()
    database_name = (os.getenv("AZURE_POSTGRES_DATABASE_NAME") or "").strip()
    admin_username = (os.getenv("AZURE_POSTGRES_ADMIN_USERNAME") or "").strip()
    admin_password = (os.getenv("AZURE_POSTGRES_ADMIN_PASSWORD") or "").strip()

    missing = [
        name
        for name, value in (
            ("AZURE_POSTGRES_SERVER_NAME", host),
            ("AZURE_POSTGRES_DATABASE_NAME", database_name),
            ("AZURE_POSTGRES_ADMIN_USERNAME", admin_username),
            ("AZURE_POSTGRES_ADMIN_PASSWORD", admin_password),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            f"Missing PostgreSQL settings: {', '.join(missing)}. "
            "Set DB_CLOUD or the Azure PostgreSQL env vars in .env."
        )

    if not host.endswith(".postgres.database.azure.com"):
        host = f"{host}.postgres.database.azure.com"

    encoded_user = quote(admin_username, safe="")
    encoded_password = quote(admin_password, safe="")
    return (
        f"postgresql://{encoded_user}:{encoded_password}@{host}:5432/"
        f"{database_name}?sslmode=require"
    )


def verify_connection() -> None:
    connection_uri = _build_connection_uri()
    try:
        with psycopg.connect(connection_uri) as conn:
            version = conn.execute("SELECT version()").fetchone()
        print("Connection successful.")
        if version:
            print(f"PostgreSQL version: {version[0]}")
    except psycopg.OperationalError as exc:
        print(f"Connection failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    verify_connection()
