"""Run on Linux: python examples/log_lifecycle_demo.py (synthetic files only)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.server.log_lifecycle import publish_latest, prune_logs

if __name__ == "__main__":
    with TemporaryDirectory() as folder:
        root = Path(folder)
        log = root / "synthetic-job-20261009.log"
        log.write_text("synthetic operational event\n", encoding="utf-8")
        alias = root / "synthetic-job-latest.log"
        publish_latest(log, alias)
        prune_logs(root, retention_days=7)
        assert alias.read_text(encoding="utf-8") == log.read_text(encoding="utf-8")
        print("Atomic relative latest-log publication and retention: PASS")
