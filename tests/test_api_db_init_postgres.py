"""Exercise concurrent schema setup only on explicitly selected loopback PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Barrier
from urllib.parse import urlsplit

import pytest

from aijurisdictionagents.api_db import ApiDatabaseStore


def test_concurrent_api_schema_initialization(tmp_path: Path) -> None:
    target = os.getenv("DB_CLOUD", "")
    if os.getenv("DB_OPTION") != "postgres" or urlsplit(target).hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        pytest.skip("Requires explicit synthetic loopback PostgreSQL")

    def store() -> ApiDatabaseStore:
        return ApiDatabaseStore(
            db_path=tmp_path / "unused",
            blob_root=tmp_path / "blobs",
            db_option="postgres",
            db_cloud=target,
        )

    store().initialize()
    start = Barrier(4)

    def initialize() -> None:
        start.wait(timeout=15)
        for _ in range(3):
            store().initialize()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(initialize) for _ in range(4)]
        for future in futures:
            future.result(timeout=60)
    store().check_connection()
