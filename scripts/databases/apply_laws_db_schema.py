from __future__ import annotations

import argparse

from aijurisdictionagents.db_migrations import apply_sql_migrations
from services.laws_collector.config import LawsCollectorConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply laws collector database schema/migrations using current environment variables."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and show pending migrations without applying them.",
    )
    args = parser.parse_args()

    config = LawsCollectorConfig.from_env()
    config.validate()

    if config.db_backend != "postgres":
        raise ValueError("Laws collector schema migrations require LAWS_DB_BACKEND=postgres.")

    print(f"LAWS_DB_BACKEND={config.db_backend}")
    print(f"Schema target: {config.db_cloud}")

    pending = apply_sql_migrations(
        project="laws",
        db_option="azure",
        target=config.db_cloud,
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
        print("Applied SQL migrations:")
        for item in pending:
            print(f" - {item}")
    else:
        print("No SQL migrations needed.")

    print("Laws schema update completed successfully.")


if __name__ == "__main__":
    main()
