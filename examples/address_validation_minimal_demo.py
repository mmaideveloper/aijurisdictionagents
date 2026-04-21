"""Minimal runnable demo for AIAddressValidatorAgent.

Run:
    python examples/address_validation_minimal_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aijurisdictionagents.agents import AIAddressValidatorAgent


if __name__ == "__main__":
    agent = AIAddressValidatorAgent()
    sample_text = "Doručovaciu adresu nastavte na Námestie slobody 1, 811 06 Bratislava."
    result = agent.validate_from_text(sample_text)

    print("Input:", sample_text)
    print("Result OK:", result["ok"])
    print("Mapping:", result["mapping"])
    print("Lookup URL:", result["lookup_url"])
