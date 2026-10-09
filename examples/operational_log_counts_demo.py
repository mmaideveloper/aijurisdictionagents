"""Offline synthetic example: python examples/operational_log_counts_demo.py."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.server.log_events import event_counts

if __name__ == "__main__":
    logs = '\n'.join([
        'level=info msg="flag evaluation succeeded" error=null',
        'level=error msg="synthetic missing file"',
        'work_retry error_type=HTTPStatusError',
        'INFO payload={"status_code":401}',
    ])
    counts = event_counts(logs)
    assert counts['failure'] == counts['retry'] == counts['access_denied'] == 1
    print(counts)
