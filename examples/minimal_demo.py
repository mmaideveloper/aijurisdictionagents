"""Minimal runnable demo for the repository end-to-end contract simulations.

Run:
    python examples/minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aijurisdictionagents.e2e_workflows import (
    outcome_to_json,
    simulate_contract_summary_case,
    simulate_slovak_lease_review,
)


if __name__ == "__main__":
    output_root = Path("runs") / "minimal_demo"
    contract_outcome = simulate_contract_summary_case(output_root / "contract_summary_case")
    lease_outcome = simulate_slovak_lease_review(output_root / "slovak_lease_case")

    print("=== Contract summary scenario ===")
    print(outcome_to_json(contract_outcome))
    print()
    print("=== Slovak lease review scenario ===")
    print(outcome_to_json(lease_outcome))
