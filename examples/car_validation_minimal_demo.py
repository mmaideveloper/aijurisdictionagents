"""Minimal runnable demo for AICarValidatorAgent and slovakia_car_validate tool.

Run:
    python examples/car_validation_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aijurisdictionagents.agents import AICarValidatorAgent
from aijurisdictionagents.tools import answer_slovak_car_validation_question
from aijurisdictionagents.tools.registry import build_default_tool_registry


if __name__ == "__main__":
    agent = AICarValidatorAgent()

    print("=== VIN + SPZ plan ===")
    print(
        agent.build_car_validation_plan(
            vin="1HGCM82633A004352",
            spz="BA123AB",
        )
    )

    print()
    print("=== Question auto-detection demo ===")
    print(
        answer_slovak_car_validation_question(
            "Over mi auto VIN 1HGCM82633A004352 a SPZ BA123AB, chcem aj historiu vlastnikov.",
        )
    )

    print()
    print("=== Direct tool run (API optional) ===")
    registry = build_default_tool_registry()
    tool_result = registry.run(
        "slovakia_car_validate",
        vin="1HGCM82633A004352",
        spz="BA123AB",
        run_api_check=True,
    )
    print(tool_result.message)
    print(tool_result.records[0]["api_check"])
