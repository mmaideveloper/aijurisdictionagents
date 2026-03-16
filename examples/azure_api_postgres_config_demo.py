from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os

from aijurisdictionagents.api_db import ApiDataConfig


@contextmanager
def temporary_env(overrides: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        os.environ.update(overrides)
        yield
    finally:
        for key, previous_value in previous.items():
            if previous_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value


def mask_password(connection_uri: str) -> str:
    prefix, separator, suffix = connection_uri.partition(":secret-password@")
    if not separator:
        return connection_uri
    return f"{prefix}:<redacted>@{suffix}"


def main() -> None:
    overrides = {
        "DB_OPTION": "azure",
        "STORAGE_OPTION": "azure",
        "DB_CLOUD": "postgresql://jurisadmin%40db-juris-dev:secret-password@db-juris-dev.postgres.database.azure.com:5432/aijurisdiction?sslmode=require",
        "STORE_CLOUD": "https://storageexample.blob.core.windows.net/case-documents",
    }

    with temporary_env(overrides):
        config = ApiDataConfig.from_env()
        config.validate()

        print(f"DB option: {config.db_option}")
        print(f"Storage option: {config.storage_option}")
        print(f"DB connection: {mask_password(config.db_connection_uri)}")
        print(f"Blob prefix: {config.store_cloud}")
        print("Azure API database configuration validates successfully.")


if __name__ == "__main__":
    main()
