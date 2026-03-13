from __future__ import annotations

import argparse

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply API database schema/migrations using current environment variables."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and show target backend without applying schema changes.",
    )
    args = parser.parse_args()

    store = ApiDatabaseStore.from_env()
    target = store.db_cloud if store.uses_postgres else str(store.db_path)

    print(f"DB_OPTION={store.db_option}")
    print(f"Schema target: {target}")

    if args.dry_run:
        if store.uses_postgres:
            pending = apply_sql_migrations(
                project="api",
                db_option=store.db_option,
                target=target,
                dry_run=True,
            )
            if pending:
                print("Pending migrations:")
                for item in pending:
                    print(f" - {item}")
            else:
                print("No pending migrations.")
        else:
            print("Dry run only: local SQLite schema is code-driven.")
        return

    if store.uses_postgres:
        pending = apply_sql_migrations(
            project="api",
            db_option=store.db_option,
            target=target,
            dry_run=False,
        )
        if pending:
            print("Applied SQL migrations:")
            for item in pending:
                print(f" - {item}")
        else:
            print("No SQL migrations needed.")

    store.initialize()
    print("Schema update completed successfully.")


if __name__ == "__main__":
    main()
