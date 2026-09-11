"""Credential-free demonstration of the private dashboard definition."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("user_reporting", root / "Deployment/monitoring/user_reporting.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dashboard = module.build_dashboard()
    print(dashboard["title"])
    for panel in dashboard["panels"]:
        if panel.get("datasource") == module.DATA_SOURCE:
            print(" -", panel["title"])
    print("Synthetic example: 100 input (40 cached) + 25 output = 125 total")


if __name__ == "__main__":
    main()
