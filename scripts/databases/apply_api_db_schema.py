from __future__ import annotations

import argparse
from urllib.parse import unquote, urlsplit

from aijurisdictionagents.api_db import ApiDatabaseStore
from aijurisdictionagents.db_migrations import apply_sql_migrations
from app.flow_packs.store import FlowPackStore


def _redacted_target(target: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return target
    username = unquote(parsed.username or "postgres")
    hostname = parsed.hostname or "unknown-host"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{username}:***@{hostname}{port}{parsed.path}"


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
    print(f"Schema target: {_redacted_target(target)}")

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
        # Later migrations reference immutable flow-pack definitions. Bootstrap only that
        # prerequisite schema before the ordered migration runner handles the remaining API DB.
        FlowPackStore.from_env()
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
