from __future__ import annotations

from services.laws_collector import LawsCollectorConfig, SlovLexImportPlanner


def main() -> None:
    config = LawsCollectorConfig.from_env()
    planner = SlovLexImportPlanner(config=config)

    print("country:", config.country_code)
    print("database_name:", config.country_db_name)
    print("historical_import_from:", config.historical_import_from.isoformat())
    print("initial_probe_year:", planner.initial_year)
    print("archive_root:", config.archive_root)
    print("local_storage:", config.storage_root)
    print("full_import_command:")
    print(
        r"$env:LAWS_COLLECTOR_IMPORT='zip'; "
        r"$env:LAWS_COLLECTOR_MAX_RUNNING_TIME='0'; "
        r".\skills\laws-collector\scripts\start_laws_collector.ps1 "
        r"-Fixture live -DatabaseOption postgres -PollSeconds 300 -MaxCycles 0 -MaxProbes 50 -Background"
    )


if __name__ == "__main__":
    main()
