from __future__ import annotations

from aijurisdictionagents.api_db import ApiDataConfig
from services.laws_collector import LawsCollectorConfig


def main() -> None:
    api_config = ApiDataConfig.from_env()
    laws_config = LawsCollectorConfig.from_env()

    print("API local sqlite:", api_config.db_path)
    print("API local files:", api_config.blob_root)
    print("Laws local sqlite:", laws_config.db_path)
    print("Laws local files:", laws_config.storage_root)
    print("API postgres data root: runs/storage/api/postgres/data")
    print("Laws postgres data root: runs/storage/laws-collector/postgres/data")


if __name__ == "__main__":
    main()
