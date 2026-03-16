from __future__ import annotations

import os

from services.laws_collector.worker import run_worker


if __name__ == "__main__":
    os.environ.setdefault("LAWS_COUNTRY", "SK")
    os.environ.setdefault("LAWS_DB_BACKEND", "sqlite")
    os.environ.setdefault("LAWS_DB_LOCAL", "./databases/laws-collector/worker_demo.sqlite3")
    os.environ.setdefault("LAWS_WORKER_FIXTURE", "baseline")
    os.environ.setdefault("LAWS_WORKER_POLL_SECONDS", "1")
    os.environ.setdefault("LAWS_WORKER_MAX_CYCLES", "1")
    run_worker()
