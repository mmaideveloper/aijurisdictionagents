from __future__ import annotations

import argparse

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description="Create per-country laws Postgres DB if it does not exist.")
    parser.add_argument("--admin-uri", required=True, help="Admin postgres URI (typically .../postgres)")
    parser.add_argument("--country", required=True, help="ISO country code, e.g. SK")
    args = parser.parse_args()

    country = args.country.strip().upper()
    if len(country) != 2 or not country.isalpha():
        raise ValueError("--country must be a 2-letter ISO code")

    db_name = f"laws_{country.lower()}"
    with psycopg.connect(args.admin_uri, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if exists:
            print(f"Database already exists: {db_name}")
            return
        conn.execute(f'CREATE DATABASE "{db_name}"')
        print(f"Created database: {db_name}")


if __name__ == "__main__":
    main()
