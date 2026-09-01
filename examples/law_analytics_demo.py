"""Print a deterministic MCP amendment ranking from the configured laws database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "aijuristiction-api"))
from app.mcp_api import _tool_rank_laws_by_amendments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2025)
    args = parser.parse_args()
    result = _tool_rank_laws_by_amendments(
        {"country_code": "SK", "published_year": args.year, "amendment_year": args.year, "limit": 5}
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
