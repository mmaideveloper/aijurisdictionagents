from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "api" / "aijuristiction-api"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from app.main import _law_snapshot_payload  # noqa: E402


def main() -> None:
    payload = {
        "laws_by_country": {
            "sk": _law_snapshot_payload(country_code="SK"),
        }
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
