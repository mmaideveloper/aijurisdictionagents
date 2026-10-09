"""Offline policy example: python examples/court_work_retry_demo.py."""
from datetime import datetime, timezone

import httpx

from services.court_decision_collector.retry import schedule_retry

if __name__ == "__main__":
    retry = schedule_retry(httpx.ConnectError("synthetic"), attempt=1,
                           reference="synthetic", now=datetime.now(timezone.utc))
    print(retry)
