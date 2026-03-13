from __future__ import annotations

import argparse

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply SQL database migrations for a project using current environment variables."
    )
    parser.add_argument(
        "--project",
        default="api",
        help="Migration project under databases/migrations (default: api).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending migrations without applying them.",
    )
    args = parser.parse_args()

    store = ApiDatabaseStore.from_env()
    target = store.db_cloud if store.uses_postgres else str(store.db_path)

    print(f"Project={args.project}")
    print(f"DB_OPTION={store.db_option}")
    print(f"Schema target: {target}")

    pending = apply_sql_migrations(
        project=args.project,
        db_option=store.db_option,
        target=target,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        if pending:
            print("Pending migrations:")
            for item in pending:
                print(f" - {item}")
        else:
            print("No pending migrations.")
        return

    if pending:
        print("Applied migrations:")
        for item in pending:
            print(f" - {item}")
    else:
        print("No migrations needed.")


if __name__ == "__main__":
    main()
