"""Minimal runnable demo for Slovak LV lookup planning.

Run:
    python examples/property_validation_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aijurisdictionagents.agents import AIPropertyValidatorAgent


if __name__ == "__main__":
    agent = AIPropertyValidatorAgent()

    print("=== Person-name nationwide lookup ===")
    print(
        agent.build_lv_lookup_plan(
            person_name="Ján Novák",
        )
    )

    print()
    print("=== LV-number lookup ===")
    print(
        agent.build_lv_lookup_plan(
            lv_number="1234",
            cadastral_unit="Staré Mesto",
            municipality="Bratislava",
        )
    )
