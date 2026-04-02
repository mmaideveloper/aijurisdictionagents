from __future__ import annotations

from datetime import date
import os

from services.laws_collector import LawsCollectorConfig, PostgresLawStore, SlovLexImportPlanner
from aijurisdictionagents.db_migrations import apply_sql_migrations


def main() -> None:
    db_cloud = os.getenv(
        "LAWS_DB_CLOUD",
        "postgresql://postgres:postgres@127.0.0.1:5432/laws_sk",
    ).strip()
    config = LawsCollectorConfig(
        country_code="SK",
        db_backend="postgres",
        db_local="",
        db_cloud=db_cloud,
        storage_local="",
        storage_cloud="",
        delta_poll_hours=3,
        initial_import_from=date(1993, 1, 1),
        historical_import_from=date(1993, 1, 1),
    )
    apply_sql_migrations(
        project="laws",
        db_option="postgres",
        target=db_cloud,
        dry_run=False,
    )
    store = PostgresLawStore.from_config(config)
    planner = SlovLexImportPlanner(config=config)
    progress = store.get_or_create_collector_progress(
        country_code=config.country_code,
        source_system="slov-lex",
        initial_year=planner.initial_year,
    )
    plan = planner.build_plan(progress=progress)

    print("Backend:", config.db_backend)
    print("Database:", config.country_db_name)
    print("Connection:", config.db_cloud)
    print("Initial year:", plan.initial_year)
    print("Last collector run:", plan.last_collector_run_at or "")
    print("Last processed law:", plan.last_processed_law or "")
    print("Next law to check:", plan.next_target.law_id)
    print("Next law URL:", plan.next_target.url)


if __name__ == "__main__":
    main()
