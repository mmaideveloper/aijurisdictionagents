from __future__ import annotations

import argparse

from aijurisdictionagents.api_db import ApiDatabaseStore


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
        print("Dry run only: no schema changes were applied.")
        return

    store.initialize()
    print("Schema update completed successfully.")


if __name__ == "__main__":
    main()
